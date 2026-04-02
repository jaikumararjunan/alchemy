import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.patheffects as pe
import numpy as np

# ── Color Palette ──────────────────────────────────────────────────────────────
C = dict(
    navy="#1B3A5C", blue="#2E75B6", sky="#5B9BD5", teal="#00B0F0",
    green="#4CAF50", amber="#FFC107", red="#E53935", purple="#7B1FA2",
    orange="#FF6D00", gray="#607D8B", lightblue="#E3F2FD", lightgreen="#E8F5E9",
    lightyellow="#FFFDE7", lightgray="#F5F5F5", white="#FFFFFF",
    darkgray="#424242", border="#90CAF9", heading="#0D47A1"
)

def save(fig, path, dpi=160):
    fig.savefig(path, dpi=dpi, bbox_inches='tight',
                facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    print(f"Saved: {path}")

def box(ax, x, y, w, h, fill, edge, label, sublabel=None,
        fontsize=9, bold=True, radius=0.3, lw=1.5, label_color="white"):
    r = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       facecolor=fill, edgecolor=edge, linewidth=lw, zorder=2)
    ax.add_patch(r)
    cy = y + h / 2 + (0.12 if sublabel else 0)
    ax.text(x + w/2, cy, label, ha='center', va='center',
            fontsize=fontsize, fontweight='bold' if bold else 'normal',
            color=label_color, zorder=3, wrap=True)
    if sublabel:
        ax.text(x + w/2, y + h/2 - 0.14, sublabel, ha='center', va='center',
                fontsize=7, color=label_color, alpha=0.9, zorder=3)

def arrow(ax, x1, y1, x2, y2, color="#455A64", label="", lw=1.5, style="-|>"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"))
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx+0.05, my, label, fontsize=6.5, color=color, va='center')

# ══════════════════════════════════════════════════════════════════════════════
# 1. SYSTEM CONTEXT DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════
def diagram_system_context():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16); ax.set_ylim(0, 10)
    ax.axis('off')
    fig.patch.set_facecolor(C['lightblue'])

    ax.text(8, 9.5, "ALCHEMY PLATFORM — System Context Diagram",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])
    ax.text(8, 9.2, "UML C4 Level 1 | QuantInsti Repository Ecosystem Integration",
            ha='center', fontsize=9, color=C['gray'])

    # Central system
    box(ax, 5.5, 3.8, 5, 2.8, C['navy'], C['teal'],
        "ALCHEMY PLATFORM", "AI-Powered Algorithmic Trading Product",
        fontsize=12, radius=0.4, lw=2.5)

    # External actors (top)
    box(ax, 0.3, 7.5, 2.8, 1.0, C['purple'], C['purple'],
        "Quant Analyst", "Strategy Designer", fontsize=8, radius=0.2)
    box(ax, 6.6, 7.5, 2.8, 1.0, C['purple'], C['purple'],
        "Portfolio Manager", "Risk Oversight", fontsize=8, radius=0.2)
    box(ax, 12.9, 7.5, 2.8, 1.0, C['purple'], C['purple'],
        "Algo Trader", "Live Execution", fontsize=8, radius=0.2)

    # External systems (bottom)
    box(ax, 0.2, 0.4, 3.0, 1.2, C['green'], C['green'],
        "Interactive Brokers", "Execution Broker\n(ib-controller)", fontsize=8, radius=0.2)
    box(ax, 4.0, 0.4, 3.0, 1.2, C['green'], C['green'],
        "Zerodha Kite", "Indian Markets\n(kiteconnect3)", fontsize=8, radius=0.2)
    box(ax, 8.0, 0.4, 3.0, 1.2, C['orange'], C['orange'],
        "LLM Providers", "Claude/GPT/Gemini\n(litellm gateway)", fontsize=8, radius=0.2)
    box(ax, 12.0, 0.4, 3.5, 1.2, C['blue'], C['blue'],
        "Blueshift Platform", "Backtesting Engine\n(blueshift-dev-kit)", fontsize=8, radius=0.2)

    # QuantInsti repos group
    box(ax, 12.5, 3.5, 3.0, 3.5, C['sky'], C['blue'],
        "QuantInsti\nLibraries", "pyfolio · arch\nzipline-pipeline\nquantrautil\nml-trading-book",
        fontsize=8, radius=0.3)

    # Arrows: users → Alchemy
    arrow(ax, 1.7, 7.5, 6.0, 6.6, C['purple'], "Designs Strategy")
    arrow(ax, 8.0, 7.5, 8.5, 6.6, C['purple'], "Monitors Risk")
    arrow(ax, 14.3, 7.5, 10.5, 6.6, C['purple'], "Executes Live")

    # Arrows: Alchemy → external
    arrow(ax, 6.5, 3.8, 1.7, 1.6, C['green'], "Orders / Status")
    arrow(ax, 7.5, 3.8, 5.5, 1.6, C['green'], "NSE Orders")
    arrow(ax, 8.5, 3.8, 9.5, 1.6, C['orange'], "AI Inference")
    arrow(ax, 9.8, 4.2, 12.0, 3.8, C['blue'], "Backtest Jobs")

    # Arrows: QuantInsti → Alchemy
    arrow(ax, 12.5, 5.2, 10.5, 5.2, C['blue'], "Analytics / Models")

    save(fig, "/home/claude/uml_diagrams/01_system_context.png")

