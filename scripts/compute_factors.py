from datetime import date, datetime
import numpy as np
import pandas as pd
import psycopg
from sqlalchemy import URL, create_engine

# Database Configuration with your credentials
PG_PASSWORD = "aakash"

RAW_DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": PG_PASSWORD,
    "host": "localhost",
    "port": 5432,
}

DB_URL_OBJ = URL.create(
    drivername="postgresql+psycopg",
    username="postgres",
    password=PG_PASSWORD,
    host="localhost",
    port=5432,
    database="mf_platform",
)

BENCHMARK_SCHEME_CODE = 118482  # BANDHAN Nifty 50 Index Fund - Direct Plan - Growth
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.065   # 6.5% standard RBI 91-day T-bill proxy


def get_nav_dataframe(engine, scheme_codes: list[int], benchmark_code: int, start_date: str) -> pd.DataFrame:
    all_codes = list(set(scheme_codes + [benchmark_code]))
    query = """
        SELECT scheme_code, nav_date, nav_value
        FROM daily_nav_records
        WHERE scheme_code = ANY(%(codes)s)
          AND nav_date >= %(start_date)s
        ORDER BY nav_date ASC;
    """
    raw_df = pd.read_sql(
        query,
        engine,
        params={"codes": all_codes, "start_date": start_date},
        parse_dates=["nav_date"],
    )

    if raw_df.empty:
        return pd.DataFrame()

    pivot_df = raw_df.pivot(index="nav_date", columns="scheme_code", values="nav_value")
    pivot_df = pivot_df.ffill().dropna(how="all")
    return pivot_df


def compute_metrics_for_series(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    rf_annual: float = RISK_FREE_RATE_ANNUAL,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> dict:
    clean_data = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(clean_data) < int(trading_days * 0.70):
        return None

    r = clean_data.iloc[:, 0].values
    r_bm = clean_data.iloc[:, 1].values
    n_days = len(r)

    # 1. CAGR
    cumulative_compound = np.prod(1.0 + r)
    years = n_days / trading_days
    cagr = (cumulative_compound ** (1.0 / years)) - 1.0

    # 2. Annualized Volatility
    daily_vol = np.std(r, ddof=1)
    annualized_vol = daily_vol * np.sqrt(trading_days)

    # 3. Sharpe Ratio
    rf_daily = (1.0 + rf_annual) ** (1.0 / trading_days) - 1.0
    excess_returns = r - rf_daily
    sharpe_ratio = (np.mean(excess_returns) / daily_vol * np.sqrt(trading_days)) if daily_vol > 1e-8 else 0.0

    # 4. Sortino Ratio
    downside_diff = np.minimum(0.0, excess_returns)
    downside_deviation = np.sqrt(np.mean(downside_diff**2)) * np.sqrt(trading_days)
    sortino_ratio = ((cagr - rf_annual) / downside_deviation) if downside_deviation > 1e-8 else 0.0

    # 5. Maximum Drawdown
    nav_series = np.cumprod(1.0 + r)
    running_max = np.maximum.accumulate(nav_series)
    drawdowns = (nav_series - running_max) / running_max
    max_drawdown = float(np.min(drawdowns))

    # 6. Beta
    cov_matrix = np.cov(r, r_bm)
    beta = (cov_matrix[0, 1] / cov_matrix[1, 1]) if cov_matrix[1, 1] > 1e-8 else 1.0

    # 7. Jensen's Alpha (Annualized)
    bm_cagr = (np.prod(1.0 + r_bm) ** (1.0 / years)) - 1.0
    expected_return = rf_annual + beta * (bm_cagr - rf_annual)
    alpha = cagr - expected_return

    return {
        "cagr": float(cagr),
        "annualized_volatility": float(annualized_vol),
        "sharpe_ratio": float(sharpe_ratio),
        "sortino_ratio": float(sortino_ratio),
        "max_drawdown": float(max_drawdown),
        "beta": float(beta),
        "alpha": float(alpha),
    }


def execute_metrics_pipeline():
    engine = create_engine(DB_URL_OBJ)
    conn = psycopg.connect(**RAW_DB_CONFIG)
    cursor = conn.cursor()

    calc_date = date.today()
    start_date = (calc_date - pd.DateOffset(years=4)).strftime("%Y-%m-%d")

    print(f"[{datetime.now()}] Reading qualifying schemes from database...")
    cursor.execute("""
        SELECT DISTINCT scheme_code 
        FROM daily_nav_records 
        WHERE scheme_code != %s
    """, (BENCHMARK_SCHEME_CODE,))
    schemes = [row[0] for row in cursor.fetchall()]

    print(f"[{datetime.now()}] Fetching NAV matrix for {len(schemes)} schemes against benchmark {BENCHMARK_SCHEME_CODE}...")
    nav_df = get_nav_dataframe(engine, schemes, BENCHMARK_SCHEME_CODE, start_date)

    if nav_df.empty or BENCHMARK_SCHEME_CODE not in nav_df.columns:
        print(f"Error: Benchmark code {BENCHMARK_SCHEME_CODE} missing or insufficient data.")
        return

    daily_returns = nav_df.pct_change().dropna(how="all")
    bm_returns = daily_returns[BENCHMARK_SCHEME_CODE]

    results = []
    windows = {1: TRADING_DAYS_PER_YEAR, 3: TRADING_DAYS_PER_YEAR * 3}

    print(f"[{datetime.now()}] Computing factor ratios across 1Y and 3Y horizons...")
    for code in schemes:
        if code not in daily_returns.columns:
            continue
        fund_r = daily_returns[code]

        for years, required_bars in windows.items():
            recent_fund_r = fund_r.iloc[-required_bars:]
            recent_bm_r = bm_returns.iloc[-required_bars:]

            stats = compute_metrics_for_series(recent_fund_r, recent_bm_r)
            if stats is None:
                continue

            results.append((
                code, calc_date, years,
                stats["cagr"], stats["annualized_volatility"],
                stats["sharpe_ratio"], stats["sortino_ratio"],
                stats["max_drawdown"], stats["beta"], stats["alpha"]
            ))

    if results:
        print(f"[{datetime.now()}] Upserting {len(results)} metrics into scheme_metrics table...")
        upsert_query = """
            INSERT INTO scheme_metrics (
                scheme_code, calculation_date, window_years, cagr,
                annualized_volatility, sharpe_ratio, sortino_ratio,
                max_drawdown, beta, alpha
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scheme_code, calculation_date, window_years)
            DO UPDATE SET
                cagr = EXCLUDED.cagr,
                annualized_volatility = EXCLUDED.annualized_volatility,
                sharpe_ratio = EXCLUDED.sharpe_ratio,
                sortino_ratio = EXCLUDED.sortino_ratio,
                max_drawdown = EXCLUDED.max_drawdown,
                beta = EXCLUDED.beta,
                alpha = EXCLUDED.alpha;
        """
        cursor.executemany(upsert_query, results)
        conn.commit()
        print(f"[{datetime.now()}] Metric computation completed successfully.")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    execute_metrics_pipeline()