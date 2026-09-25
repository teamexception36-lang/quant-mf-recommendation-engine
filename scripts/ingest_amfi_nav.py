from datetime import datetime
import psycopg
import requests

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": "aakash",  # Keep your real password here
    "host": "localhost",
    "port": 5432,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}


def parse_and_ingest_nav():
    print(f"[{datetime.now()}] Fetching raw AMFI NAV data...")
    response = requests.get(AMFI_NAV_URL, headers=HEADERS, timeout=90)
    response.raise_for_status()

    lines = response.text.splitlines()
    print(f"[{datetime.now()}] Downloaded {len(lines)} lines from AMFI.")

    conn = psycopg.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Load existing cache
        cursor.execute("SELECT name, id FROM asset_management_companies;")
        amc_cache = dict(cursor.fetchall())

        cursor.execute("SELECT category_name || ' - ' || sub_category_name, id FROM scheme_categories;")
        category_cache = dict(cursor.fetchall())

        cursor.execute("SELECT scheme_code FROM schemes;")
        existing_schemes = set(row[0] for row in cursor.fetchall())

        current_amc = "General Asset Management"
        current_category = "Open Ended Schemes"
        current_sub_category = "Other"

        schemes_to_insert = []
        nav_records = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Header / Section Tracking
            if ";" not in line:
                if "Mutual Fund" in line or "Asset Management" in line:
                    current_amc = line.strip()
                    if current_amc not in amc_cache:
                        cursor.execute(
                            "INSERT INTO asset_management_companies (name) VALUES (%s) RETURNING id;",
                            (current_amc,),
                        )
                        amc_id = cursor.fetchone()[0]
                        amc_cache[current_amc] = amc_id
                elif "Schemes" in line or "Open Ended" in line or "Close Ended" in line:
                    parts = line.split("(")
                    current_category = parts[0].strip()
                    current_sub_category = parts[1].replace(")", "").strip() if len(parts) > 1 else "General"
                    cat_key = f"{current_category} - {current_sub_category}"
                    if cat_key not in category_cache:
                        cursor.execute(
                            """
                            INSERT INTO scheme_categories (category_name, sub_category_name)
                            VALUES (%s, %s)
                            ON CONFLICT (category_name, sub_category_name) DO UPDATE 
                            SET category_name = EXCLUDED.category_name
                            RETURNING id;
                            """,
                            (current_category, current_sub_category),
                        )
                        cat_id = cursor.fetchone()[0]
                        category_cache[cat_key] = cat_id
                continue

            # Parse delimited data row
            parts = [p.strip() for p in line.split(";")]
            
            # Must have at least Scheme Code, ISINs, Name, NAV, Date
            if len(parts) < 5 or not parts[0].isdigit():
                continue

            scheme_code = int(parts[0])
            isin_growth = parts[1] if parts[1] not in ("-", "") else None
            isin_div = parts[2] if parts[2] not in ("-", "") else None
            
            # Handle variable number of middle columns (Scheme Name, Plan, Option)
            nav_str = parts[-2]
            date_str = parts[-1]
            scheme_name = " - ".join(p for p in parts[3:-2] if p)

            try:
                nav_value = float(nav_str)
                nav_date = datetime.strptime(date_str, "%d-%b-%Y").date()
            except ValueError:
                continue

            if scheme_code not in existing_schemes:
                cat_key = f"{current_category} - {current_sub_category}"
                cat_id = category_cache.get(cat_key)
                amc_id = amc_cache.get(current_amc)

                schemes_to_insert.append(
                    (scheme_code, isin_growth, isin_div, scheme_name, amc_id, cat_id)
                )
                existing_schemes.add(scheme_code)

            nav_records.append((scheme_code, nav_date, nav_value))

        print(f"[{datetime.now()}] Extracted {len(schemes_to_insert)} new schemes and {len(nav_records)} NAV records.")

        if schemes_to_insert:
            print(f"Persisting {len(schemes_to_insert)} schemes to database...")
            insert_schemes_query = """
                INSERT INTO schemes (scheme_code, isin_growth, isin_div_reinvestment, scheme_name, amc_id, category_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (scheme_code) DO NOTHING;
            """
            cursor.executemany(insert_schemes_query, schemes_to_insert)

        if nav_records:
            print(f"Persisting {len(nav_records)} daily NAV entries...")
            upsert_nav_query = """
                INSERT INTO daily_nav_records (scheme_code, nav_date, nav_value)
                VALUES (%s, %s, %s)
                ON CONFLICT (scheme_code, nav_date) 
                DO UPDATE SET nav_value = EXCLUDED.nav_value;
            """
            cursor.executemany(upsert_nav_query, nav_records)

        conn.commit()
        print(f"[{datetime.now()}] Initial ingestion completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Error during ingestion: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parse_and_ingest_nav()