"""
check_db.py — Verificação pós-carga: contagens, integridade e duplicatas.
"""
from scripts.db_config import get_connection

TABELAS = [
    "tb_paciente", "tb_notificacao", "tb_dados_clinicos",
    "tb_geografia_epidemiologica", "tb_sistema_rastreabilidade",
    "tb_uf", "tb_municipio", "tb_unidade_saude", "tb_ocupacao",
    "tb_agravo", "tb_pais", "tb_auditoria",
]


def check_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        print("=== Contagem de registros por tabela ===")
        for t in TABELAS:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"{t.ljust(32)}: {cur.fetchone()[0]}")

        print("\n=== Integridade relacional (JOIN das fatos) ===")
        cur.execute("""
            SELECT p.id_paciente, p.idade_anos, n.dt_notificacao,
                   d.classi_fin, g.id_municipio_not
            FROM tb_notificacao n
            JOIN tb_paciente p              ON n.id_paciente = p.id_paciente
            JOIN tb_dados_clinicos d        ON n.id_notificacao = d.id_notificacao
            JOIN tb_geografia_epidemiologica g ON n.id_notificacao = g.id_notificacao
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(row)

        # Confirma que idade_anos NÃO está toda nula (bug do ETL antigo)
        cur.execute("SELECT COUNT(*) FROM tb_paciente WHERE idade_anos IS NOT NULL")
        print(f"\nPacientes com idade_anos preenchida: {cur.fetchone()[0]}")

        print("\n=== Auditoria de duplicatas pós-carga (deve ser 0 grupos) ===")
        cur.execute("SELECT COUNT(*) FROM fn_detecta_duplicatas()")
        n = cur.fetchone()[0]
        print(f"Grupos duplicados remanescentes: {n}"
              + ("  ✓ base limpa" if n == 0 else "  ⚠ verificar dedup"))
    except Exception as e:
        print("Erro:", e)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    check_db()