# ══════════════════════════════════════════════════════════════════════════════
# 2. COMPONENT ARCHITECTURE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════
def diagram_component_architecture():
    fig, ax = plt.subplots(figsize=(18, 13))
    ax.set_xlim(0, 18); ax.set_ylim(0, 13)
    ax.axis('off')
    fig.patch.set_facecolor("#F8FBFF")

    ax.text(9, 12.6, "ALCHEMY PLATFORM — Component Architecture Diagram",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])
    ax.text(9, 12.3, "UML C4 Level 2 | Module Decomposition & QuantInsti Library Mapping",
            ha='center', fontsize=9, color=C['gray'])

    # Layer labels
    layers = [
        (0.1, 10.4, 1.8, "PRESENTATION\nLAYER", C['purple']),
        (0.1, 7.8,  1.8, "AI AGENT\nLAYER", C['orange']),
        (0.1, 5.4,  1.8, "STRATEGY\nLAYER", C['blue']),
        (0.1, 3.0,  1.8, "ANALYTICS\nLAYER", C['green']),
        (0.1, 1.0,  1.8, "EXECUTION\nLAYER", C['red']),
    ]
    for (x, y, h, lbl, col) in layers:
        r = FancyBboxPatch((x, y), 1.6, h,
                           boxstyle="round,pad=0,rounding_size=0.2",
                           facecolor=col, edgecolor=col, linewidth=1, alpha=0.85, zorder=2)
        ax.add_patch(r)
        ax.text(x+0.8, y+h/2, lbl, ha='center', va='center', fontsize=7.5,
                fontweight='bold', color='white', zorder=3)

    # ── Presentation Layer ──────────────────────────────────────────
    box(ax, 2.2, 10.8, 3.2, 1.0, C['purple'], "#4A148C",
        "React Dashboard", "Portfolio Monitor", 8, radius=0.25)
    box(ax, 5.8, 10.8, 3.2, 1.0, C['purple'], "#4A148C",
        "Strategy Builder UI", "Dify Visual Workflow", 8, radius=0.25)
    box(ax, 9.4, 10.8, 3.2, 1.0, "#7B1FA2", "#4A148C",
        "Risk Monitor", "Real-time Alerts", 8, radius=0.25)
    box(ax, 13.0, 10.8, 4.5, 1.0, "#9C27B0", "#4A148C",
        "Report Engine", "pyfolio Tear Sheets", 8, radius=0.25)

    # ── AI Agent Layer ──────────────────────────────────────────────
    box(ax, 2.2, 8.2, 2.8, 1.0, C['orange'], "#E65100",
        "LiteLLM Gateway", "100+ LLM Providers", 8, radius=0.25)
    box(ax, 5.4, 8.2, 3.0, 1.0, "#FF6D00", "#E65100",
        "LangGraph Engine", "Multi-Agent Orchestration", 8, radius=0.25)
    box(ax, 8.8, 8.2, 2.8, 1.0, "#FF6D00", "#E65100",
        "Sentiment Agent", "News + FinBERT", 8, radius=0.25)
    box(ax, 12.0, 8.2, 2.5, 1.0, "#FF8F00", "#E65100",
        "Decision Agent", "Signal Generator", 8, radius=0.25)
    box(ax, 14.9, 8.2, 2.7, 1.0, "#FF8F00", "#E65100",
        "MCP Server", "IB/Kite Tools", 8, radius=0.25)

    # ── Strategy Layer ──────────────────────────────────────────────
    box(ax, 2.2, 5.8, 3.0, 1.0, C['blue'], "#0D47A1",
        "Blueshift Engine", "Strategy Execution", 8, radius=0.25)
    box(ax, 5.6, 5.8, 3.0, 1.0, C['sky'], "#0D47A1",
        "Zipline Pipeline", "Factor Screening", 8, radius=0.25)
    box(ax, 9.0, 5.8, 3.2, 1.0, C['sky'], "#0D47A1",
        "Strategy Library", "Demo Strategies", 8, radius=0.25)
    box(ax, 12.6, 5.8, 5.0, 1.0, "#1565C0", "#0D47A1",
        "ML Strategy Engine", "RandomForest / LSTM / XGBoost", 8, radius=0.25)

    # ── Analytics Layer ──────────────────────────────────────────────
    box(ax, 2.2, 3.4, 3.2, 1.0, C['green'], "#1B5E20",
        "pyfolio Analytics", "Tear Sheets / Metrics", 8, radius=0.25)
    box(ax, 5.8, 3.4, 3.0, 1.0, "#388E3C", "#1B5E20",
        "ARCH Volatility", "GARCH / EGARCH", 8, radius=0.25)
    box(ax, 9.2, 3.4, 3.0, 1.0, "#388E3C", "#1B5E20",
        "quantrautil", "Data Fetching NSE/US", 8, radius=0.25)
    box(ax, 12.6, 3.4, 5.0, 1.0, "#2E7D32", "#1B5E20",
        "TimescaleDB / Redis", "Time-Series Store + Cache", 8, radius=0.25)

    # ── Execution Layer ──────────────────────────────────────────────
    box(ax, 2.2, 1.2, 3.0, 1.0, C['red'], "#B71C1C",
        "IB Gateway", "ib-controller (Java)", 8, radius=0.25)
    box(ax, 5.6, 1.2, 3.0, 1.0, "#C62828", "#B71C1C",
        "Kite Connect", "Zerodha NSE/BSE", 8, radius=0.25)
    box(ax, 9.0, 1.2, 3.2, 1.0, "#C62828", "#B71C1C",
        "Risk Manager", "Max DD / Position Limits", 8, radius=0.25)
    box(ax, 12.6, 1.2, 5.0, 1.0, "#D32F2F", "#B71C1C",
        "Cloud Deploy", "trading-from-cloud / AWS", 8, radius=0.25)

    # Inter-layer arrows (simplified)
    for x in [3.6, 7.0, 10.4, 14.3]:
        arrow(ax, x, 10.8, x, 9.2, "#757575", lw=1.2)
    for x in [3.6, 7.0, 10.4, 13.5]:
        arrow(ax, x, 8.2, x, 6.8, "#757575", lw=1.2)
    for x in [3.6, 7.0, 10.4, 14.5]:
        arrow(ax, x, 5.8, x, 4.4, "#757575", lw=1.2)
    for x in [3.6, 7.0, 10.4, 14.5]:
        arrow(ax, x, 3.4, x, 2.2, "#757575", lw=1.2)

    save(fig, "/home/claude/uml_diagrams/02_component_architecture.png")

