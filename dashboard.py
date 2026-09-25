import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Quant MF Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = "http://127.0.0.1:8000"

st.title("📈 Quantitative Mutual Fund & Wealth Planner")
st.markdown(
    "Automated fund ranking via **LightGBM LambdaMART** paired with "
    "**Markowitz Mean-Variance Optimization** and **Monte Carlo Wealth Simulation**."
)

# Sidebar Configuration
st.sidebar.header("User Investment Profile")

mode = st.sidebar.radio("Investment Mode", ["Lump-Sum Investment", "Monthly SIP Mandate"])

risk_profile = st.sidebar.selectbox(
    "Risk Profile",
    options=["conservative", "moderate", "aggressive"],
    index=2,
    help="Conservative focuses on capital preservation, Moderate targets balanced growth, Aggressive maximizes risk-adjusted alpha.",
)

if mode == "Lump-Sum Investment":
    capital = st.sidebar.number_input(
        "Lump-Sum Capital (INR)",
        min_value=5000.0,
        max_value=10000000.0,
        value=100000.0,
        step=5000.0,
    )
    horizon_years = None
else:
    capital = st.sidebar.number_input(
        "Monthly Installment (INR)",
        min_value=500.0,
        max_value=500000.0,
        value=10000.0,
        step=500.0,
    )
    horizon_years = st.sidebar.slider(
        "Horizon (Years)",
        min_value=1,
        max_value=25,
        value=5,
        step=1,
    )

submit_button = st.sidebar.button("Generate Optimization", use_container_width=True)

# Main Application Logic
if submit_button:
    with st.spinner("Connecting to optimization microservice..."):
        try:
            if mode == "Lump-Sum Investment":
                payload = {
                    "investment_amount": float(capital),
                    "risk_profile": risk_profile,
                }
                res = requests.post(f"{API_BASE_URL}/api/v1/recommend", json=payload, timeout=20)
            else:
                payload = {
                    "monthly_sip_amount": float(capital),
                    "horizon_years": int(horizon_years),
                    "risk_profile": risk_profile,
                }
                res = requests.post(f"{API_BASE_URL}/api/v1/sip-plan", json=payload, timeout=20)

            if res.status_code != 200:
                st.error(f"API Error ({res.status_code}): {res.text}")
            else:
                data = res.json()

                if mode == "Lump-Sum Investment":
                    metrics = data["metrics"]
                    holdings = data["portfolio_holdings"]

                    # Metric KPIs
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Expected CAGR", f"{metrics['expected_annual_return_pct']}%")
                    c2.metric("Annual Volatility", f"{metrics['annual_volatility_pct']}%")
                    c3.metric("Sharpe Ratio", f"{metrics['expected_sharpe_ratio']}")
                    c4.metric("Unallocated Cash", f"₹{metrics['cash_leftover_inr']:,.2f}")

                    st.markdown("---")

                    col_left, col_right = st.columns([1, 1])

                    df_holdings = pd.DataFrame(holdings)

                    with col_left:
                        st.subheader("Asset & Category Distribution")
                        fig_pie = px.pie(
                            df_holdings,
                            values="target_weight_pct",
                            names="category",
                            hole=0.45,
                            color_discrete_sequence=px.colors.qualitative.Prism,
                        )
                        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                        st.plotly_chart(fig_pie, use_container_width=True)

                    with col_right:
                        st.subheader("Executable Discrete Orders")
                        display_df = df_holdings[[
                            "scheme_name", "category", "target_weight_pct", "allocated_units", "allocated_capital"
                        ]].rename(columns={
                            "scheme_name": "Scheme",
                            "category": "Category",
                            "target_weight_pct": "Weight (%)",
                            "allocated_units": "Units",
                            "allocated_capital": "Amount (₹)",
                        })
                        st.dataframe(display_df, use_container_width=True, hide_index=True)

                else:
                    # SIP Mode
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Principal Invested", f"₹{data['total_invested_capital_inr']:,.0f}")
                    c2.metric("Median Wealth (P50)", f"₹{data['projected_median_wealth_inr']:,.0f}")
                    c3.metric("Bullish Case (P90)", f"₹{data['best_case_wealth_p90']:,.0f}")
                    c4.metric("Prob. Beating FD", f"{data['prob_beat_fd_pct']}%")

                    st.markdown("---")

                    timeline_df = pd.DataFrame(data["growth_timeline"])

                    st.subheader(f"Monte Carlo Simulation: {data['horizon_years']}-Year Wealth Trajectory")
                    
                    fig_line = go.Figure()

                    # P10 to P90 Confidence Band
                    fig_line.add_trace(go.Scatter(
                        x=timeline_df["year"],
                        y=timeline_df["best_case_p90"],
                        mode='lines',
                        line=dict(width=0),
                        showlegend=False,
                    ))
                    fig_line.add_trace(go.Scatter(
                        x=timeline_df["year"],
                        y=timeline_df["worst_case_p10"],
                        mode='lines',
                        line=dict(width=0),
                        fill='tonexty',
                        fillcolor='rgba(16, 149, 106, 0.15)',
                        name='10th - 90th Percentile Range',
                    ))

                    # Median Expected Growth
                    fig_line.add_trace(go.Scatter(
                        x=timeline_df["year"],
                        y=timeline_df["expected_median_p50"],
                        mode='lines+markers',
                        name='Median Expected Wealth (P50)',
                        line=dict(color='#10956A', width=3),
                    ))

                    # Cumulative Principal
                    fig_line.add_trace(go.Scatter(
                        x=timeline_df["year"],
                        y=timeline_df["invested_capital"],
                        mode='lines',
                        name='Principal Invested',
                        line=dict(color='#64748B', width=2, dash='dot'),
                    ))

                    fig_line.update_layout(
                        xaxis_title="Investment Horizon (Years)",
                        yaxis_title="Projected Value (INR)",
                        hovermode="x unified",
                        template="plotly_white",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig_line, use_container_width=True)

                    st.subheader("Monthly Scheme SIP Mandates")
                    mandates_df = pd.DataFrame(data["sip_mandates"])[[
                        "scheme_name", "category", "target_weight_pct", "monthly_contribution_inr"
                    ]].rename(columns={
                        "scheme_name": "Scheme",
                        "category": "Category",
                        "target_weight_pct": "Weight (%)",
                        "monthly_contribution_inr": "Monthly SIP (₹)",
                    })
                    st.dataframe(mandates_df, use_container_width=True, hide_index=True)

        except requests.exceptions.ConnectionError:
            st.error("Could not reach the FastAPI server. Ensure Uvicorn is running on port 8000.")
else:
    st.info("Select your parameters in the sidebar and click **Generate Optimization** to run the pipeline.")