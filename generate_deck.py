from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# Color Palette: Deep Navy & Emerald Accent
COLOR_PRIMARY = RGBColor(16, 37, 66)       # Deep Navy
COLOR_SECONDARY = RGBColor(16, 149, 106)   # Emerald Green
COLOR_DARK = RGBColor(30, 41, 59)          # Slate Dark
COLOR_MUTED = RGBColor(100, 116, 139)      # Slate Gray
COLOR_BG_CARD = RGBColor(241, 245, 249)    # Light gray-blue

def add_header(slide, title_text, category_text="MUTUAL FUND QUANTITATIVE PLATFORM"):
    cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.5), Inches(0.35))
    tf_c = cat_box.text_frame
    tf_c.word_wrap = True
    p_c = tf_c.paragraphs[0]
    p_c.text = category_text.upper()
    p_c.font.size = Pt(10)
    p_c.font.bold = True
    p_c.font.color.rgb = COLOR_SECONDARY

    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.5), Inches(0.8))
    tf_t = title_box.text_frame
    tf_t.word_wrap = True
    p_t = tf_t.paragraphs[0]
    p_t.text = title_text
    p_t.font.size = Pt(22)
    p_t.font.bold = True
    p_t.font.color.rgb = COLOR_PRIMARY

def add_bullet(text_frame, title, body):
    p = text_frame.add_paragraph()
    p.font.size = Pt(13)
    p.line_spacing = 1.2
    run1 = p.add_run()
    run1.text = title + ": " if title else ""
    run1.font.bold = True
    run1.font.color.rgb = COLOR_PRIMARY
    run2 = p.add_run()
    run2.text = body
    run2.font.color.rgb = COLOR_DARK

# -------------------------------------------------------------
# SLIDE 1: Title Slide
# -------------------------------------------------------------
s1 = prs.slides.add_slide(prs.slide_layouts[6])
accent = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.2), Inches(0.15), Inches(2.8))
accent.fill.solid()
accent.fill.fore_color.rgb = COLOR_SECONDARY
accent.line.fill.background()

tbox = s1.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(11.0), Inches(2.0))
tf = tbox.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "Quantitative Mutual Fund Recommendation\n& Dynamic Portfolio Optimizer"
p.font.size = Pt(32)
p.font.bold = True
p.font.color.rgb = COLOR_PRIMARY

sub_box = s1.shapes.add_textbox(Inches(1.2), Inches(4.3), Inches(11.0), Inches(1.2))
tf_sub = sub_box.text_frame
p_sub = tf_sub.paragraphs[0]
p_sub.text = "Integrating Multi-Factor Financial Indicators, LambdaMART Ranking, and Markowitz Efficient Frontier"
p_sub.font.size = Pt(15)
p_sub.font.color.rgb = COLOR_MUTED

# -------------------------------------------------------------
# SLIDE 2: Agenda / Outline
# -------------------------------------------------------------
s2 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s2, "Executive Agenda & Roadmap")
agenda_items = [
    ("Problem & Industry Context", "Challenges in retail mutual fund distribution."),
    ("Critical Research Gaps", "Shortcomings of legacy heuristics and naive ML."),
    ("Project Objectives", "End-to-end system and mathematical milestones."),
    ("System Architecture", "Ingestion, feature store, ranking, and optimization layers."),
    ("Algorithmic Methodology", "LambdaMART formulation & Mean-Variance Theory."),
    ("Empirical Results", "Empirical outputs for Conservative, Moderate, and Aggressive profiles."),
]

col_w = Inches(3.6)
card_h = Inches(2.1)
xs = [Inches(0.8), Inches(4.8), Inches(8.8)]
ys = [Inches(1.8), Inches(4.3)]

for i, (head, desc) in enumerate(agenda_items):
    x = xs[i % 3]
    y = ys[i // 3]
    card = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, col_w, card_h)
    card.fill.solid()
    card.fill.fore_color.rgb = COLOR_BG_CARD
    card.line.fill.background()
    ctf = card.text_frame
    ctf.word_wrap = True
    ctf.margin_left = Inches(0.3)
    p0 = ctf.paragraphs[0]
    p0.text = f"0{i+1}"
    p0.font.bold = True
    p0.font.size = Pt(12)
    p0.font.color.rgb = COLOR_SECONDARY
    p1 = ctf.add_paragraph()
    p1.text = head
    p1.font.bold = True
    p1.font.size = Pt(14)
    p1.font.color.rgb = COLOR_PRIMARY
    p2 = ctf.add_paragraph()
    p2.text = desc
    p2.font.size = Pt(11)
    p2.font.color.rgb = COLOR_MUTED