# ══════════════════════════════════════════════════════════════════════════════
# 3. SEQUENCE DIAGRAM — AI Trading Agent Workflow
# ══════════════════════════════════════════════════════════════════════════════
def diagram_sequence():
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.set_xlim(0, 18); ax.set_ylim(0, 12)
    ax.axis('off')
    fig.patch.set_facecolor("#FAFAFA")

    ax.text(9, 11.6, "ALCHEMY PLATFORM — AI Trading Agent Sequence Diagram",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])
    ax.text(9, 11.3, "UML Sequence | End-to-End Trade Lifecycle with LangGraph + LiteLLM",
            ha='center', fontsize=9, color=C['gray'])

    participants = [
        (1.2, "Trader\nUI", C['purple']),
        (3.5, "LangGraph\nOrchestrator", C['orange']),
        (6.0, "LiteLLM\nGateway", C['amber']),
        (8.3, "Sentiment\nAgent", C['sky']),
        (10.6, "Volatility\n(ARCH)", C['green']),
        (12.9, "Decision\nAgent", C['blue']),
        (15.2, "Execution\nLayer", C['red']),
    ]

    # Draw lifeline boxes
    for (x, label, color) in participants:
        box(ax, x-0.7, 10.5, 1.4, 0.8, color, color, label, fontsize=7.5, radius=0.15)
        ax.plot([x, x], [10.5, 0.3], color='#BDBDBD', lw=1, linestyle='--', zorder=1)

    def seq_arrow(x1, x2, y, label, color="#455A64", ret=False):
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(
                        arrowstyle="<|-" if ret else "-|>",
                        color=color, lw=1.5,
                        linestyle=("dashed" if ret else "solid")))
        mx = (x1+x2)/2
        ax.text(mx, y+0.08, label, ha='center', fontsize=7, color=color)

    def act_box(x, y, h, color):
        r = FancyBboxPatch((x-0.08, y-h), 0.16, h,
                           boxstyle="square,pad=0", facecolor=color,
                           edgecolor='white', linewidth=0.5, alpha=0.9, zorder=2)
        ax.add_patch(r)

    # Message sequence
    msgs = [
        (1.2,  3.5,  10.0, "initiate_trade('RELIANCE')", C['purple'], False),
        (3.5,  8.3,   9.4, "fetch_news(ticker)", C['orange'], False),
        (8.3,  6.0,   8.8, "llm.complete(news_prompt)", C['sky'], False),
        (6.0,  8.3,   8.2, "sentiment_score=0.72", C['amber'], True),
        (3.5,  10.6,  7.6, "compute_garch_vol(returns)", C['orange'], False),
        (10.6, 3.5,   7.0, "annualized_vol=0.24", C['green'], True),
        (3.5,  12.9,  6.4, "decide(sentiment, vol)", C['orange'], False),
        (12.9,  6.0,  5.8, "llm.complete(decision_prompt)", C['blue'], False),
        (6.0, 12.9,   5.2, "signal=BUY, size=5%", C['amber'], True),
        (12.9,  3.5,  4.6, "TradingState.signal=BUY", C['blue'], True),
        (3.5,  15.2,  4.0, "place_order(RELIANCE, BUY, 5%)", C['orange'], False),
        (15.2,  3.5,  3.4, "order_id=IB#98765", C['red'], True),
        (3.5,   1.2,  2.8, "trade_confirmed(order_id)", C['orange'], True),
        (1.2,   3.5,  2.2, "update_risk_limits()", C['purple'], False),
        (3.5,  10.6,  1.6, "log_metrics(pyfolio)", C['orange'], False),
    ]
    for (x1, x2, y, label, color, ret) in msgs:
        seq_arrow(x1, x2, y, label, color, ret)

    # Activation boxes
    act_box(3.5,  10.0, 8.5, C['orange'])
    act_box(8.3,   9.4, 1.5, C['sky'])
    act_box(10.6,  7.6, 0.9, C['green'])
    act_box(12.9,  6.4, 1.8, C['blue'])
    act_box(15.2,  4.0, 0.8, C['red'])

    save(fig, "/home/claude/uml_diagrams/03_sequence_diagram.png")

