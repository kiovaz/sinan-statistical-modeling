import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.environ.get("PGHOST")
DB_PORT = os.environ.get("PGPORT", "5432")
DB_NAME = os.environ.get("PGDATABASE")
DB_USER = os.environ.get("PGUSER")
DB_PASS = os.environ.get("PGPASSWORD")
DB_SSLMODE = os.environ.get("PGSSLMODE", "require")

def reset_db():
    print("Recriando as tabelas para o modelo Altamente Normalizado...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            sslmode=DB_SSLMODE
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # 1. Apaga as tabelas antigas em cascata
        print("Apagando tabelas antigas e suas views em cascata...")
        tabelas = [
            "tb_auditoria_notificacao", "tb_auditoria", "tb_sistema_rastreabilidade", 
            "tb_geografia_epidemiologica", "tb_dados_clinicos", "tb_notificacao", "tb_paciente",
            "tb_uf", "tb_municipio", "tb_unidade_saude", "tb_ocupacao", "tb_agravo", "tb_pais"
        ]
        for t in tabelas:
            cursor.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
        
        # 2. Roda o arquivo 01_schema.sql
        print("Executando 01_schema.sql...")
        with open("sql/01_schema.sql", "r", encoding="utf-8") as f:
            cursor.execute(f.read())
            
        # 3. Roda o 02_functions_triggers.sql
        print("Executando 02_functions_triggers.sql...")
        with open("sql/02_functions_triggers.sql", "r", encoding="utf-8") as f:
            cursor.execute(f.read())
            
        # 4. Roda o 03_views.sql
        print("Executando 03_views.sql...")
        with open("sql/03_views.sql", "r", encoding="utf-8") as f:
            cursor.execute(f.read())

        print("Banco resetado com sucesso! Modelo normalizado aplicado.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    reset_db()
