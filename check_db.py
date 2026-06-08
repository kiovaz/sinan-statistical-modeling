import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

def check_db():
    try:
        conn = psycopg2.connect(
            host=os.environ.get("PGHOST"),
            port=os.environ.get("PGPORT", "5432"),
            dbname=os.environ.get("PGDATABASE"),
            user=os.environ.get("PGUSER"),
            password=os.environ.get("PGPASSWORD"),
            sslmode=os.environ.get("PGSSLMODE", "require")
        )
        cursor = conn.cursor()
        
        tables = [
            "tb_paciente",
            "tb_notificacao",
            "tb_dados_clinicos",
            "tb_geografia_epidemiologica",
            "tb_sistema_rastreabilidade",
            "tb_uf",
            "tb_municipio",
            "tb_unidade_saude",
            "tb_ocupacao",
            "tb_agravo",
            "tb_pais"
        ]
        
        print("=== Contagem de Registros por Tabela ===")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table.ljust(30)}: {count} registros")
            
        print("\n=== Testando Integridade Relacional (JOIN) ===")
        query = """
            SELECT p.id_paciente, n.dt_notificacao, d.dt_encerramento, g.id_municipio_not 
            FROM tb_notificacao n
            JOIN tb_paciente p ON n.id_paciente = p.id_paciente
            JOIN tb_dados_clinicos d ON n.id_notificacao = d.id_notificacao
            JOIN tb_geografia_epidemiologica g ON n.id_notificacao = g.id_notificacao
            LIMIT 5
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for row in rows:
            print(row)
            
    except Exception as e:
        print("Erro:", e)
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    check_db()
