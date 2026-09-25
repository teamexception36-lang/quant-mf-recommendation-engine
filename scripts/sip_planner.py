import numpy as np
import pandas as pd

def simulate_sip_wealth(
    monthly_sip: float,
    expected_annual_return: float,
    annual_volatility: float,
    horizon_years: int = 5,
    num_simulations: int = 5000,
    random_seed: int = 42,
) -> dict:
    """
    Simulates wealth paths for a monthly systematic investment plan (SIP)
    using vectorized Geometric Brownian Motion (GBM) under log-normal returns.
    """
    np.random.seed(random_seed)
    
    total_months = horizon_years * 12
    dt = 1.0 / 12.0  # Monthly intervals
    
    # Monthly drift and diffusion parameters
    # Ito's correction: drift = mu - 0.5 * sigma^2
    drift = (expected_annual_return - 0.5 * (annual_volatility ** 2)) * dt
    diffusion = annual_volatility * np.sqrt(dt)
    
    # Generate random monthly shocks (total_months x num_simulations)
    random_shocks = np.random.normal(loc=0.0, scale=1.0, size=(total_months, num_simulations))
    monthly_growth_factors = np.exp(drift + diffusion * random_shocks)
    
    # Track portfolio balance month-by-month across all simulation runs
    wealth_paths = np.zeros((total_months + 1, num_simulations))
    
    for t in range(total_months):
        # Add monthly SIP installment at beginning of month, then apply growth
        wealth_paths[t + 1] = (wealth_paths[t] + monthly_sip) * monthly_growth_factors[t]
        
    final_wealth_distribution = wealth_paths[-1]
    total_invested_capital = monthly_sip * total_months
    
    # Calculate key percentile outcomes
    percentile_10 = np.percentile(final_wealth_distribution, 10)
    percentile_50 = np.percentile(final_wealth_distribution, 50)  # Median
    percentile_90 = np.percentile(final_wealth_distribution, 90)
    
    # Probability of beating bank fixed deposit baseline (e.g. 7.0% compounded)
    fd_monthly_rate = 0.07 / 12.0
    fd_final_corpus = sum(monthly_sip * ((1 + fd_monthly_rate) ** (total_months - i)) for i in range(total_months))
    prob_beat_fd = float(np.mean(final_wealth_distribution > fd_final_corpus) * 100)
    
    # Monthly timeline snapshot for plotting (yearly intervals)
    timeline = []
    for yr in range(1, horizon_years + 1):
        m_idx = yr * 12
        timeline.append({
            "year": yr,
            "invested_capital": round(monthly_sip * m_idx, 2),
            "worst_case_p10": round(float(np.percentile(wealth_paths[m_idx], 10)), 2),
            "expected_median_p50": round(float(np.percentile(wealth_paths[m_idx], 50)), 2),
            "best_case_p90": round(float(np.percentile(wealth_paths[m_idx], 90)), 2),
        })
        
    return {
        "monthly_sip": monthly_sip,
        "horizon_years": horizon_years,
        "total_invested_capital": round(total_invested_capital, 2),
        "median_projected_wealth": round(float(percentile_50), 2),
        "worst_case_wealth_p10": round(float(percentile_10), 2),
        "best_case_wealth_p90": round(float(percentile_90), 2),
        "fd_benchmark_corpus_7pct": round(fd_final_corpus, 2),
        "prob_beat_fd_pct": round(prob_beat_fd, 2),
        "growth_timeline": timeline,
    }


def allocate_monthly_sip(monthly_amount: float, raw_weights: dict) -> dict:
    """
    Rounds SIP scheme contributions into executable monthly mandates
    (multiples of INR 100 or 500) to adhere to AMC rules.
    """
    sip_allocation = {}
    remaining = monthly_amount
    sorted_weights = sorted(raw_weights.items(), key=lambda x: x[1], reverse=True)
    
    for i, (code, weight) in enumerate(sorted_weights):
        if i == len(sorted_weights) - 1:
            allocated = remaining
        else:
            allocated = round((monthly_amount * weight) / 100.0) * 100.0
            allocated = max(500.0, allocated)  # Standard mutual fund minimum SIP
            allocated = min(allocated, remaining)
        
        sip_allocation[code] = allocated
        remaining -= allocated
        
    return sip_allocation


if __name__ == "__main__":
    # Test simulation: INR 15,000 monthly SIP for 5 years on Aggressive profile (mu=23.07%, sigma=17.05%)
    res = simulate_sip_wealth(
        monthly_sip=15000.0,
        expected_annual_return=0.2307,
        annual_volatility=0.1705,
        horizon_years=5,
        num_simulations=5000,
    )
    
    print("\n========================================================")
    print(f"SIP Wealth Projection: INR {res['monthly_sip']:,.2f}/mo | {res['horizon_years']} Years")
    print("========================================================")
    print(f"Total Principal Invested   : INR {res['total_invested_capital']:,.2f}")
    print(f"Worst-Case Outcome (P10)   : INR {res['worst_case_wealth_p10']:,.2f}")
    print(f"Median Expected Wealth     : INR {res['median_projected_wealth']:,.2f}")
    print(f"Bull-Case Outcome (P90)    : INR {res['best_case_wealth_p90']:,.2f}")
    print(f"FD Corpus Benchmark (7.0%) : INR {res['fd_benchmark_corpus_7pct']:,.2f}")
    print(f"Probability of Beating FD  : {res['prob_beat_fd_pct']}%")
    
    print("\n--- Year-by-Year Growth Table ---")
    df = pd.DataFrame(res["growth_timeline"])
    print(df.to_string(index=False))