# -------------------------------------------------------------
# SLIDE 3: Problem Statement
# -------------------------------------------------------------
s3 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s3, "Problem Statement & Structural Market Inefficiencies")
probs = [
    ("Scheme Selection Saturation", "The Indian AMFI universe comprises 2,500+ mutual fund schemes. Retail investors face choice paralysis without quantitative tools to distinguish persistent performance from transient luck."),
    ("Misleading Return Metrics", "Distributors frequently highlight 1Y, 3Y, or 5Y absolute trailing returns, ignoring downside volatility, maximum drawdown regimes, and market beta."),
    ("Arbitrary Portfolio Allocation", "Commercial aggregators provide isolated fund recommendations without solving for optimal asset weights, creating unmanaged correlation risks and portfolio bloat."),
]
for i, (title, body) in enumerate(probs):
    y = Inches(1.8 + i * 1.7)
    card = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), y, Inches(11.7), Inches(1.4))
    card.fill.solid()
    card.fill.fore_color.rgb = COLOR_BG_CARD
    card.line.fill.background()
    ctf = card.text_frame
    ctf.word_wrap = True
    ctf.margin_left = Inches(0.4)
    ctf.margin_top = Inches(0.25)
    p0 = ctf.paragraphs[0]
    p0.text = title
    p0.font.bold = True
    p0.font.size = Pt(14)
    p0.font.color.rgb = COLOR_PRIMARY
    p1 = ctf.add_paragraph()
    p1.text = body
    p1.font.size = Pt(12)
    p1.font.color.rgb = COLOR_DARK

# -------------------------------------------------------------
# SLIDE 4: Research Gap
# -------------------------------------------------------------
s4 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s4, "Research Gap in Current Machine Learning Approaches")
gap_cards = [
    ("Flawed Predictive Formulation", "Standard regression/classification models attempt to forecast exact future NAV returns. This approach fails due to high noise-to-signal ratios, regime shifts, and non-stationary financial data."),
    ("Peer Distortion & Category Bias", "Evaluating cross-category funds without intra-class normalization introduces significant bias (e.g., small-cap funds naturally outperforming large-cap funds in bull cycles)."),
    ("Disconnected Allocation Frameworks", "Existing research treats fund ranking and portfolio construction as disconnected silos, omitting the discrete integer allocation needed to produce realistic, actionable share units."),
]
for i, (title, body) in enumerate(gap_cards):
    x = Inches(0.8 + i * 4.0)
    card = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.0), Inches(3.7), Inches(4.5))
    card.fill.solid()
    card.fill.fore_color.rgb = COLOR_BG_CARD
    card.line.fill.background()
    ctf = card.text_frame
    ctf.word_wrap = True
    ctf.margin_left = Inches(0.3)
    ctf.margin_right = Inches(0.3)
    ctf.margin_top = Inches(0.4)
    p0 = ctf.paragraphs[0]
    p0.text = f"GAP {i+1}"
    p0.font.bold = True
    p0.font.size = Pt(11)
    p0.font.color.rgb = COLOR_SECONDARY
    p1 = ctf.add_paragraph()
    p1.text = title
    p1.font.bold = True
    p1.font.size = Pt(14)
    p1.font.color.rgb = COLOR_PRIMARY
    p2 = ctf.add_paragraph()
    p2.text = body
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_DARK

# -------------------------------------------------------------
# SLIDE 5: Objectives
# -------------------------------------------------------------
s5 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s5, "Core Objectives of the System")
box = s5.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.7), Inches(5.0))
tf = box.text_frame
tf.word_wrap = True
objs = [
    ("Automated Time-Series Data Pipelines", "Direct ingestion of historical NAV datasets across active AMFI mutual fund schemes into PostgreSQL."),
    ("Multi-Horizon Factor Modeling", "Computation of key quantitative metrics (Sharpe, Sortino, Jensen's Alpha, Beta, CAGR, and Drawdown) across 1Y and 3Y horizons."),
    ("Intra-Category Learning-to-Rank Engine", "LambdaMART formulation to rank schemes within their respective categories, optimizing NDCG@K."),
    ("Constrained Modern Portfolio Theory", "Markowitz Mean-Variance Optimization paired with Ledoit-Wolf covariance shrinkage to allocate profile-specific weights."),
    ("Production-Ready Microservice", "Sub-second REST API powered by FastAPI, returning discrete allocations and projected risk-return metrics."),
]
for title, body in objs:
    add_bullet(tf, title, body)