# ══════════════════════════════════════════════════════════════════════════════
# 4. CLASS DIAGRAM — Core Integration Classes
# ══════════════════════════════════════════════════════════════════════════════
def diagram_class():
    fig, ax = plt.subplots(figsize=(18, 13))
    ax.set_xlim(0, 18); ax.set_ylim(0, 13)
    ax.axis('off')
    fig.patch.set_facecolor("#FAFAFA")

    ax.text(9, 12.6, "ALCHEMY PLATFORM — Class Diagram (Core Integration Classes)",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])
    ax.text(9, 12.3, "UML Class Diagram | Key Classes from QuantInsti Libraries",
            ha='center', fontsize=9, color=C['gray'])

    def cls_box(ax, x, y, w, title, attrs, methods, title_color, border_color):
        total_lines = 1 + len(attrs) + 1 + len(methods)
        lh = 0.28
        h = lh * total_lines + 0.4
        # border
        r = FancyBboxPatch((x, y-h), w, h, boxstyle="square,pad=0",
                           facecolor='white', edgecolor=border_color, linewidth=1.5, zorder=2)
        ax.add_patch(r)
        # title bar
        r2 = FancyBboxPatch((x, y-lh-0.15), w, lh+0.15,
                            boxstyle="square,pad=0",
                            facecolor=title_color, edgecolor=border_color, linewidth=1.5, zorder=3)
        ax.add_patch(r2)
        ax.text(x+w/2, y-lh/2-0.07, title, ha='center', va='center',
                fontsize=7.5, fontweight='bold', color='white', zorder=4)
        # separator after attrs
        sep_y = y - lh - 0.15 - lh * len(attrs) - 0.05
        ax.plot([x, x+w], [sep_y, sep_y], color=border_color, lw=0.8, zorder=3)
        # attrs
        for i, attr in enumerate(attrs):
            ay = y - lh - 0.15 - lh*(i+0.5) - 0.02
            ax.text(x+0.08, ay, f"  {attr}", ha='left', va='center',
                    fontsize=6.5, color=C['darkgray'], family='monospace', zorder=3)
        # methods
        for i, meth in enumerate(methods):
            my = sep_y - lh*(i+0.5) - 0.02
            ax.text(x+0.08, my, f"  {meth}", ha='left', va='center',
                    fontsize=6.5, color=C['navy'], family='monospace', zorder=3)
        return y - h  # bottom y

    # AlchemyTradingState
    cls_box(ax, 0.3, 12.0, 4.0, "AlchemyTradingState",
        ["+ ticker: str", "+ price_data: dict", "+ news_headlines: list[str]",
         "+ sentiment: float", "+ volatility: float"],
        ["+ to_dict() → dict", "+ validate() → bool"],
        C['orange'], "#E65100")

    # AlchemyLLMRouter
    cls_box(ax, 5.1, 12.0, 4.2, "AlchemyLLMRouter",
        ["- primary_model: str", "- fallback_model: str", "- budget_manager"],
        ["+ analyze_signal(data) → dict", "+ set_budget(amount: float)",
         "+ async acompletion(msg) → str"],
        C['amber'], "#F57F17")

    # AlchemyStrategyBase  (abstract)
    cls_box(ax, 10.0, 12.0, 4.2, "«abstract» AlchemyStrategyBase",
        ["# context: BlueshiftContext", "# params: dict", "# universe: list"],
        ["+ initialize(ctx) → None", "+ handle_data(ctx, data) → None",
         "# rebalance(ctx, data) → None"],
        C['blue'], "#0D47A1")

    # VolatilityEngine
    cls_box(ax, 0.3, 8.5, 3.8, "VolatilityEngine",
        ["- model: ARCHModel", "- last_fit: ARCHModelResult"],
        ["+ fit(returns: Series) → self",
         "+ forecast_vol(horizon=1) → float",
         "+ get_cond_vol() → Series"],
        C['green'], "#1B5E20")

    # PortfolioAnalytics
    cls_box(ax, 4.5, 8.5, 4.0, "PortfolioAnalytics",
        ["- returns: pd.Series", "- positions: pd.DataFrame",
         "- transactions: pd.DataFrame"],
        ["+ create_tear_sheet() → Figure",
         "+ sharpe_ratio() → float",
         "+ max_drawdown() → float",
         "+ calmar_ratio() → float"],
        C['teal'], "#006064")

    # PipelineScreen
    cls_box(ax, 9.0, 8.5, 4.2, "PipelineScreen",
        ["- engine: SimplePipelineEngine",
         "- domain: NSEDomain", "- universe_size: int"],
        ["+ build_pipeline() → Pipeline",
         "+ run_screen(start, end) → DataFrame",
         "+ get_factors() → dict"],
        C['sky'], "#01579B")

    # LiveTradingBot
    cls_box(ax, 13.6, 8.5, 4.0, "LiveTradingBot",
        ["- ib: IB | kite: KiteConnect",
         "- max_position: float",
         "- max_drawdown: float"],
        ["+ connect() → None",
         "+ place_order(ticker, qty, side)",
         "+ check_risk() → bool",
         "+ emergency_close()"],
        C['red'], "#B71C1C")

    # AlchemyAgent (inherits AlchemyTradingState + uses others)
    cls_box(ax, 4.0, 5.2, 4.5, "AlchemyTradingAgent",
        ["- graph: CompiledGraph",
         "- state: AlchemyTradingState",
         "- vol_engine: VolatilityEngine"],
        ["+ build_graph() → CompiledGraph",
         "+ run(ticker) → TradingSignal",
         "+ sentiment_node(state) → state",
         "+ decision_node(state) → state"],
        C['orange'], "#BF360C")

    # DataFetcher
    cls_box(ax, 9.5, 5.2, 4.0, "DataFetcher",
        ["- source: str  # NSE/BSE/US", "- cache: Redis"],
        ["+ fetch_ohlcv(sym, start, end) → df",
         "+ fetch_returns(sym) → Series",
         "+ stream_tick(sym) → Generator"],
        C['gray'], "#37474F")

    # Relationships / arrows
    def rel(x1, y1, x2, y2, dashed=True, label="", color="#455A64"):
        style = dict(arrowstyle="-|>", color=color, lw=1.2,
                     connectionstyle="arc3,rad=0.05",
                     linestyle="dashed" if dashed else "solid")
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=style)
        if label:
            ax.text((x1+x2)/2+0.1, (y1+y2)/2, label, fontsize=6, color=color)

    rel(6.2, 12.0, 10.0, 12.0, True,  "<<uses>>", C['gray'])
    rel(5.6, 12.0, 4.2, 8.5,   False, "<<uses>>", C['gray'])
    rel(7.1, 8.5,  6.5, 12.0,  True,  "<<returns>>", C['gray'])
    rel(6.2, 5.2,  2.1, 8.5,   True,  "<<uses>>", C['green'])
    rel(6.2, 5.2,  5.1, 12.0,  True,  "<<uses>>", C['orange'])
    rel(8.5, 5.2,  9.0, 8.5,   True,  "<<queries>>", C['sky'])
    rel(11.5, 5.2, 13.6, 8.5,  True,  "<<triggers>>", C['red'])
    rel(11.5, 5.2, 9.5, 5.2,   True,  "<<fetches>>", C['gray'])

    save(fig, "/home/claude/uml_diagrams/04_class_diagram.png")

