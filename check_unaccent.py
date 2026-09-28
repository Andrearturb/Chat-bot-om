import os
from sqlalchemy import create_engine, text

url = os.getenv("DATABASE_URL", "")
engine = create_engine(url)

with engine.connect() as conn:
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        conn.commit()
        result = conn.execute(text("SELECT unaccent('Mossor\u00f3')"))
        print("unaccent available:", result.scalar())
    except Exception as ex:
        print("unaccent not available:", ex)
