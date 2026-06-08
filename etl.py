import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

DB_HOST = os.environ.get("PGHOST", "ep-calm-rice-ackd5wqt-pooler.sa-east-1.aws.neon.tech")
DB_PORT = os.environ.get("PGPORT", "5432")
DB_NAME = os.environ.get("PGDATABASE", "neondb")
DB_USER = os.environ.get("PGUSER", "neondb_owner")
DB_PASS = os.environ.get("PGPASSWORD", "npg_mr0YqOSNQn8j")
DB_SSLMODE = os.environ.get("PGSSLMODE", "require")

CSV_PATH = r"C:\Users\caiov\OneDrive\Área de Trabalho\modelagem_bd\sinan-statistical-modeling\ZIKA_BR_2018_2026_UNIFICADO.csv"

def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS, sslmode=DB_SSLMODE
    )

def clean_date(val):
    if pd.isna(val) or val == '' or str(val).strip() == '': return None
    try: return pd.to_datetime(val).date()
    except: return None

def clean_int(val):
    if pd.isna(val) or val == '' or str(val).strip() == '': return None
    try: return int(float(val))
    except: return None

def clean_str(val):
    if pd.isna(val) or str(val).strip() == '': return None
    return str(val).strip()

def extract_and_load_dimensions(conn):
    print(f"[{datetime.now()}] Iniciando a extração das Dimensões...")
    ufs, municipios, unidades, ocupacoes, agravos, paises = set(), set(), set(), set(), set(), set()
    chunksize = 100000
    for chunk in pd.read_csv(CSV_PATH, dtype=str, chunksize=chunksize):
        ufs.update(chunk['SG_UF_NOT'].dropna().unique())
        ufs.update(chunk['SG_UF'].dropna().unique())
        municipios.update(chunk['ID_MUNICIP'].dropna().unique())
        municipios.update(chunk['ID_MN_RESI'].dropna().unique())
        municipios.update(chunk['COMUNINF'].dropna().unique())
        unidades.update(chunk['ID_UNIDADE'].dropna().unique())
        ocupacoes.update(chunk['ID_OCUPA_N'].dropna().unique())
        agravos.update(chunk['ID_AGRAVO'].dropna().unique())
        paises.update(chunk['ID_PAIS'].dropna().unique())
        paises.update(chunk['COPAISINF'].dropna().unique())

    cursor = conn.cursor()
    ufs_data = [(clean_int(uf), str(uf), 'Desconhecido') for uf in ufs if clean_int(uf) is not None]
    execute_values(cursor, "INSERT INTO tb_uf (id_uf, sg_uf, nm_uf) VALUES %s ON CONFLICT DO NOTHING", ufs_data)
    
    municipios_data = [(clean_int(m), None, f'Município {m}', None) for m in municipios if clean_int(m) is not None]
    execute_values(cursor, "INSERT INTO tb_municipio (id_municipio, id_uf, nm_municipio, id_regional) VALUES %s ON CONFLICT DO NOTHING", municipios_data)

    unidades_data = [(clean_str(u), None, f'CNES {u}', None) for u in unidades if clean_str(u) is not None]
    execute_values(cursor, "INSERT INTO tb_unidade_saude (id_cnes, id_municipio, nm_unidade, tp_unidade) VALUES %s ON CONFLICT DO NOTHING", unidades_data)

    ocupacoes_data = [(clean_str(o), f'CBO {o}') for o in ocupacoes if clean_str(o) is not None]
    execute_values(cursor, "INSERT INTO tb_ocupacao (id_cbo, nm_ocupacao) VALUES %s ON CONFLICT DO NOTHING", ocupacoes_data)

    agravos_data = [(clean_str(a), 'Zika Vírus' if 'A92' in str(a) else f'Agravo {a}') for a in agravos if clean_str(a) is not None]
    execute_values(cursor, "INSERT INTO tb_agravo (id_cid, nm_agravo) VALUES %s ON CONFLICT DO NOTHING", agravos_data)

    paises_data = [(clean_int(p), 'Brasil' if clean_int(p)==1 else f'País {p}') for p in paises if clean_int(p) is not None]
    execute_values(cursor, "INSERT INTO tb_pais (id_pais, nm_pais) VALUES %s ON CONFLICT DO NOTHING", paises_data)
    conn.commit()
    cursor.close()
    print(f"[{datetime.now()}] Dimensões populadas com sucesso!")

