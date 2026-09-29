import os
import psycopg
from dotenv import load_dotenv

load_dotenv("../.env")

def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])

if __name__ == "__main__":
        with get_conn() as conn:
            rows = conn.execute("SELECT name, unit FROM sensors ORDER BY id").fetchall()
            for r in rows:
                print(r)