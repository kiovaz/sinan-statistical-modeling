"""
db_config.py
Configuração central de conexão com o banco (PostgreSQL / Neon).

SEGURANÇA: nenhuma credencial fica escrita aqui. Tudo vem de variáveis de
ambiente, normalmente carregadas de um arquivo .env que NÃO deve ir para o
controle de versão (adicione `.env` ao seu .gitignore).

Exemplo de .env (crie na raiz do projeto):
    PGHOST=seu-host.neon.tech
    PGPORT=5432
    PGDATABASE=neondb
    PGUSER=seu_usuario
    PGPASSWORD=sua_senha_NOVA
    PGSSLMODE=require
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Caminho do CSV via ambiente, com fallback relativo ao projeto.
CSV_PATH = os.environ.get(
    "ZIKA_CSV_PATH",
    os.path.join(os.path.dirname(__file__), "ZIKA_BR_2018_2026_UNIFICADO.csv"),
)

# Pasta onde ficam os scripts SQL (01_schema.sql etc.)
SQL_DIR = os.environ.get("SQL_DIR", os.path.join(os.path.dirname(__file__), "sql"))


def get_connection():
    """Abre conexão lendo TODAS as credenciais do ambiente.

    Lança erro claro se faltar alguma variável obrigatória, em vez de
    silenciosamente tentar conectar com valor None.
    """
    obrigatorias = ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"]
    faltando = [v for v in obrigatorias if not os.environ.get(v)]
    if faltando:
        raise RuntimeError(
            "Variáveis de ambiente ausentes: "
            + ", ".join(faltando)
            + ". Crie um arquivo .env (veja db_config.py)."
        )

    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=os.environ.get("PGSSLMODE", "require"),
    )