# -------------------------------------------------------------
# SLIDE 6: Architecture & Methodology
# -------------------------------------------------------------
s6 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s6, "Methodology & Architecture Pipeline")
steps = [
    ("1. Ingestion Engine", "PostgreSQL database storing raw historical NAV time-series and scheme metadata."),
    ("2. Feature Store", "14 engineered multi-horizon features covering risk, downside, and return ratios."),
    ("3. Ranking Tier", "LightGBM LambdaRank optimizing NDCG to select the top fund per market segment."),
    ("4. MPT Optimizer", "PyPortfolioOpt running quadratic optimization with category exclusivity constraints."),
]
for i, (title, body) in enumerate(steps):
    x = Inches(0.8 + i * 3.0)
    card = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.2), Inches(2.7), Inches(4.0))
    card.fill.solid()
    card.fill.fore_color.rgb = COLOR_BG_CARD
    card.line.fill.background()
    ctf = card.text_frame
    ctf.word_wrap = True
    ctf.margin_left = Inches(0.2)
    ctf.margin_right = Inches(0.2)
    p0 = ctf.paragraphs[0]
    p0.text = title
    p0.font.bold = True
    p0.font.size = Pt(13)
    p0.font.color.rgb = COLOR_PRIMARY
    p1 = ctf.add_paragraph()
    p1.text = body
    p1.font.size = Pt(11)
    p1.font.color.rgb = COLOR_DARK

# -------------------------------------------------------------
# SLIDE 7: Experimental Results & Profile Allocations
# -------------------------------------------------------------
s7 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s7, "Empirical Allocation Results (₹1,00,000 Portfolio)")

rows, cols = 4, 6
table_shape = s7.shapes.add_table(rows, cols, Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.5))
table = table_shape.table

headers = ["Profile", "Fund Count", "Holdings Breakdown", "Exp. Return", "Volatility", "Sharpe"]
for c, h in enumerate(headers):
    cell = table.cell(0, c)
    cell.fill.solid()
    cell.fill.fore_color.rgb = COLOR_PRIMARY
    p = cell.text_frame.paragraphs[0]
    p.text = h
    p.font.bold = True
    p.font.size = Pt(12)
    p.font.color.rgb = RGBColor(255, 255, 255)

data = [
    ["Conservative", "3 Funds", "Equity Savings (47.5%), Aggressive Hybrid (47.5%), Large Cap (5.0%)", "6.02%", "0.91%", "-0.52"],
    ["Moderate", "4 Funds", "Mid Cap (32.5%), Flexi Cap (31.4%), Large Cap (31.2%), Hybrid (5.0%)", "11.69%", "14.37%", "0.36"],
    ["Aggressive", "4 Funds", "Large & Mid (25.6%), Small (25.4%), Mid (25.2%), Flexi (23.8%)", "23.07%", "17.05%", "0.97"],
]

for r, row_data in enumerate(data):
    for c, val in enumerate(row_data):
        cell = table.cell(r + 1, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_BG_CARD if r % 2 == 0 else RGBColor(255, 255, 255)
        p = cell.text_frame.paragraphs[0]
        p.text = val
        p.font.size = Pt(11)
        p.font.color.rgb = COLOR_DARK
        if c == 0:
            p.font.bold = True

# -------------------------------------------------------------
# SLIDE 8: Conclusion & Future Scope
# -------------------------------------------------------------
s8 = prs.slides.add_slide(prs.slide_layouts[6])
add_header(s8, "Conclusion & Future Enhancements")

col1_box = s8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8))
col1_box.fill.solid()
col1_box.fill.fore_color.rgb = COLOR_BG_CARD
col1_box.line.fill.background()
tf1 = col1_box.text_frame
tf1.word_wrap = True
tf1.margin_left = Inches(0.3)
p_title1 = tf1.paragraphs[0]
p_title1.text = "Key Contributions"
p_title1.font.bold = True
p_title1.font.size = Pt(16)
p_title1.font.color.rgb = COLOR_PRIMARY
add_bullet(tf1, "Intra-Category Equity Fairness", "Mitigated broad market cap bias by deploying LambdaMART rankers strictly within sub-category groups.")
add_bullet(tf1, "Near-Zero Unallocated Drag", "Discrete integer optimization deployed ₹99,967+ across portfolios with negligible unallocated cash.")
add_bullet(tf1, "Microservice Deployment", "Exposed FastAPI microservices returning sub-second portfolio allocations.")

col2_box = s8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.9), Inches(1.8), Inches(5.6), Inches(4.8))
col2_box.fill.solid()
col2_box.fill.fore_color.rgb = COLOR_BG_CARD
col2_box.line.fill.background()
tf2 = col2_box.text_frame
tf2.word_wrap = True
tf2.margin_left = Inches(0.3)
p_title2 = tf2.paragraphs[0]
p_title2.text = "Future Scope"
p_title2.font.bold = True
p_title2.font.size = Pt(16)
p_title2.font.color.rgb = COLOR_PRIMARY
add_bullet(tf2, "Tax-Aware Rebalancing", "Integration of LTCG/STCG tax schedules and exit loads into rebalancing optimization.")
add_bullet(tf2, "SIP Simulation & Horizon Modeling", "Extending integer allocation to recurring SIP mandates and goal horizons.")
add_bullet(tf2, "Interactive Dashboard", "React/Streamlit dashboard providing visual wealth projections and automated PDF fact-sheets.")

output_file = "Mutual_Fund_Recommendation_Engine.pptx"
prs.save(output_file)
print(f"Presentation successfully created: {output_file}")