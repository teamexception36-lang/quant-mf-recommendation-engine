import os
import sys
from datetime import datetime, timedelta
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import numpy as np
import pandas as pd
import psycopg
from pypfopt import EfficientFrontier, risk_models, expected_returns
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices
import lightgbm as lgb

# Include scripts folder in path for modular imports
sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))
try:
    from sip_planner import simulate_sip_wealth, allocate_monthly_sip
except ImportError:
    # Embedded fallback for SIP functions if sip_planner.py is not present
    def simulate_sip_wealth(monthly_sip, expected_annual_return, annual_volatility, horizon_years=5, num_simulations=5000, random_seed=42):
        np.random.seed(random_seed)
        total_months = horizon_years * 12
        dt = 1.0 / 12.0
        drift = (expected_annual_return - 0.5 * (annual_volatility ** 2)) * dt
        diffusion = annual_volatility * np.sqrt(dt)
        random_shocks = np.random.normal(0.0, 1.0, size=(total_months, num_simulations))
        growth = np.exp(drift + diffusion * random_shocks)
        wealth = np.zeros((total_months + 1, num_simulations))
        for t in range(total_months):
            wealth[t + 1] = (wealth[t] + monthly_sip) * growth[t]
        final = wealth[-1]
        fd_rate = 0.07 / 12.0
        fd_corpus = sum(monthly_sip * ((1 + fd_rate) ** (total_months - i)) for i in range(total_months))
        timeline = []
        for yr in range(1, horizon_years + 1):
            m = yr * 12
            timeline.append({
                "year": yr,
                "invested_capital": round(monthly_sip * m, 2),
                "worst_case_p10": round(float(np.percentile(wealth[m], 10)), 2),
                "expected_median_p50": round(float(np.percentile(wealth[m], 50)), 2),
                "best_case_p90": round(float(np.percentile(wealth[m], 90)), 2),
            })
        return {
            "total_invested_capital": round(monthly_sip * total_months, 2),
            "median_projected_wealth": round(float(np.percentile(final, 50)), 2),
            "worst_case_wealth_p10": round(float(np.percentile(final, 10)), 2),
            "best_case_wealth_p90": round(float(np.percentile(final, 90)), 2),
            "prob_beat_fd_pct": round(float(np.mean(final > fd_corpus) * 100), 2),
            "growth_timeline": timeline,
        }

    def allocate_monthly_sip(monthly_amount, raw_weights):
        allocation = {}
        rem = monthly_amount
        sorted_w = sorted(raw_weights.items(), key=lambda x: x[1], reverse=True)
        for i, (code, weight) in enumerate(sorted_w):
            if i == len(sorted_w) - 1:
                alloc = rem
            else:
                alloc = max(500.0, round((monthly_amount * weight) / 100.0) * 100.0)
                alloc = min(alloc, rem)
            allocation[code] = alloc
            rem -= alloc
        return allocation


app = FastAPI(
    title="Mutual Fund Recommendation & Optimization API",
    version="1.0.0",
    description="Quantitative fund ranking via LightGBM and Mean-Variance Optimization portfolio engine."
)

PG_PASSWORD = "aakash"

RAW_DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": PG_PASSWORD,
    "host": "localhost",
    "port": 5432,
}

MODEL_FILE = os.path.join(os.path.dirname(__file__), "models", "lgbm_ranker.txt")

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

# --- Pydantic Data Contracts ---

class RecommendRequest(BaseModel):
    investment_amount: float = Field(..., gt=1000.0, description="Capital to allocate in INR (min ₹1,000)")
    risk_profile: Literal["conservative", "moderate", "aggressive"] = Field("aggressive")

class HoldingItem(BaseModel):
    scheme_code: int
    scheme_name: str
    category: str
    target_weight_pct: float
    allocated_capital: float
    allocated_units: float

class PortfolioMetrics(BaseModel):
    expected_annual_return_pct: float
    annual_volatility_pct: float
    expected_sharpe_ratio: float
    cash_leftover_inr: float

class RecommendResponse(BaseModel):
    status: str
    risk_profile: str
    total_capital_inr: float
    allocated_capital_inr: float
    portfolio_holdings: list[HoldingItem]
    metrics: PortfolioMetrics

class SIPRequest(BaseModel):
    monthly_sip_amount: float = Field(..., ge=500.0, description="Monthly installment in INR (min ₹500)")
    horizon_years: int = Field(5, ge=1, le=30, description="Investment horizon in years")
    risk_profile: Literal["conservative", "moderate", "aggressive"] = Field("aggressive")

class SIPHoldingItem(BaseModel):
    scheme_code: int
    scheme_name: str
    category: str
    target_weight_pct: float
    monthly_contribution_inr: float

class SIPTimelineYear(BaseModel):
    year: int
    invested_capital: float
    worst_case_p10: float
    expected_median_p50: float
    best_case_p90: float

class SIPResponse(BaseModel):
    status: str
    risk_profile: str
    monthly_sip_inr: float
    horizon_years: int
    total_invested_capital_inr: float
    projected_median_wealth_inr: float
    worst_case_wealth_p10: float
    best_case_wealth_p90: float
    prob_beat_fd_pct: float
    sip_mandates: list[SIPHoldingItem]
    growth_timeline: list[SIPTimelineYear]


# --- Core Quantitative Helper Functions ---

