"""
Supabase Seeder Script for Finance Twin.
Connects to Supabase PostgreSQL and loads `db/finacle_tables.sql` and `db/finance_seed_data.sql`.
"""

import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_URL")


def seed_supabase():
    if not DATABASE_URL:
        print("[!] ERROR: No DATABASE_URL or SUPABASE_URL found in .env.")
        print("Please add your Supabase connection string to .env, e.g.:")
        print('DATABASE_URL="postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres"')
        sys.exit(1)

    print(f"[*] Connecting to Supabase database...")
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                print("[*] 1/2 Loading schema from db/finacle_tables.sql...")
                with open("db/finacle_tables.sql", "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                cur.execute(schema_sql)
                print("[+] Schema created successfully (24 tables, triggers, views).")

                print("[*] 2/2 Loading seed data from db/finance_seed_data.sql (Client 200)...")
                with open("db/finance_seed_data.sql", "r", encoding="utf-8") as f:
                    seed_sql = f.read()
                cur.execute(seed_sql)
                print("[+] Seed data loaded successfully (806 documents, 4,090 line items).")

        print("\n[SUCCESS] Supabase database setup is complete!")
    except Exception as ex:
        print(f"[!] Error seeding Supabase: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    seed_supabase()
