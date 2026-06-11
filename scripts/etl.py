"""
etl.py — Pipeline ETL para a base ZIKA/SINAN (modelo normalizado)

Fluxo (Extract -> Transform -> Load):
  1. EXTRACT  : lê o CSV bruto em memória (com dtype=str para não perder zeros).
  2. TRANSFORM: limpa tipos, decodifica idade, trata inconsistências clínicas
                e DEDUPLICA por chave composta (sem identificador de pessoa).
  3. LOAD     : popula dimensões e depois as tabelas fato, em ordem de FK,
                com alinhamento seguro entre paciente e notificação.

Decisões de projeto (ver conversa):
  - Deduplicação no pandas, ANTES de carregar (mais eficiente p/ 236k linhas
    e elimina o risco de desalinhamento entre lotes).
  - Chave de duplicidade de NOTIFICAÇÃO:
      ID_AGRAVO + DT_SIN_PRI + NU_IDADE_N + CS_SEXO + ID_MN_RESI + ID_MUNICIP
    reforçada por NDUPLIC_N quando preenchido.
  - Representante mantido por grupo: registro mais COMPLETO (menos campos
    vazios); empate -> DT_DIGITA mais antiga; empate -> menor índice.
  - Removidos são gravados em duplicatas_removidas.csv (trilha de auditoria).
  - idade_anos é calculada aqui (não fica mais None).
  - Inconsistências clínicas que a trigger bloqueante barraria são corrigidas
    em transform, para não derrubar lotes inteiros na carga.
"""
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

from scripts.db_config import get_connection, CSV_PATH

# Colunas que formam a chave de duplicidade de notificação
CHAVE_DUP = ["ID_AGRAVO", "DT_SIN_PRI", "NU_IDADE_N", "CS_SEXO", "ID_MN_RESI", "ID_MUNICIP"]

REL_DUPLICATAS = "duplicatas_removidas.csv"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------
# Helpers de limpeza de valores escalares
# --------------------------------------------------------------------------
def clean_int(val):
    if pd.isna(val) or str(val).strip() == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def clean_str(val):
    if pd.isna(val) or str(val).strip() == "":
        return None
    return str(val).strip()


def clean_date(val):
    if pd.isna(val) or str(val).strip() == "":
        return None
    dt = pd.to_datetime(val, errors="coerce")
    return None if pd.isna(dt) else dt.date()


def decode_age(age_code):
    """Decodifica NU_IDADE_N -> idade em anos (alinhado à função SQL).
    Unidade 4 = anos; 1/2/3 (hora/dia/mês) = menos de 1 ano -> 0.
    Idades implausíveis (>120) viram None.
    """
    if pd.isna(age_code) or str(age_code).strip() == "":
        return None
    try:
        s = str(int(float(age_code))).zfill(4)
        unidade = int(s[0])
        valor = int(s[1:])
        if unidade == 4:
            return valor if 0 <= valor <= 120 else None
        if unidade in (1, 2, 3):
            return 0
        return None
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# TRANSFORM: deduplicação por chave composta
# --------------------------------------------------------------------------
def deduplicar(df):
    """Mantém 1 representante por grupo da chave composta.
    Critério: mais completo -> DT_DIGITA mais antiga -> menor índice.
    Grava os removidos em REL_DUPLICATAS. Retorna o DataFrame limpo.
    """
    n0 = len(df)
    df = df.copy()
    df["_idx_orig"] = np.arange(n0)

    # 1) "completude" = quantidade de campos não vazios na linha
    df["_completude"] = df.notna().sum(axis=1)

    # 2) DT_DIGITA como data p/ desempate (NaT vai por último)
    df["_dt_digita"] = pd.to_datetime(df.get("DT_DIGITA"), errors="coerce")

    # NDUPLIC_N preenchido (>1 no SINAN sinaliza duplicidade) entra como dica:
    # rebaixa a prioridade desse registro para ser o descartado do grupo.
    nd = pd.to_numeric(df.get("NDUPLIC_N"), errors="coerce")
    df["_marcado_sinan"] = nd.notna() & (nd > 1)

    # Ordena de forma que o PRIMEIRO de cada grupo seja o representante:
    #   - não marcado pelo SINAN primeiro (_marcado_sinan False < True)
    #   - mais completo primeiro (completude desc)
    #   - digitação mais antiga primeiro
    #   - menor índice original
    df_ord = df.sort_values(
        by=["_marcado_sinan", "_completude", "_dt_digita", "_idx_orig"],
        ascending=[True, False, True, True],
        na_position="last",
    )

    # Chave composta como string (NaN tratado como token fixo p/ agrupar)
    chave = df_ord[CHAVE_DUP].fillna("∅").astype(str).agg("|".join, axis=1)
    eh_primeiro = ~chave.duplicated(keep="first")

    representantes = df_ord[eh_primeiro]
    removidos = df_ord[~eh_primeiro]

    # Trilha de auditoria: salva os removidos com a chave do grupo
    if len(removidos) > 0:
        out = removidos.drop(columns=["_completude", "_dt_digita",
                                      "_marcado_sinan", "_idx_orig"],
                             errors="ignore").copy()
        out.insert(0, "_chave_grupo", chave[~eh_primeiro].values)
        out.to_csv(REL_DUPLICATAS, index=False)
        log(f"Duplicatas removidas: {len(removidos)} (relatório em {REL_DUPLICATAS})")
    else:
        log("Nenhuma duplicata encontrada pela chave composta.")

    # devolve na ordem original dos representantes, sem colunas auxiliares
    limpo = (representantes
             .sort_values("_idx_orig")
             .drop(columns=["_completude", "_dt_digita", "_marcado_sinan", "_idx_orig"],
                   errors="ignore")
             .reset_index(drop=True))
    log(f"Registros: {n0} -> {len(limpo)} após deduplicação.")
    return limpo


