import concurrent.futures
from datetime import datetime, date
import psycopg
import requests

DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": "aakash",  # Use your real password
    "host": "localhost",
    "port": 5432,
}

BASE_API_URL = "https://api.mfapi.in/mf"
CUTOFF_YEARS = 5  # Backfill trailing 5 years of daily history
MAX_WORKERS = 8   # Concurrent threads


def get_target_schemes():
    """
    Selects active equity, hybrid, and index Growth schemes to backfill.
    """
    conn = psycopg.connect(**DB_CONFIG)
    cursor = conn.cursor()

    query = """
        SELECT s.scheme_code, s.scheme_name
        FROM schemes s
        JOIN scheme_categories c ON s.category_id = c.id
        WHERE s.is_active = TRUE
          AND (
            s.scheme_name ILIKE '%Growth%'
            OR s.scheme_name ILIKE '%- Gr%'
            OR s.scheme_name ILIKE '% Direct %'
          )
          AND (
            c.category_name ILIKE '%Equity%' 
            OR c.category_name ILIKE '%Hybrid%'
            OR c.sub_category_name ILIKE '%Index%'
            OR c.sub_category_name ILIKE '%Cap%'
          )
        ORDER BY s.scheme_code;
    """
    cursor.execute(query)
    schemes = cursor.fetchall()
    cursor.close()
    conn.close()
    return schemes


def fetch_and_store_scheme_history(scheme_tuple, cutoff_date):
    """
    Fetches daily NAV time-series for a single scheme from mfapi.in and upserts into PostgreSQL.
    """
    scheme_code, scheme_name = scheme_tuple
    url = f"{BASE_API_URL}/{scheme_code}"

    try:
        resp = requests.get(url, timeout=25)
        if resp.status_code != 200:
            return 0

        data = resp.json()
        nav_list = data.get("data", [])
        if not nav_list:
            return 0

        records_to_insert = []
        for entry in nav_list:
            try:
                nav_date = datetime.strptime(entry["date"], "%d-%m-%Y").date()
                if nav_date < cutoff_date:
                    continue
                nav_val = float(entry["nav"])
                records_to_insert.append((scheme_code, nav_date, nav_val))
            except (ValueError, KeyError):
                continue

        if not records_to_insert:
            return 0

        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                upsert_query = """
                    INSERT INTO daily_nav_records (scheme_code, nav_date, nav_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (scheme_code, nav_date) 
                    DO UPDATE SET nav_value = EXCLUDED.nav_value;
                """
                cur.executemany(upsert_query, records_to_insert)
            conn.commit()

        return len(records_to_insert)

    except Exception as e:
        print(f"[Error] Scheme {scheme_code}: {e}")
        return 0


def run_backfill():
    cutoff_date = date(date.today().year - CUTOFF_YEARS, 1, 1)
    schemes = get_target_schemes()
    total_schemes = len(schemes)

    print(f"[{datetime.now()}] Found {total_schemes} qualifying Growth schemes to backfill.")
    print(f"[{datetime.now()}] Target Cutoff Date: {cutoff_date}")
    print(f"[{datetime.now()}] Fetching history with {MAX_WORKERS} workers...")

    completed = 0
    total_records = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_scheme = {
            executor.submit(fetch_and_store_scheme_history, s, cutoff_date): s
            for s in schemes
        }

        for future in concurrent.futures.as_completed(future_to_scheme):
            scheme = future_to_scheme[future]
            try:
                inserted_count = future.result()
                total_records += inserted_count
                completed += 1
                if completed % 25 == 0 or completed == total_schemes:
                    print(
                        f"Progress: [{completed}/{total_schemes}] schemes completed. "
                        f"NAV records ingested: {total_records:,}"
                    )
            except Exception as exc:
                print(f"Scheme {scheme[0]} error: {exc}")

    print(f"[{datetime.now()}] Backfill completed! Total records ingested: {total_records:,}")


if __name__ == "__main__":
    run_backfill()