# ══════════════════════════════════════════════════════════════════════════════
# 5. MODULE-WISE INTEGRATION ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
def diagram_integration():
    fig, ax = plt.subplots(figsize=(18, 13))
    ax.set_xlim(0, 18); ax.set_ylim(0, 13)
    ax.axis('off')
    fig.patch.set_facecolor("#F1F8E9")

    ax.text(9, 12.6, "ALCHEMY — Module-wise Integration Architecture",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])
    ax.text(9, 12.3, "QuantInsti Repository → Alchemy Module Mapping",
            ha='center', fontsize=9, color=C['gray'])

    # Headers
    headers = ["QuantInsti\nRepository", "Alchemy\nModule", "Integration\nPattern",
               "Key APIs / Classes", "Alchemy\nBenefit"]
    col_x = [0.2, 3.5, 6.8, 10.0, 15.0]
    col_w = [3.1, 3.1, 3.0, 4.8, 2.8]
    
    for i, (hdr, x, w) in enumerate(zip(headers, col_x, col_w)):
        box(ax, x, 11.5, w, 0.7, C['navy'], C['teal'], hdr, fontsize=8, radius=0.15)

    # Rows
    rows = [
        ("blueshift-developer-kit\n(Mar 2026)", "Strategy Factory\nModule",
         "Direct Library\nIntegration",
         "BlueshiftStubs, LLMGuide,\nVSCode Snippets, PyrightConfig",
         "AI Strategy\nGeneration"),
        ("AI-in-Trading-Workflow\n(Jan 2026)", "AI Agent\nOrchestrator",
         "Fork & Adapt\nLangGraph Graph",
         "TradingState, build_graph(),\nsentiment_node(), MCP Server",
         "Autonomous\nTrading"),
        ("blueshift-demo-strategies\n(173 ★)", "Strategy\nTemplate Library",
         "Template\nImport + Extend",
         "initialize(), handle_data(),\norder_target_percent()",
         "Rapid Strategy\nPrototyping"),
        ("zipline-pipeline\n(Oct 2025)", "Universe Screen\n& Factor Engine",
         "Subclass Core\nAbstractions",
         "Domain, DataSet, Pipeline,\nSimplePipelineEngine",
         "Factor-Based\nSignals"),
        ("pyfolio\n(Quantopian fork)", "Performance\nAnalytics Module",
         "Direct pip Install\n+ API Calls",
         "create_full_tear_sheet(),\ntimeseries.*_ratio()",
         "Institutional\nReporting"),
        ("arch\n(GARCH Library)", "Volatility\nForecasting Module",
         "Service Wrapper\nPattern",
         "arch_model(), GARCH, EGARCH,\nforecast(), conditional_volatility",
         "Real-time Vol\nSurface"),
        ("litellm\n(LLM Gateway fork)", "LLM Router\nModule",
         "Proxy Server\n+ SDK",
         "completion(), acompletion(),\nBudgetManager, fallbacks=[]",
         "Provider-Agnostic\nAI Calls"),
        ("quantrautil\n(Data Fetcher)", "Market Data\nAdapter",
         "Adapter Pattern\nWrapper",
         "get_data(), get_nse_data(),\nget_bse_data()",
         "Multi-Market\nData Access"),
        ("ib-controller\n(Java)", "Execution\nGateway — IB",
         "Process Mgmt\nJava Bridge",
         "IBController.ini, TWS API,\nic_insync.IB",
         "US Market\nExecution"),
        ("kiteconnect3\n(R → Python)", "Execution\nGateway — INR",
         "Pattern Port\nto Python SDK",
         "KiteConnect, place_order(),\nMIS/CNC products",
         "Indian Market\nExecution"),
    ]

    fill_colors = [C['lightblue'], "#FFF3E0", C['lightblue'], "#FFF3E0",
                   C['lightblue'], "#FFF3E0", C['lightblue'], "#FFF3E0",
                   C['lightblue'], "#FFF3E0"]
    row_colors = [C['blue'], C['orange'], C['sky'], C['blue'],
                  C['green'], C['green'], C['amber'], C['gray'],
                  C['red'], C['red']]

    for i, (row, fill, rc) in enumerate(zip(rows, fill_colors, row_colors)):
        y = 11.0 - i * 1.0
        for j, (val, x, w) in enumerate(zip(row, col_x, col_w)):
            fc = rc if j == 0 else fill
            tc = "white" if j == 0 else C['darkgray']
            border = rc if j == 0 else "#BDBDBD"
            r = FancyBboxPatch((x, y-0.9), w, 0.88,
                               boxstyle="square,pad=0",
                               facecolor=fc, edgecolor=border, linewidth=0.8, zorder=2)
            ax.add_patch(r)
            ax.text(x + w/2, y - 0.46, val, ha='center', va='center',
                    fontsize=6.8, color=tc, fontweight='bold' if j == 0 else 'normal',
                    zorder=3)

    save(fig, "/home/claude/uml_diagrams/05_integration_architecture.png")