def corrigir_inconsistencias_clinicas(df):
    """Evita que a trigger BLOQUEANTE de validação clínica derrube lotes.
    Aplica as mesmas regras, mas corrigindo em vez de abortar:
      - evolução = óbito (2/3) sem dt_obito  -> evolução vira 9 (Ignorado)
      - dt_obito presente com evolução = Cura -> evolução vira 9
      - dt_obito anterior a dt_sin_pri        -> zera dt_obito
    Retorna df ajustado e um dicionário de contagens.
    """
    df = df.copy()
    evol = pd.to_numeric(df.get("EVOLUCAO"), errors="coerce")
    dt_obito = pd.to_datetime(df.get("DT_OBITO"), errors="coerce")
    dt_sin = pd.to_datetime(df.get("DT_SIN_PRI"), errors="coerce")

    cont = {}

    m1 = evol.isin([2, 3]) & dt_obito.isna()
    cont["obito_sem_data"] = int(m1.sum())
    df.loc[m1, "EVOLUCAO"] = "9"

    m2 = dt_obito.notna() & (evol == 1)
    cont["cura_com_obito"] = int(m2.sum())
    df.loc[m2, "EVOLUCAO"] = "9"

    m3 = dt_obito.notna() & dt_sin.notna() & (dt_obito < dt_sin)
    cont["obito_antes_sintoma"] = int(m3.sum())
    df.loc[m3, "DT_OBITO"] = pd.NA

    total = sum(cont.values())
    if total:
        log(f"Inconsistências clínicas corrigidas: {cont}")
    return df


