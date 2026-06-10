"""
reset_db.py — Recria o esquema do zero e aplica schema, funções, views e seed.

Ordem: DROP em cascata -> 01_schema -> 02_functions_triggers -> 03_views -> 04_seed.
"""
import os
from scripts.db_config import get_connection, SQL_DIR

# Ordem importa: schema antes de funções/views; seed por último.
SCRIPTS = [
    "01_schema.sql",
    "02_functions_triggers.sql",
    "03_views.sql",
    "04_seed_dimensoes.sql",
]

# Tabelas a remover antes de recriar (ordem indiferente por causa do CASCADE).
TABELAS = [
    "tb_auditoria", "tb_sistema_rastreabilidade", "tb_geografia_epidemiologica",
    "tb_dados_clinicos", "tb_notificacao", "tb_paciente",
    "tb_municipio", "tb_unidade_saude", "tb_ocupacao", "tb_agravo",
    "tb_pais", "tb_uf",
]


def reset_db():
    print("Recriando o banco (modelo normalizado)...")
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        print("Apagando tabelas antigas (CASCADE)...")
        for t in TABELAS:
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
        # remove a materialized view de KPI, se existir
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_kpi_cards CASCADE;")

        for script in SCRIPTS:
            caminho = os.path.join(SQL_DIR, script)
            print(f"Executando {script}...")
            with open(caminho, "r", encoding="utf-8") as f:
                cur.execute(f.read())

        print("Banco resetado com sucesso!")
    except Exception as e:
        print(f"Erro ao resetar: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    reset_db()
