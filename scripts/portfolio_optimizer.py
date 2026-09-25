import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import psycopg
from pypfopt import EfficientFrontier, risk_models, expected_returns
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices
import lightgbm as lgb

PG_PASSWORD = "aakash"

RAW_DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": PG_PASSWORD,
    "host": "localhost",
    "port": 5432,
}

MODEL_FILE = os.path.join(os.path.dirname(__file__), "..", "models", "lgbm_ranker.txt")

# Calibrated category baskets aligned with backfilled Equity & Hybrid universe
PROFILE_CONFIG = {
    "conservative": {
        "categories": [
            "Arbitrage Fund",
            "Conservative Hybrid Fund",
            "Equity Savings",
            "Aggressive Hybrid Fund",
            "Large Cap Fund",
        ],
        "target": "min_volatility",
    },
    "moderate": {
        "categories": [
            "Aggressive Hybrid Fund",
            "Multi Asset Allocation",
            "Large Cap Fund",
            "Flexi Cap Fund",
            "Mid Cap Fund",
        ],
        "target": "max_sharpe",
    },
    "aggressive": {
        "categories": [
            "Large & Mid Cap Fund",
            "Flexi Cap Fund",
            "Mid Cap Fund",
            "Small Cap Fund",
        ],
        "target": "max_sharpe",
    },
}


