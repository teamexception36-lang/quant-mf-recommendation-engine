\# Quantitative Mutual Fund Recommendation \& Wealth Management Engine



An end-to-end quantitative platform for Indian Mutual Funds that combines machine learning ranking, portfolio risk optimization, and Monte Carlo wealth projections with an interactive web dashboard.



\---



\## System Architecture



\- \*\*Storage \& Ingestion\*\*: PostgreSQL database storing AMFI daily historical NAV records and computing multi-horizon rolling factors (CAGR, Volatility, Sharpe, Sortino, Drawdown, Alpha, Beta).

\- \*\*Quant Ranking\*\*: LightGBM LambdaMART learning-to-rank algorithm to evaluate and select optimal direct-growth schemes across market cap and hybrid categories.

\- \*\*Portfolio Allocation\*\*: Modern Portfolio Theory (Mean-Variance Optimization via PyPortfolioOpt) using Ledoit-Wolf covariance shrinkage and CAPM expected returns, combined with Integer Linear Programming for discrete unit allocation.

\- \*\*Wealth Simulation\*\*: Vectorized Monte Carlo engine based on Geometric Brownian Motion (GBM) providing 10th (worst-case), 50th (median), and 90th percentile wealth bands for monthly SIP mandates.

\- \*\*Interface \& Delivery\*\*: FastAPI REST microservice with an interactive Streamlit frontend.



\---



\## Repository Structure



```text

├── app.py                      # FastAPI microservice (/recommend \& /sip-plan)

├── dashboard.py                # Streamlit interactive visual frontend

├── requirements.txt            # Python dependencies

├── models/

│   └── lgbm\_ranker.txt         # Pre-trained LightGBM LambdaMART ranking model

└── scripts/

&#x20;   ├── ingest\_amfi\_nav.py      # AMFI scheme and master list ingestion

&#x20;   ├── backfill\_history.py     # Historical daily NAV data backfiller

&#x20;   ├── compute\_factors.py      # Rolling risk \& return factor calculator

&#x20;   ├── train\_ranker.py         # LightGBM learning-to-rank training pipeline

&#x20;   ├── portfolio\_optimizer.py  # MPT Sharpe / Min-Vol allocation logic

&#x20;   ├── sip\_planner.py          # Monte Carlo SIP wealth simulation engine

&#x20;   └── live\_nav\_sync.py        # Daily live closing NAV ingestion script

```



\---



\## Quick Start



\### 1. Environment Setup

```bash

git clone \[https://github.com/teamexception36-lang/quant-mf-recommendation-engine.git](https://github.com/teamexception36-lang/quant-mf-recommendation-engine.git)

cd quant-mf-recommendation-engine

python -m venv venv

.\\venv\\Scripts\\Activate.ps1

pip install -r requirements.txt

```



\### 2. Configure Database

Ensure PostgreSQL is running locally with database `mf\_platform`. Update credentials in `RAW\_DB\_CONFIG` inside `app.py` if necessary.



\### 3. Run Backend Microservice

```bash

uvicorn app:app --reload --port 8000

```

Interactive Swagger docs are accessible at `http://127.0.0.1:8000/docs`.



\### 4. Run Frontend Dashboard

In a separate terminal (with virtual environment activated):

```bash

streamlit run dashboard.py

```

Open `http://localhost:8501` to use the interactive application.