# --------------------------------------------------------------------------
# LOAD: dimensões
# --------------------------------------------------------------------------
def carregar_dimensoes(conn, df):
    log("Carregando dimensões a partir do CSV...")
    cur = conn.cursor()

    ufs = set(df["SG_UF_NOT"].dropna()) | set(df["SG_UF"].dropna())
    municipios = (set(df["ID_MUNICIP"].dropna()) | set(df["ID_MN_RESI"].dropna())
                  | set(df.get("COMUNINF", pd.Series(dtype=str)).dropna()))
    unidades = set(df.get("ID_UNIDADE", pd.Series(dtype=str)).dropna())
    ocupacoes = set(df.get("ID_OCUPA_N", pd.Series(dtype=str)).dropna())
    agravos = set(df["ID_AGRAVO"].dropna())
    paises = (set(df.get("ID_PAIS", pd.Series(dtype=str)).dropna())
              | set(df.get("COPAISINF", pd.Series(dtype=str)).dropna()))

    # As dimensões do seed (04) já trazem nomes corretos; aqui usamos
    # ON CONFLICT DO NOTHING para apenas COMPLETAR o que faltar, sem
    # sobrescrever o que o seed populou.
    # Mapa código IBGE (2 díg.) -> sigla, para não inserir UF com sigla errada
    # caso alguma não esteja no seed.
    UF_SIGLA = {
        11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
        21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
        28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
        42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
    }
    ufs_data = [(clean_int(u), UF_SIGLA.get(clean_int(u), str(u)), "Desconhecido")
                for u in ufs if clean_int(u) is not None]
    execute_values(cur, "INSERT INTO tb_uf (id_uf, sg_uf, nm_uf) VALUES %s ON CONFLICT DO NOTHING", ufs_data)

    # id_uf é derivado dos 2 PRIMEIROS dígitos do código IBGE do município
    # (ex.: 3550308 -> 35 = SP). Sem isso, os JOINs município->UF falham e as
    # views por UF (vw_casos_uf_ano, fn_resumo_epidemiologico) retornam vazio.
    # IMPORTANTE: só atribui se o prefixo for uma UF REAL (está em UF_SIGLA).
    # Códigos inválidos do SINAN (ex.: 9999999, 0000000) ficam com id_uf NULL,
    # evitando violar a foreign key tb_municipio_id_uf_fkey.
    def uf_do_municipio(cod):
        try:
            uf = int(str(int(cod))[:2])
            return uf if uf in UF_SIGLA else None
        except (ValueError, TypeError):
            return None

    mun_data = [(clean_int(m), uf_do_municipio(m), f"Município {clean_int(m)}", None)
                for m in municipios if clean_int(m) is not None]
    execute_values(cur, "INSERT INTO tb_municipio (id_municipio, id_uf, nm_municipio, id_regional) VALUES %s ON CONFLICT DO NOTHING", mun_data)

    uni_data = [(clean_str(u), None, f"CNES {clean_str(u)}", None) for u in unidades if clean_str(u)]
    execute_values(cur, "INSERT INTO tb_unidade_saude (id_cnes, id_municipio, nm_unidade, tp_unidade) VALUES %s ON CONFLICT DO NOTHING", uni_data)

    ocu_data = [(clean_str(o), f"CBO {clean_str(o)}") for o in ocupacoes if clean_str(o)]
    execute_values(cur, "INSERT INTO tb_ocupacao (id_cbo, nm_ocupacao) VALUES %s ON CONFLICT DO NOTHING", ocu_data)

    agr_data = [(clean_str(a), "Febre pelo vírus Zika" if "A92" in str(a) else f"Agravo {a}")
                for a in agravos if clean_str(a)]
    execute_values(cur, "INSERT INTO tb_agravo (id_cid, nm_agravo) VALUES %s ON CONFLICT DO NOTHING", agr_data)

    pais_data = [(clean_int(p), "Brasil" if clean_int(p) == 1 else f"País {clean_int(p)}")
                 for p in paises if clean_int(p) is not None]
    execute_values(cur, "INSERT INTO tb_pais (id_pais, nm_pais) VALUES %s ON CONFLICT DO NOTHING", pais_data)

    conn.commit()
    cur.close()
    log("Dimensões carregadas.")