def get_best_scheme_per_category(target_categories: list[str]) -> list[tuple[int, str, str]]:
    booster = lgb.Booster(model_file=MODEL_FILE)

    query = """
        SELECT 
            m.scheme_code,
            s.scheme_name,
            s.category_id,
            c.sub_category_name,
            m.window_years,
            m.cagr,
            m.annualized_volatility,
            m.sharpe_ratio,
            m.sortino_ratio,
            m.max_drawdown,
            m.beta,
            m.alpha
        FROM scheme_metrics m
        JOIN schemes s ON m.scheme_code = s.scheme_code
        JOIN scheme_categories c ON s.category_id = c.id
        WHERE s.is_active = TRUE
          AND (s.scheme_name ILIKE '%Growth%' OR s.scheme_name ILIKE '%- Gr%')
          AND m.calculation_date = (SELECT MAX(calculation_date) FROM scheme_metrics);
    """
    with psycopg.connect(**RAW_DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            df = pd.DataFrame(rows, columns=cols)

    metric_cols = [
        "cagr", "annualized_volatility", "sharpe_ratio",
        "sortino_ratio", "max_drawdown", "beta", "alpha"
    ]
    for col in metric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df_1y = df[df["window_years"] == 1]
    df_3y = df[df["window_years"] == 3]

    merged = pd.merge(
        df_1y[["scheme_code", "scheme_name", "category_id", "sub_category_name"] + metric_cols],
        df_3y[["scheme_code"] + metric_cols],
        on="scheme_code",
        suffixes=("_1y", "_3y"),
        how="inner"
    )

    feature_cols = [
        "cagr_1y", "annualized_volatility_1y", "sharpe_ratio_1y", "sortino_ratio_1y", "max_drawdown_1y", "beta_1y", "alpha_1y",
        "cagr_3y", "annualized_volatility_3y", "sharpe_ratio_3y", "sortino_ratio_3y", "max_drawdown_3y", "beta_3y", "alpha_3y"
    ]

    merged["rank_score"] = booster.predict(merged[feature_cols])

    selected = []
    for cat in target_categories:
        cat_df = merged[merged["sub_category_name"].str.contains(cat, case=False, na=False)].copy()
        if not cat_df.empty:
            cat_df["is_direct"] = cat_df["scheme_name"].str.contains("Direct", case=False).astype(int)
            best_scheme = cat_df.sort_values(by=["is_direct", "rank_score"], ascending=[False, False]).iloc[0]
            selected.append((int(best_scheme["scheme_code"]), best_scheme["scheme_name"], cat))

    return selected


def fetch_price_series(scheme_codes: list[int], lookback_years: int = 3) -> pd.DataFrame:
    cutoff_date = (datetime.now() - timedelta(days=lookback_years * 365)).strftime("%Y-%m-%d")
    query = """
        SELECT scheme_code, nav_date, nav_value
        FROM daily_nav_records
        WHERE scheme_code = ANY(%s)
          AND nav_date >= %s
        ORDER BY nav_date ASC;
    """
    with psycopg.connect(**RAW_DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (scheme_codes, cutoff_date))
            rows = cur.fetchall()
            df = pd.DataFrame(rows, columns=["scheme_code", "nav_date", "nav_value"])

    df["nav_value"] = pd.to_numeric(df["nav_value"], errors="coerce")
    pivot = df.pivot(index="nav_date", columns="scheme_code", values="nav_value")
    return pivot.ffill().dropna()


def optimize_portfolio(risk_profile: str = "aggressive", investment_amount: float = 100000.0):
    profile = risk_profile.lower()
    if profile not in PROFILE_CONFIG:
        raise ValueError(f"Unknown profile: {risk_profile}. Choose conservative, moderate, or aggressive.")

    config = PROFILE_CONFIG[profile]
    print(f"\n==========================================================================")
    print(f"Generating Portfolio: [{profile.upper()}] | Capital: INR {investment_amount:,.2f}")
    print(f"==========================================================================")

    selected_schemes = get_best_scheme_per_category(config["categories"])
    scheme_codes = [s[0] for s in selected_schemes]
    meta_lookup = {s[0]: {"name": s[1], "category": s[2]} for s in selected_schemes}

    prices = fetch_price_series(scheme_codes)
    valid_codes = [c for c in scheme_codes if c in prices.columns]
    num_assets = len(valid_codes)

    if num_assets < 2:
        print(f"Insufficient active assets ({num_assets}) found for profile '{risk_profile}'.")
        return

    # Dynamic weight bounds guaranteed to satisfy sum(w) = 1.0:
    # Minimum 10%, Maximum scaled to allow full distribution across available assets
    min_w = 0.05
    max_w = min(0.60, max(0.30, 1.5 / num_assets))

    mu = expected_returns.capm_return(prices[valid_codes], risk_free_rate=0.065)
    S = risk_models.CovarianceShrinkage(prices[valid_codes]).ledoit_wolf()

    ef = EfficientFrontier(mu, S, weight_bounds=(min_w, max_w))

    if config["target"] == "min_volatility":
        ef.min_volatility()
    else:
        ef.max_sharpe(risk_free_rate=0.065)

    raw_weights = ef.clean_weights()
    perf = ef.portfolio_performance(verbose=False, risk_free_rate=0.065)

    latest_navs = get_latest_prices(prices[valid_codes])
    da = DiscreteAllocation(raw_weights, latest_navs, total_portfolio_value=investment_amount)
    allocation, leftover = da.lp_portfolio()

    summary = []
    for code, units in allocation.items():
        weight = raw_weights.get(code, 0.0)
        nav = float(latest_navs[code])
        invested = units * nav
        summary.append({
            "Category": meta_lookup[code]["category"],
            "Scheme Name": meta_lookup[code]["name"],
            "Target Weight": f"{weight * 100:.1f}%",
            "Allocated Capital": f"INR {invested:,.2f}",
            "Units": round(units, 3),
        })

    summary_df = pd.DataFrame(summary).sort_values(by="Target Weight", ascending=False)
    print(summary_df.to_string(index=False))

    print("\n--- Portfolio Expected Performance Metrics ---")
    print(f"Expected Annualized Return : {perf[0] * 100:.2f}%")
    print(f"Annualized Volatility       : {perf[1] * 100:.2f}%")
    print(f"Expected Sharpe Ratio      : {perf[2]:.2f}")
    print(f"Cash Leftover / Buffer     : INR {leftover:,.2f}")


if __name__ == "__main__":
    for profile in ["conservative", "moderate", "aggressive"]:
        optimize_portfolio(risk_profile=profile, investment_amount=100000.0)