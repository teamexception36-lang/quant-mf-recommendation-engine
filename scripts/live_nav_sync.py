import io
import requests
import pandas as pd
import psycopg
from datetime import datetime

AMFI_LATEST_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

PG_PASSWORD = "aakash"
DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": PG_PASSWORD,
    "host": "localhost",
    "port": 5432,
}

def sync_today_live_nav():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching latest live NAV file from AMFI...")
    response = requests.get(AMFI_LATEST_NAV_URL, timeout=30)
    
    if response.status_code != 200:
        print(f"Failed to fetch live NAV data. HTTP Status: {response.status_code}")
        return

    lines = response.text.splitlines()
    data_rows = []
    
    for line in lines:
        parts = line.strip().split(";")
        # Valid AMFI NAV lines contain 6 semicolon-separated fields:
        # Scheme Code; ISIN Div Payout/ISIN Growth; ISIN Div Reinvestment; Scheme Name; Net Asset Value; Date
        if len(parts) >= 6 and parts[0].isdigit():
            scheme_code = int(parts[0])
            scheme_name = parts[3].strip()
            nav_str = parts[4].strip()
            date_str = parts[5].strip()
            
            try:
                nav_val = float(nav_str)
                # Parse date format (AMFI format: 'DD-Mon-YYYY', e.g. '25-Sep-2026')
                nav_date = datetime.strptime(date_str, "%d-%b-%Y").strftime("%Y-%m-%d")
                data_rows.append((scheme_code, nav_date, nav_val))
            except (ValueError, TypeError):
                continue

    df = pd.DataFrame(data_rows, columns=["scheme_code", "nav_date", "nav_value"])
    print(f"Extracted {len(df):,} scheme NAV entries for live sync.")

    # Perform Upsert into PostgreSQL
    query = """
        INSERT INTO daily_nav_records (scheme_code, nav_date, nav_value)
        VALUES (%s, %s, %s)
        ON CONFLICT (scheme_code, nav_date) 
        DO UPDATE SET nav_value = EXCLUDED.nav_value;
    """

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.executemany(query, data_rows)
            conn.commit()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Live NAV database sync completed successfully.")

if __name__ == "__main__":
    sync_today_live_nav()