# --------------------------------------------------------------------------
# LOAD: tabelas fato (carga linha-alinhada e segura)
# --------------------------------------------------------------------------
def carregar_fatos(conn, df, lote=20000):
    log("Carregando tabelas fato...")
    cur = conn.cursor()
    total = 0

    for ini in range(0, len(df), lote):
        bloco = df.iloc[ini:ini + lote]
        try:
            # 1) Pacientes — itera sobre o MESMO objeto (bloco) o tempo todo,
            #    garantindo alinhamento posicional com os IDs retornados.
            pac = [(
                clean_str(r.ID_OCUPA_N) if hasattr(r, "ID_OCUPA_N") else None,
                clean_str(r.CS_SEXO),
                clean_str(r.NU_IDADE_N),
                decode_age(r.NU_IDADE_N),
                clean_int(r.CS_GESTANT),
                clean_int(r.CS_RACA),
                clean_int(r.CS_ESCOL_N) if hasattr(r, "CS_ESCOL_N") else None,
            ) for r in bloco.itertuples(index=False)]

            ids_pac = execute_values(
                cur,
                "INSERT INTO tb_paciente (id_cbo, cs_sexo, nu_idade_n, idade_anos, "
                "cs_gestant, cs_raca, cs_escolaridade) VALUES %s RETURNING id_paciente",
                pac, fetch=True,
            )

            # 2) Notificações — mesma iteração posicional
            notif = [(
                ids_pac[i][0],
                clean_str(r.ID_AGRAVO),
                clean_str(r.ID_UNIDADE) if hasattr(r, "ID_UNIDADE") else None,
                clean_date(r.DT_NOTIFIC),
                clean_int(r.SEM_NOT) if hasattr(r, "SEM_NOT") else None,
                clean_int(r.NU_ANO),
                clean_int(r.TP_NOT) if hasattr(r, "TP_NOT") else None,
                clean_str(r.CS_SUSPEIT) if hasattr(r, "CS_SUSPEIT") else None,
            ) for i, r in enumerate(bloco.itertuples(index=False))]

            ids_not = execute_values(
                cur,
                "INSERT INTO tb_notificacao (id_paciente, id_agravo, id_cnes_not, "
                "dt_notificacao, sem_notificacao, nu_ano, tp_notificacao, cs_suspeito) "
                "VALUES %s RETURNING id_notificacao",
                notif, fetch=True,
            )

            # 3) Sub-tabelas (clínicos, geografia, rastreabilidade)
            clinicos, geo, sistema = [], [], []
            for i, r in enumerate(bloco.itertuples(index=False)):
                nid = ids_not[i][0]
                clinicos.append((
                    nid, clean_date(r.DT_SIN_PRI), clean_int(r.SEM_PRI) if hasattr(r, "SEM_PRI") else None,
                    clean_date(r.DT_INVEST) if hasattr(r, "DT_INVEST") else None,
                    clean_date(r.DT_ENCERRA) if hasattr(r, "DT_ENCERRA") else None,
                    clean_date(r.DT_OBITO) if hasattr(r, "DT_OBITO") else None,
                    clean_int(r.CLASSI_FIN), clean_int(r.CRITERIO) if hasattr(r, "CRITERIO") else None,
                    clean_int(r.DOENCA_TRA) if hasattr(r, "DOENCA_TRA") else None,
                    clean_int(r.EVOLUCAO),
                ))
                geo.append((
                    nid, clean_int(r.ID_MUNICIP), clean_int(r.ID_MN_RESI),
                    clean_int(r.COMUNINF) if hasattr(r, "COMUNINF") else None,
                    clean_int(r.ID_PAIS) if hasattr(r, "ID_PAIS") else None,
                    clean_int(r.COPAISINF) if hasattr(r, "COPAISINF") else None,
                    clean_int(r.TPAUTOCTO) if hasattr(r, "TPAUTOCTO") else None,
                ))
                sistema.append((
                    nid, clean_date(r.DT_DIGITA) if hasattr(r, "DT_DIGITA") else None,
                    clean_int(r.NDUPLIC_N) if hasattr(r, "NDUPLIC_N") else None,
                    clean_int(r.IN_VINCULA) if hasattr(r, "IN_VINCULA") else None,
                    clean_int(r.CS_FLXRET) if hasattr(r, "CS_FLXRET") else None,
                    clean_int(r.FLXRECEBI) if hasattr(r, "FLXRECEBI") else None,
                    clean_str(r.TP_SISTEMA) if hasattr(r, "TP_SISTEMA") else None,
                    clean_str(r.arquivo_origem) if hasattr(r, "arquivo_origem") else None,
                ))

            execute_values(cur, "INSERT INTO tb_dados_clinicos (id_notificacao, dt_sin_pri, sem_pri, dt_investigacao, dt_encerramento, dt_obito, classi_fin, criterio, doenca_trabalho, evolucao) VALUES %s", clinicos)
            execute_values(cur, "INSERT INTO tb_geografia_epidemiologica (id_notificacao, id_municipio_not, id_municipio_resi, id_municipio_inf, id_pais_resi, id_pais_inf, tp_autoctonia) VALUES %s", geo)
            execute_values(cur, "INSERT INTO tb_sistema_rastreabilidade (id_notificacao, dt_digitacao, nduplic_n, in_vincula, cs_flxret, flxrecebi, tp_sistema, arquivo_origem) VALUES %s", sistema)

            conn.commit()
            total += len(bloco)
            log(f"  {total}/{len(df)} registros carregados...")
        except Exception as e:
            conn.rollback()
            log(f"ERRO no lote {ini}-{ini+lote}: {e}")
            raise  # não engole o erro silenciosamente

    cur.close()
    log(f"Carga concluída. Total: {total}")


def run_etl():
    log("=== ETL ZIKA/SINAN ===")
    # EXTRACT
    log(f"Lendo CSV: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, dtype=str)
    log(f"Linhas lidas: {len(df)}")

    # TRANSFORM
    df = corrigir_inconsistencias_clinicas(df)
    df = deduplicar(df)

    # LOAD
    conn = get_connection()
    try:
        carregar_dimensoes(conn, df)
        carregar_fatos(conn, df)
    finally:
        conn.close()
    log("=== ETL finalizado ===")


if __name__ == "__main__":
    run_etl()
