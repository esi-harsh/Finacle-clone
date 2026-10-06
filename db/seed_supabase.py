"""
Supabase Database Seeder for Finance Twin.
Loads `db/finacle_tables.sql` and `db/finance_seed_data.sql` into your Supabase PostgreSQL database.
"""

import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")


def get_connection_string():
    # If DATABASE_URL starts with postgresql://, use it directly
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        return DATABASE_URL
    
    # Check if SUPABASE_URL was erroneously set as a web URL
    if SUPABASE_URL.startswith("http"):
        project_ref = SUPABASE_URL.replace("https://", "").split(".")[0]
        print("\n" + "=" * 70)
        print("[!] NOTICE: SUPABASE_URL in .env is an HTTPS REST URL.")
        print("To connect directly to Supabase PostgreSQL, please set `DATABASE_URL` in .env:")
        print("=" * 70)
        print(f'DATABASE_URL="postgresql://postgres.{project_ref}:[YOUR_PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"')
        print("\nWhere to find it in Supabase:")
        print("1. Go to your Supabase Dashboard -> Project Settings -> Database")
        print("2. Under 'Connection string', select 'URI' (Transaction Mode or Session Mode)")
        print("3. Replace [YOUR-PASSWORD] with your Supabase database password.")
        print("=" * 70 + "\n")
        return None

    return None


def seed_supabase():
    conn_str = get_connection_string()
    if not conn_str:
        print("[!] Exiting. Please update .env with your DATABASE_URL and run this script again.")
        sys.exit(1)

    print("[*] Connecting to Supabase PostgreSQL database...")
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
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
        print(f"\n[!] Error seeding Supabase: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    seed_supabase()
