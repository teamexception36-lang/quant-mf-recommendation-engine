import os
from datetime import datetime
import numpy as np
import pandas as pd
import psycopg
import lightgbm as lgb

PG_PASSWORD = "aakash"

RAW_DB_CONFIG = {
    "dbname": "mf_platform",
    "user": "postgres",
    "password": PG_PASSWORD,
    "host": "localhost",
    "port": 5432,
}

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_FILE = os.path.join(MODEL_DIR, "lgbm_ranker.txt")


def load_dataset():
    print(f"[{datetime.now()}] Loading metrics from database...")
    
    query = """
        SELECT 
            m.scheme_code,
            s.scheme_name,
            s.category_id,
            c.category_name,
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
        raise ValueError("No records found in scheme_metrics table matching criteria.")

    metric_cols = [
        "cagr", "annualized_volatility", "sharpe_ratio",
        "sortino_ratio", "max_drawdown", "beta", "alpha"
    ]
    
    # Ensure numeric types
    for col in metric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df_1y = df[df["window_years"] == 1].copy()
    df_3y = df[df["window_years"] == 3].copy()

    merged = pd.merge(
        df_1y[["scheme_code", "scheme_name", "category_id", "category_name", "sub_category_name"] + metric_cols],
        df_3y[["scheme_code"] + metric_cols],
        on="scheme_code",
        suffixes=("_1y", "_3y"),
        how="inner"
    )

    return merged


def generate_relevance_labels(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["raw_composite_score"] = (
        0.35 * df["sharpe_ratio_3y"].fillna(0) +
        0.25 * df["sortino_ratio_3y"].fillna(0) +
        0.15 * df["alpha_3y"].fillna(0) +
        0.15 * df["sharpe_ratio_1y"].fillna(0) +
        0.10 * df["cagr_3y"].fillna(0) -
        0.10 * df["annualized_volatility_3y"].fillna(0) -
        0.05 * df["max_drawdown_3y"].abs().fillna(0)
    )

    def assign_tiers(group):
        if len(group) < 4:
            return pd.Series(2, index=group.index)
        ranks = group["raw_composite_score"].rank(pct=True, method="first")
        return pd.cut(ranks, bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0], labels=[0, 1, 2, 3, 4], include_lowest=True)

    df["relevance"] = df.groupby("category_id", group_keys=False).apply(assign_tiers).astype(int)
    return df


def train_lgbm_ranker():
    df = load_dataset()
    print(f"[{datetime.now()}] Found {len(df)} Growth schemes with both 1Y & 3Y metrics.")

    df = generate_relevance_labels(df)

    category_counts = df["category_id"].value_counts()
    valid_categories = category_counts[category_counts >= 4].index
    df = df[df["category_id"].isin(valid_categories)].copy()

    df = df.sort_values(by=["category_id", "raw_composite_score"], ascending=[True, False]).reset_index(drop=True)

    feature_cols = [
        "cagr_1y", "annualized_volatility_1y", "sharpe_ratio_1y", "sortino_ratio_1y", "max_drawdown_1y", "beta_1y", "alpha_1y",
        "cagr_3y", "annualized_volatility_3y", "sharpe_ratio_3y", "sortino_ratio_3y", "max_drawdown_3y", "beta_3y", "alpha_3y"
    ]

    X = df[feature_cols]
    y = df["relevance"]
    groups = df.groupby("category_id", sort=False).size().to_numpy()

    print(f"[{datetime.now()}] Configured {len(groups)} distinct categories for LambdaMART training.")

    train_data = lgb.Dataset(X, label=y, group=groups)

    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": [1, 3, 5],
        "learning_rate": 0.03,
        "num_leaves": 31,
        "min_child_samples": 3,
        "max_depth": 5,
        "boosting_type": "gbdt",
        "verbosity": -1,
        "random_state": 42,
    }

    print(f"[{datetime.now()}] Training LightGBM LambdaMART ranker...")
    booster = lgb.train(
        params,
        train_data,
        num_boost_round=150,
    )

    booster.save_model(MODEL_FILE)
    print(f"[{datetime.now()}] Saved optimized model to: {MODEL_FILE}")

    # Predict ranking score
    df["rank_score"] = booster.predict(X)
    df["category_rank"] = df.groupby("category_id")["rank_score"].rank(ascending=False, method="first").astype(int)

    top_picks = df[df["category_rank"] <= 2][
        ["scheme_code", "scheme_name", "sub_category_name", "category_rank", "rank_score", "sharpe_ratio_3y", "cagr_3y"]
    ]

    print("\n--- Top Ranked Funds per Category (Sample) ---")
    print(top_picks.head(20).to_string(index=False))


if __name__ == "__main__":
    train_lgbm_ranker()