# ══════════════════════════════════════════════════════════════════════════════
# 6. MIGRATION ROADMAP
# ══════════════════════════════════════════════════════════════════════════════
def diagram_migration():
    fig, ax = plt.subplots(figsize=(18, 10))
    ax.set_xlim(0, 18); ax.set_ylim(0, 10)
    ax.axis('off')
    fig.patch.set_facecolor("#ECEFF1")

    ax.text(9, 9.6, "ALCHEMY PLATFORM — Migration Roadmap",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])
    ax.text(9, 9.3, "Phased Migration from Legacy System → Alchemy + QuantInsti Stack",
            ha='center', fontsize=9, color=C['gray'])

    phases = [
        ("Phase 1\nFoundation\nWeek 1–2", C['blue'], [
            "Install: pyfolio, arch,",
            "litellm, langgraph",
            "Set up LiteLLM proxy",
            "Blueshift stubs install",
            "Base project scaffold",
        ]),
        ("Phase 2\nStrategy\nWeek 3–4", C['sky'], [
            "Port blueshift-demo-strategies",
            "Integrate zipline-pipeline",
            "GARCH volatility service",
            "Factor universe screen",
            "Strategy unit tests",
        ]),
        ("Phase 3\nAI Agents\nWeek 5–6", C['orange'], [
            "LangGraph multi-agent",
            "LiteLLM routing setup",
            "Sentiment agent (FinBERT)",
            "MCP server for IB API",
            "End-to-end agent test",
        ]),
        ("Phase 4\nLive Trading\nWeek 7–8", C['red'], [
            "ib-controller deploy",
            "Kite Connect NSE live",
            "Risk manager module",
            "Cloud (AWS EC2) setup",
            "Paper trading validation",
        ]),
        ("Phase 5\nMonitoring\nWeek 9–10", C['green'], [
            "pyfolio live dashboards",
            "Real-time GARCH monitor",
            "LLM performance reports",
            "Alert & notification system",
            "Go-live: Production",
        ]),
    ]

    for i, (title, color, tasks) in enumerate(phases):
        x = 0.4 + i * 3.5
        # Phase header
        box(ax, x, 8.8, 3.0, 0.8, color, color, title, fontsize=9, radius=0.25)
        # Arrow between phases
        if i < len(phases) - 1:
            arrow(ax, x+3.0, 9.2, x+3.5, 9.2, color="#607D8B", lw=2.5, style="-|>")
        # Task box
        r = FancyBboxPatch((x, 1.0), 3.0, 7.6,
                           boxstyle="round,pad=0,rounding_size=0.2",
                           facecolor='white', edgecolor=color, linewidth=1.5, alpha=0.95, zorder=2)
        ax.add_patch(r)
        for j, task in enumerate(tasks):
            ty = 8.3 - j * 0.7
            circ = plt.Circle((x + 0.25, ty), 0.10, color=color, zorder=3)
            ax.add_patch(circ)
            ax.text(x + 0.45, ty, task, ha='left', va='center',
                    fontsize=7.5, color=C['darkgray'], zorder=3)

        # Deliverable label
        deliverables = [
            "LiteLLM + pyfolio live",
            "Backtest running",
            "AI agent trading",
            "Paper trading OK",
            "Production live 🚀",
        ]
        box(ax, x, 1.0, 3.0, 0.65, color, color, deliverables[i],
            fontsize=7.5, radius=0.2)

    # Timeline bar
    ax.add_patch(FancyBboxPatch((0.4, 0.2), 17.1, 0.4,
                                boxstyle="round,pad=0,rounding_size=0.15",
                                facecolor="#CFD8DC", edgecolor="#90A4AE", linewidth=1, zorder=2))
    for i, wk in enumerate(["Week 1", "Week 2", "Week 4", "Week 6", "Week 8", "Week 10"]):
        ax.text(0.4 + i * 3.4, 0.42, wk, ha='center', va='center',
                fontsize=7, color=C['darkgray'], zorder=3)

    save(fig, "/home/claude/uml_diagrams/06_migration_roadmap.png")