def get_best_scheme_per_category(target_categories: list[str]) -> list[tuple[int, str, str]]:
    if not os.path.exists(MODEL_FILE):
        raise FileNotFoundError(f"Trained LightGBM model artifact not found at {MODEL_FILE}")

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

    if df.empty:
        return []

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
            best = cat_df.sort_values(by=["is_direct", "rank_score"], ascending=[False, False]).iloc[0]
            selected.append((int(best["scheme_code"]), best["scheme_name"], cat))

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


# --- API Routes ---

@app.get("/health")
def health():
    return {"status": "online", "server_time": datetime.now().isoformat()}


@app.post("/api/v1/recommend", response_model=RecommendResponse)
def get_lump_sum_recommendation(payload: RecommendRequest):
    config = PROFILE_CONFIG.get(payload.risk_profile)
    if not config:
        raise HTTPException(status_code=400, detail="Invalid risk profile specified")

    selected_schemes = get_best_scheme_per_category(config["categories"])
    if not selected_schemes:
        raise HTTPException(status_code=500, detail="No qualifying schemes found for target risk profile")

    scheme_codes = [s[0] for s in selected_schemes]
    meta_lookup = {s[0]: {"name": s[1], "category": s[2]} for s in selected_schemes}

    prices = fetch_price_series(scheme_codes)
    valid_codes = [c for c in scheme_codes if c in prices.columns]
    num_assets = len(valid_codes)

    if num_assets < 2:
        raise HTTPException(status_code=500, detail="Insufficient price history for portfolio optimization")

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
    da = DiscreteAllocation(raw_weights, latest_navs, total_portfolio_value=payload.investment_amount)
    allocation, leftover = da.lp_portfolio()

    holdings = []
    allocated_sum = 0.0
    for code, units in allocation.items():
        w = raw_weights.get(code, 0.0)
        nav = float(latest_navs[code])
        cap = round(units * nav, 2)
        allocated_sum += cap
        holdings.append(HoldingItem(
            scheme_code=code,
            scheme_name=meta_lookup[code]["name"],
            category=meta_lookup[code]["category"],
            target_weight_pct=round(w * 100, 2),
            allocated_capital=cap,
            allocated_units=round(units, 3)
        ))

    holdings.sort(key=lambda x: x.target_weight_pct, reverse=True)

    return RecommendResponse(
        status="success",
        risk_profile=payload.risk_profile,
        total_capital_inr=payload.investment_amount,
        allocated_capital_inr=round(allocated_sum, 2),
        portfolio_holdings=holdings,
        metrics=PortfolioMetrics(
            expected_annual_return_pct=round(perf[0] * 100, 2),
            annual_volatility_pct=round(perf[1] * 100, 2),
            expected_sharpe_ratio=round(perf[2], 2),
            cash_leftover_inr=round(leftover, 2)
        )
    )


@app.post("/api/v1/sip-plan", response_model=SIPResponse)
def get_sip_recommendation(payload: SIPRequest):
    config = PROFILE_CONFIG.get(payload.risk_profile)
    if not config:
        raise HTTPException(status_code=400, detail="Invalid risk profile specified")

    selected_schemes = get_best_scheme_per_category(config["categories"])
    if not selected_schemes:
        raise HTTPException(status_code=500, detail="No qualifying schemes found for target risk profile")

    scheme_codes = [s[0] for s in selected_schemes]
    meta_lookup = {s[0]: {"name": s[1], "category": s[2]} for s in selected_schemes}

    prices = fetch_price_series(scheme_codes)
    valid_codes = [c for c in scheme_codes if c in prices.columns]
    num_assets = len(valid_codes)

    if num_assets < 2:
        raise HTTPException(status_code=500, detail="Insufficient price history for portfolio optimization")

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

    # Calculate AMC-compliant monthly rupee allocations
    sip_splits = allocate_monthly_sip(payload.monthly_sip_amount, raw_weights)

    # Run Monte Carlo simulation across horizon
    mc_sim = simulate_sip_wealth(
        monthly_sip=payload.monthly_sip_amount,
        expected_annual_return=float(perf[0]),
        annual_volatility=float(perf[1]),
        horizon_years=payload.horizon_years,
    )

    mandates = []
    for code, monthly_amt in sip_splits.items():
        if code in meta_lookup:
            mandates.append(SIPHoldingItem(
                scheme_code=code,
                scheme_name=meta_lookup[code]["name"],
                category=meta_lookup[code]["category"],
                target_weight_pct=round(raw_weights.get(code, 0.0) * 100, 2),
                monthly_contribution_inr=round(monthly_amt, 2)
            ))

    mandates.sort(key=lambda x: x.target_weight_pct, reverse=True)

    return SIPResponse(
        status="success",
        risk_profile=payload.risk_profile,
        monthly_sip_inr=payload.monthly_sip_amount,
        horizon_years=payload.horizon_years,
        total_invested_capital_inr=mc_sim["total_invested_capital"],
        projected_median_wealth_inr=mc_sim["median_projected_wealth"],
        worst_case_wealth_p10=mc_sim["worst_case_wealth_p10"],
        best_case_wealth_p90=mc_sim["best_case_wealth_p90"],
        prob_beat_fd_pct=mc_sim["prob_beat_fd_pct"],
        sip_mandates=mandates,
        growth_timeline=[SIPTimelineYear(**t) for t in mc_sim["growth_timeline"]],
    )