def run_etl():
    conn = get_connection()
    extract_and_load_dimensions(conn)
    
    print(f"[{datetime.now()}] Iniciando a carga nas tabelas normalizadas...")
    chunksize = 20000 # Menor chunk para gerenciar o retorno de IDs múltiplos com segurança
    cursor = conn.cursor()
    total_processed = 0
    
    for chunk in pd.read_csv(CSV_PATH, dtype=str, chunksize=chunksize):
        # Preparar dados do Paciente
        pacientes_data = []
        for _, row in chunk.iterrows():
            pacientes_data.append((
                clean_str(row.get('ID_OCUPA_N')),
                clean_str(row.get('CS_SEXO')),
                clean_str(row.get('NU_IDADE_N')),
                None, # idade_anos populada via trigger ou function no banco se quiser, mas aqui a trigger nao foi feita na tb_paciente, vamos calcular
                clean_int(row.get('CS_GESTANT')),
                clean_int(row.get('CS_RACA')),
                clean_int(row.get('CS_ESCOL_N'))
            ))
            
        try:
            # 1. Inserir Pacientes e pegar IDs
            query_paciente = "INSERT INTO tb_paciente (id_cbo, cs_sexo, nu_idade_n, idade_anos, cs_gestant, cs_raca, cs_escolaridade) VALUES %s RETURNING id_paciente"
            ids_paciente = execute_values(cursor, query_paciente, pacientes_data, fetch=True)
            
            # Preparar Notificação
            notif_data = []
            for i, row in enumerate(chunk.itertuples(index=False)):
                row_dict = row._asdict()
                notif_data.append((
                    ids_paciente[i][0],
                    clean_str(row_dict.get('ID_AGRAVO')),
                    clean_str(row_dict.get('ID_UNIDADE')),
                    clean_date(row_dict.get('DT_NOTIFIC')),
                    clean_int(row_dict.get('SEM_NOT')),
                    clean_int(row_dict.get('NU_ANO')),
                    clean_int(row_dict.get('TP_NOT')),
                    clean_str(row_dict.get('CS_SUSPEIT'))
                ))
            
            # 2. Inserir Notificações e pegar IDs
            query_notif = "INSERT INTO tb_notificacao (id_paciente, id_agravo, id_cnes_not, dt_notificacao, sem_notificacao, nu_ano, tp_notificacao, cs_suspeito) VALUES %s RETURNING id_notificacao"
            ids_notificacao = execute_values(cursor, query_notif, notif_data, fetch=True)
            
            # Preparar as 3 sub-tabelas
            clinicos_data, geo_data, sistema_data = [], [], []
            for i, row in enumerate(chunk.itertuples(index=False)):
                row_dict = row._asdict()
                n_id = ids_notificacao[i][0]
                
                clinicos_data.append((
                    n_id, clean_date(row_dict.get('DT_SIN_PRI')), clean_int(row_dict.get('SEM_PRI')),
                    clean_date(row_dict.get('DT_INVEST')), clean_date(row_dict.get('DT_ENCERRA')),
                    clean_date(row_dict.get('DT_OBITO')), clean_int(row_dict.get('CLASSI_FIN')),
                    clean_int(row_dict.get('CRITERIO')), clean_int(row_dict.get('DOENCA_TRA')),
                    clean_int(row_dict.get('EVOLUCAO'))
                ))
                
                geo_data.append((
                    n_id, clean_int(row_dict.get('ID_MUNICIP')), clean_int(row_dict.get('ID_MN_RESI')),
                    clean_int(row_dict.get('COMUNINF')), clean_int(row_dict.get('ID_PAIS')),
                    clean_int(row_dict.get('COPAISINF')), clean_int(row_dict.get('TPAUTOCTO'))
                ))
                
                sistema_data.append((
                    n_id, clean_date(row_dict.get('DT_DIGITA')), clean_int(row_dict.get('NDUPLIC_N')),
                    clean_int(row_dict.get('IN_VINCULA')), clean_int(row_dict.get('CS_FLXRET')),
                    clean_int(row_dict.get('FLXRECEBI')), clean_str(row_dict.get('TP_SISTEMA')),
                    clean_str(row_dict.get('arquivo_origem'))
                ))

            # 3. Inserir Dados Complementares
            execute_values(cursor, "INSERT INTO tb_dados_clinicos (id_notificacao, dt_sin_pri, sem_pri, dt_investigacao, dt_encerramento, dt_obito, classi_fin, criterio, doenca_trabalho, evolucao) VALUES %s", clinicos_data)
            execute_values(cursor, "INSERT INTO tb_geografia_epidemiologica (id_notificacao, id_municipio_not, id_municipio_resi, id_municipio_inf, id_pais_resi, id_pais_inf, tp_autoctonia) VALUES %s", geo_data)
            execute_values(cursor, "INSERT INTO tb_sistema_rastreabilidade (id_notificacao, dt_digitacao, nduplic_n, in_vincula, cs_flxret, flxrecebi, tp_sistema, arquivo_origem) VALUES %s", sistema_data)
            
            conn.commit()
            total_processed += len(chunk)
            print(f"[{datetime.now()}] Inseridos {total_processed} registros no modelo normalizado...")
        except Exception as e:
            print(f"Erro na inserção do chunk: {e}")
            conn.rollback()

    cursor.close()
    conn.close()
    print(f"[{datetime.now()}] ETL Finalizado com sucesso. Total: {total_processed}")

if __name__ == "__main__":
    run_etl()