# ══════════════════════════════════════════════════════════════════════════════
# 7. DEPLOYMENT ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
def diagram_deployment():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16); ax.set_ylim(0, 10)
    ax.axis('off')
    fig.patch.set_facecolor("#E8EAF6")

    ax.text(8, 9.6, "ALCHEMY PLATFORM — Deployment Architecture (UML Deployment Diagram)",
            ha='center', fontsize=14, fontweight='bold', color=C['navy'])

    # Cloud boundary
    cloud = FancyBboxPatch((0.3, 0.5), 15.4, 8.6,
                           boxstyle="round,pad=0,rounding_size=0.4",
                           facecolor='#E3F2FD', edgecolor=C['blue'], linewidth=2, linestyle='--', zorder=1)
    ax.add_patch(cloud)
    ax.text(8, 9.1, "AWS Cloud (us-east-1)", ha='center', fontsize=10,
            color=C['blue'], fontstyle='italic')

    # EC2 — Strategy Server
    box(ax, 0.5, 5.0, 4.8, 3.5, "#E3F2FD", C['blue'],
        "EC2: Strategy Server", "t3.xlarge | 32GB RAM", 9, radius=0.3, label_color=C['navy'])
    for j, svc in enumerate(["blueshift-engine (Python 3.12)",
                              "zipline-pipeline service",
                              "ARCH volatility worker",
                              "LangGraph agent pool"]):
        box(ax, 0.7, 7.8-j*0.75, 4.3, 0.6, C['blue'], C['sky'], svc, fontsize=7, radius=0.1)

    # EC2 — AI/LLM Gateway
    box(ax, 5.8, 5.0, 4.5, 3.5, "#FFF3E0", C['orange'],
        "EC2: AI Gateway", "t3.large | LiteLLM Proxy", 9, radius=0.3, label_color=C['navy'])
    for j, svc in enumerate(["LiteLLM Proxy :4000",
                              "Redis Cache (signals)",
                              "Budget Manager",
                              "Fallback Router"]):
        box(ax, 6.0, 7.8-j*0.75, 4.1, 0.6, C['orange'], C['amber'], svc, fontsize=7, radius=0.1)

    # EC2 — Execution
    box(ax, 10.8, 5.0, 5.0, 3.5, "#FFEBEE", C['red'],
        "EC2: Execution Server", "c5.large | IB Gateway", 9, radius=0.3, label_color=C['navy'])
    for j, svc in enumerate(["IBController (Java)",
                              "Kite Connect (Python)",
                              "Risk Manager svc",
                              "Order Book / Deadman"]):
        box(ax, 11.0, 7.8-j*0.75, 4.6, 0.6, C['red'], "#EF9A9A", svc, fontsize=7, radius=0.1)

    # RDS / TimescaleDB
    box(ax, 0.5, 1.0, 4.5, 1.5, C['lightgreen'], C['green'],
        "TimescaleDB (RDS)", "Trade data / Metrics / OHLCV", 8, radius=0.3, label_color=C['darkgray'])

    # S3 / Reporting
    box(ax, 5.5, 1.0, 4.5, 1.5, "#F3E5F5", C['purple'],
        "S3 + CloudFront", "pyfolio Reports / Artifacts", 8, radius=0.3, label_color=C['darkgray'])

    # SQS
    box(ax, 10.8, 1.0, 5.0, 1.5, C['lightyellow'], C['amber'],
        "SQS + SNS", "Trade Events / Alerts / Notifications", 8, radius=0.3, label_color=C['darkgray'])

    # Arrows
    arrow(ax, 5.3, 6.5, 5.8, 6.5, C['orange'], "LLM Calls")
    arrow(ax, 10.3, 6.5, 10.8, 6.5, C['red'], "Signals")
    arrow(ax, 2.9, 5.0, 2.9, 2.5, C['green'], "Store Metrics")
    arrow(ax, 7.5, 5.0, 7.5, 2.5, C['purple'], "Publish Reports")
    arrow(ax, 13.2, 5.0, 13.2, 2.5, C['amber'], "Trade Events")

    save(fig, "/home/claude/uml_diagrams/07_deployment.png")


if __name__ == "__main__":
    print("Generating UML diagrams...")
    diagram_system_context()
    diagram_component_architecture()
    diagram_sequence()
    diagram_class()
    diagram_integration()
    diagram_migration()
    diagram_deployment()
    print("All diagrams generated successfully!")
