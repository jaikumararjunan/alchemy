"""
Generate 8 UML architecture diagrams for Alchemy v0.2
Includes: Frontend + Delta Exchange + Binance layers
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

OUT = "/home/claude/alchemy/docs/architecture"

C = dict(
    navy="#1B3A5C",  blue="#2E75B6",  sky="#5B9BD5",   teal="#00B0F0",
    green="#2E7D32", amber="#F59E0B", red="#C62828",    orange="#E65100",
    purple="#7B1FA2",gray="#546E7A",  white="#FFFFFF",  lgray="#F5F5F5",
    lblue="#E3F2FD", lgreen="#E8F5E9",lyellow="#FFFDE7",dgray="#37474F",
    crypto="#D97706",delta="#1D4ED8", binance="#F59E0B",
)

def save(fig, name):
    import os
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/{name}.png"
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {name}.png")

def box(ax, x, y, w, h, fill, edge, label, sub=None, fs=8.5, bold=True,
        lc="white", radius=0.25, lw=1.5, zorder=2):
    r = FancyBboxPatch((x,y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       facecolor=fill, edgecolor=edge, linewidth=lw, zorder=zorder)
    ax.add_patch(r)
    cy = y + h/2 + (0.1 if sub else 0)
    ax.text(x+w/2, cy, label, ha='center', va='center',
            fontsize=fs, fontweight='bold' if bold else 'normal',
            color=lc, zorder=zorder+1)
    if sub:
        ax.text(x+w/2, y+h/2-0.13, sub, ha='center', va='center',
                fontsize=6.5, color=lc, alpha=0.88, zorder=zorder+1)

def arr(ax, x1, y1, x2, y2, color="#546E7A", lw=1.4, label="", style="-|>"):
    ax.annotate("", xy=(x2,y2), xytext=(x1,y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                connectionstyle="arc3,rad=0.0"))
    if label:
        ax.text((x1+x2)/2+0.05,(y1+y2)/2+0.05, label,
                fontsize=6, color=color, va='center')

def title(ax, text, sub=""):
    ax.text(0.5, 0.97, text, transform=ax.transAxes,
            ha='center', va='top', fontsize=13, fontweight='bold', color=C['navy'])
    if sub:
        ax.text(0.5, 0.93, sub, transform=ax.transAxes,
                ha='center', va='top', fontsize=8, color=C['gray'])


# ══════════════════════════════════════════════════════════════════════════════
# 1 — SYSTEM CONTEXT (C4 Level 1) — updated with crypto
# ══════════════════════════════════════════════════════════════════════════════
def d1_system_context():
    fig, ax = plt.subplots(figsize=(16,10)); ax.set_xlim(0,16); ax.set_ylim(0,10)
    ax.axis('off'); fig.patch.set_facecolor("#F0F4F8")
    title(ax,"Alchemy Platform — System Context (C4 L1)","UML C4 Level 1 · All actors, brokers, exchanges and QuantInsti library ecosystem")

    # Central system
    box(ax,5.2,3.5,5.6,3.0,C['navy'],C['teal'],"ALCHEMY PLATFORM",
        "AI-Powered Algorithmic Trading",fs=12,radius=0.5,lw=3)

    # Actors
    for x,y,lbl,sub in [(0.2,8.2,"Quant Analyst","Strategy Design"),(6.2,8.2,"Portfolio Mgr","Risk Oversight"),(12.1,8.2,"Algo Trader","Live Execution")]:
        box(ax,x,7.8,3.5,0.9,C['purple'],"#4A148C",lbl,sub,fs=8,radius=0.2)

    # Brokers / Exchanges
    brokers=[
        (0.2,0.5,3.0,1.1,C['red'],"#B71C1C","Interactive Brokers","US Equities + Options\n(ib-controller)"),
        (3.6,0.5,3.0,1.1,C['blue'],"#0D47A1","Zerodha Kite","NSE / BSE India\n(kiteconnect3)"),
        (7.2,0.5,3.0,1.1,C['delta'],"#1E40AF","Delta Exchange","BTC/ETH Perps + Options\n(delta_gateway.py)"),
        (10.8,0.5,3.0,1.1,C['binance'],"#92400E","Binance","Spot + USD-M Futures\n(binance_gateway.py)"),
    ]
    for x,y,w,h,f,e,lbl,sub in brokers:
        box(ax,x,y,w,h,f,e,lbl,sub,fs=8,radius=0.2)

    # LLM + Blueshift
    box(ax,13.2,4.0,2.5,1.4,C['orange'],"#BF360C","LLM Providers","Claude/GPT/Gemini\n(litellm)",fs=7.5,radius=0.2)
    box(ax,13.2,5.8,2.5,1.4,C['sky'],"#01579B","QuantInsti Libs","pyfolio·arch·zipline\nblueshift-dev-kit",fs=7.5,radius=0.2)
    box(ax,13.2,2.2,2.5,1.4,C['green'],"#1B5E20","Frontend","React Dashboard\nVite + Tailwind CSS",fs=7.5,radius=0.2)

    # Arrows: actors → platform
    for x,y in [(1.95,7.8),(7.95,7.8),(13.85,7.8)]:
        arr(ax,x,y,x,6.5,C['purple'],lw=1.5)

    # Arrows: platform → brokers
    for bx,by in [(1.7,1.6),(5.1,1.6),(8.7,1.6),(12.3,1.6)]:
        arr(ax,8.0,3.5,bx,by,C['gray'],lw=1.2)

    # Arrows: platform → LLM / libs / frontend
    arr(ax,10.8,5.0,13.2,4.7,C["orange"],label="AI inference",lw=1.2)
    arr(ax,10.8,5.5,13.2,6.5,C["sky"],label="analytics",lw=1.2)
    arr(ax,10.8,4.2,13.2,2.9,C["green"],label="REST/WS",lw=1.2)

    save(fig,"01_system_context")


# ══════════════════════════════════════════════════════════════════════════════
# 2 — COMPONENT ARCHITECTURE (C4 Level 2) — 6 layers
# ══════════════════════════════════════════════════════════════════════════════
def d2_component():
    fig,ax = plt.subplots(figsize=(19,14)); ax.set_xlim(0,19); ax.set_ylim(0,14)
    ax.axis('off'); fig.patch.set_facecolor("#F8FBFF")
    title(ax,"Alchemy Platform — Component Architecture (C4 L2)","Six-layer decomposition with Frontend, AI Agent, Strategy, Analytics, Execution, Infrastructure")

    layers=[
        (0.1,11.8,1.8,"FRONTEND\nLAYER",    "#7B1FA2"),
        (0.1,9.6, 1.8,"AI AGENT\nLAYER",    C['orange']),
        (0.1,7.4, 1.8,"STRATEGY\nLAYER",    C['blue']),
        (0.1,5.2, 1.8,"ANALYTICS\nLAYER",   C['green']),
        (0.1,3.0, 1.8,"EXECUTION\nLAYER",   C['red']),
        (0.1,0.8, 1.8,"INFRA\nLAYER",       C['gray']),
    ]
    for x,y,h,lbl,col in layers:
        r=FancyBboxPatch((x,y),1.6,h,boxstyle="round,pad=0,rounding_size=0.2",
                         facecolor=col,edgecolor=col,linewidth=1,alpha=0.85,zorder=2)
        ax.add_patch(r)
        ax.text(x+0.8,y+h/2,lbl,ha='center',va='center',fontsize=7.5,
                fontweight='bold',color='white',zorder=3)

    def row(items, y, fill, edge, fs=7.5):
        xs = [2.2+i*(17-2.2)/len(items) for i in range(len(items))]
        w  = (17-2.2)/len(items) - 0.15
        for i,(lbl,sub) in enumerate(items):
            box(ax,xs[i],y,w,0.95,fill,edge,lbl,sub,fs=fs,radius=0.2)

    # Frontend layer
    row([("React Dashboard","Portfolio + Signals"),("Crypto Panel","Delta + Binance"),
         ("Risk Monitor","Emergency stop"),("Analytics View","Tear sheets"),
         ("Strategy Builder","Backtest + Deploy")],
        12.0,"#7B1FA2","#4A148C")

    # AI Agent layer
    row([("LiteLLM Gateway","100+ LLM providers"),("LangGraph Engine","Multi-agent orchestration"),
         ("Sentiment Agent","News + FinBERT"),("Volatility Agent","GARCH classifier"),
         ("Decision Agent","Signal generator"),("MCP Server","Broker tool calls")],
        9.8,C['orange'],"#BF360C",fs=7)

    # Strategy layer
    row([("Blueshift Engine","Strategy execution"),("SMA Crossover","Momentum template"),
         ("Zipline Pipeline","Factor screening"),("ML Strategy","RF/LSTM/XGBoost"),
         ("Crypto Strategy","BTC/ETH momentum")],
        7.6,C['blue'],"#0D47A1")

    # Analytics layer
    row([("pyfolio","Tear sheets"),("ARCH/GARCH","Vol engine"),
         ("quantrautil","NSE/US data"),("TimescaleDB","Time-series"),
         ("Redis","Signal cache")],
        5.4,C['green'],"#1B5E20")

    # Execution layer
    row([("IB Gateway","US markets"),("Kite Connect","NSE/BSE India"),
         ("Delta Gateway","BTC/ETH perps"),("Binance Gateway","Spot + Futures"),
         ("Risk Manager","Drawdown + limits")],
        3.2,C['red'],"#B71C1C")

    # Infra layer
    row([("FastAPI","REST + WebSocket"),("Docker Compose","Local dev stack"),
         ("AWS EC2","Cloud compute"),("S3/CloudFront","Reports + static"),
         ("SQS/SNS","Events + alerts")],
        1.0,C['gray'],"#263238")

    # Inter-layer arrows
    for x in [3.8,7.2,10.5,13.8]:
        for y_from,y_to in [(12.0,10.75),(9.8,8.55),(7.6,6.35),(5.4,4.15),(3.2,1.95)]:
            arr(ax,x,y_from,x,y_to,C['gray'],lw=1.0)

    save(fig,"02_component_architecture")


# ══════════════════════════════════════════════════════════════════════════════
# 3 — SEQUENCE: AI CRYPTO TRADE LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════════
def d3_sequence():
    fig,ax = plt.subplots(figsize=(19,13)); ax.set_xlim(0,19); ax.set_ylim(0,13)
    ax.axis('off'); fig.patch.set_facecolor("#FAFAFA")
    title(ax,"Alchemy — AI Crypto Trade Sequence Diagram",
          "UML Sequence · React frontend → LangGraph agents → Delta Exchange execution")

    parts=[
        (1.2, "React\nFrontend",   "#7B1FA2"),
        (3.5, "FastAPI\n:8000",    C['blue']),
        (5.8, "LangGraph\nAgent",  C['orange']),
        (8.1, "LiteLLM\nGateway",  C['amber']),
        (10.4,"GARCH\nVol Engine", C['green']),
        (12.7,"Delta\nGateway",    C['delta']),
        (15.0,"Binance\nGateway",  C['binance']),
        (17.3,"Risk\nManager",     C['red']),
    ]

    for x,lbl,col in parts:
        box(ax,x-0.65,11.5,1.3,0.9,col,col,lbl,fs=7,radius=0.15)
        ax.plot([x,x],[11.5,0.4],color='#CBD5E1',lw=1,linestyle='--',zorder=1)

    def msg(x1,x2,y,lbl,col="#546E7A",ret=False,lw=1.4):
        ax.annotate("",xy=(x2,y),xytext=(x1,y),
            arrowprops=dict(arrowstyle="<|-" if ret else "-|>",color=col,lw=lw,
                            linestyle="dashed" if ret else "solid"))
        ax.text((x1+x2)/2,(y+0.09),lbl,ha='center',fontsize=6.5,color=col)

    def act(x,y,h,col):
        ax.add_patch(FancyBboxPatch((x-0.08,y-h),0.16,h,
                     boxstyle="square,pad=0",facecolor=col,edgecolor='white',lw=0.5,alpha=0.9,zorder=2))

    msgs=[
        (1.2, 3.5, 10.8,"POST /signal {ticker:'BTCUSD',market:'CRYPTO'}",C['purple'],False),
        (3.5, 5.8, 10.2,"invoke_agent(ticker,market)",                    C['blue'],  False),
        (5.8, 8.1,  9.6,"llm.complete(news_sentiment_prompt)",             C['orange'],False),
        (8.1, 5.8,  9.0,"sentiment_score=0.72, conf=0.84",                 C['amber'], True),
        (5.8,10.4,  8.4,"garch.forecast_vol(returns_90d)",                 C['orange'],False),
        (10.4,5.8,  7.8,"annualized_vol=0.54, regime='high'",              C['green'], True),
        (5.8, 8.1,  7.2,"llm.complete(decision_prompt)",                   C['orange'],False),
        (8.1, 5.8,  6.6,"signal=LONG, pos=3%, sl=1.5%, tp=4%",            C['amber'], True),
        (5.8,17.3,  6.0,"check_risk(signal, portfolio_nav)",               C['orange'],False),
        (17.3,5.8,  5.4,"approved, adjusted_pos=2.8%",                     C['red'],   True),
        (5.8, 3.5,  4.8,"TradingSignal(BTCUSD, LONG, 2.8%)",              C['orange'],True),
        (3.5,12.7,  4.2,"delta.place_order(BTCUSD,buy,2,market,lev=5)",   C['blue'],  False),
        (12.7,3.5,  3.6,"order_id=DX-98312, state=filled, price=68,400",  C['delta'], True),
        (3.5,15.0,  3.0,"binance.place_order(BTCUSDT,BUY,0.001,MARKET)",  C['blue'],  False),
        (15.0,3.5,  2.4,"orderId=BN-77421, status=FILLED, avgPrice=68380", C['binance'],True),
        (3.5, 1.2,  1.8,"signal+order_ids → WebSocket broadcast",          C['blue'],  True),
        (1.2, 3.5,  1.2,"update_risk_limits(); render positions",           C['purple'],False),
    ]
    for x1,x2,y,lbl,col,ret in msgs:
        msg(x1,x2,y,lbl,col,ret)

    act(3.5, 10.8, 9.7, C['blue'])
    act(5.8, 10.2, 8.8, C['orange'])
    act(10.4,  8.4, 0.7, C['green'])
    act(12.7,  4.2, 0.7, C['delta'])
    act(15.0,  3.0, 0.7, C['binance'])

    save(fig,"03_sequence_crypto_trade")


# ══════════════════════════════════════════════════════════════════════════════
# 4 — CLASS DIAGRAM — full with crypto gateways
# ══════════════════════════════════════════════════════════════════════════════
def d4_class():
    fig,ax = plt.subplots(figsize=(19,14)); ax.set_xlim(0,19); ax.set_ylim(0,14)
    ax.axis('off'); fig.patch.set_facecolor("#FAFAFA")
    title(ax,"Alchemy — Complete Class Diagram","UML Class · 10 core classes covering AI agent, analytics, strategy, execution and crypto gateways")

    def cls(ax,x,y,w,title_text,attrs,methods,tc,bc,lh=0.28):
        lines  = 1+len(attrs)+1+len(methods)
        h      = lh*lines+0.4
        FancyBboxPatch((x,y-h),w,h,boxstyle="square,pad=0",
                        facecolor='white',edgecolor=bc,lw=1.5,zorder=2,clip_on=False)
        r=FancyBboxPatch((x,y-h),w,h,boxstyle="square,pad=0",
                         facecolor='white',edgecolor=bc,linewidth=1.5,zorder=2)
        ax.add_patch(r)
        r2=FancyBboxPatch((x,y-lh-0.15),w,lh+0.15,boxstyle="square,pad=0",
                           facecolor=tc,edgecolor=bc,linewidth=1.5,zorder=3)
        ax.add_patch(r2)
        ax.text(x+w/2,y-lh/2-0.07,title_text,ha='center',va='center',
                fontsize=7,fontweight='bold',color='white',zorder=4)
        sep_y=y-lh-0.15-lh*len(attrs)-0.05
        ax.plot([x,x+w],[sep_y,sep_y],color=bc,lw=0.7,zorder=3)
        for i,a in enumerate(attrs):
            ax.text(x+0.07,y-lh-0.15-lh*(i+0.5)-0.02,f" {a}",
                    ha='left',va='center',fontsize=6,color=C['dgray'],family='monospace',zorder=3)
        for i,m in enumerate(methods):
            ax.text(x+0.07,sep_y-lh*(i+0.5)-0.02,f" {m}",
                    ha='left',va='center',fontsize=6,color=C['navy'],family='monospace',zorder=3)
        return y-h

    # Row 1
    cls(ax,0.2,13.5,3.8,"AlchemyTradingState",
        ["+ ticker: str","+ market: MarketType","+ sentiment_score: float",
         "+ current_volatility: float","+ signal: SignalType","+ order_id: str"],
        ["+ is_actionable() → bool","+ add_error(msg)","+ to_dict() → dict"],
        C['orange'],"#BF360C")

    cls(ax,4.4,13.5,3.8,"AlchemyLLMRouter",
        ["- primary_model: str","- fallback_model: str","- budget_manager"],
        ["+ complete(user,sys,json) → dict","+ acomplete(user) → dict","+ stats() → dict"],
        C['amber'],"#92400E")

    cls(ax,8.6,13.5,4.0,"«abstract» AlchemyStrategyBase",
        ["# params: StrategyParams","# context: BlueshiftContext"],
        ["+ initialize(ctx) → None","+ handle_data(ctx,data) → None",
         "# rebalance(ctx,data) → None","+ order_target_pct(asset,pct)"],
        C['blue'],"#0D47A1")

    cls(ax,13.0,13.5,5.7,"SMACrossoverStrategy(AlchemyStrategyBase)",
        ["+ fast: int = 10","+ slow: int = 30"],
        ["+ rebalance(ctx,data) → None",
         "+ compute_signals_offline(prices) → df"],
        C['sky'],"#0277BD")

    # Row 2
    cls(ax,0.2,9.6,3.8,"VolatilityEngine",
        ["- model_type: str","- p,q: int","- _result: ARCHModelResult"],
        ["+ fit(returns) → self","+ forecast_vol(horizon) → float",
         "+ get_current_vol() → Series","+ vol_regime() → str"],
        C['green'],"#1B5E20")

    cls(ax,4.4,9.6,3.8,"PortfolioAnalytics",
        ["- returns: pd.Series","- benchmark: pd.Series"],
        ["+ compute_metrics() → dict","+ create_full_tear_sheet()",
         "+ save_tear_sheet(path) → Path"],
        C['teal'],"#006064")

    cls(ax,8.6,9.6,4.0,"AlchemyPipelineScreen",
        ["- engine: SimplePipelineEngine","- cfg: ScreenConfig"],
        ["+ build_pipeline() → Pipeline","+ run(start,end) → df",
         "+ momentum_factor_offline(prices) → df"],
        C['sky'],"#01579B")

    cls(ax,13.0,9.6,5.7,"RiskManager",
        ["- cfg: RiskConfig","- _pnl: DailyPnL","- _emergency_stop: bool"],
        ["+ evaluate(signal,nav) → RiskVeto",
         "+ trigger_emergency_stop(reason)","+ status() → dict",
         "+ vol_scale_position(signal) → float"],
        "#6A1B9A","#4A148C")

    # Row 3 — crypto
    cls(ax,0.2,5.8,4.0,"DeltaGateway",
        ["- base_url: str","- paper: bool","- testnet: bool"],
        ["+ get_ticker(symbol) → dict",
         "+ place_order(sym,side,size,lev) → dict",
         "+ get_positions() → list","+ get_funding_rate(sym) → dict",
         "+ cancel_all_orders() → dict"],
        C['delta'],"#1E40AF")

    cls(ax,4.6,5.8,4.0,"BinanceGateway",
        ["- market: MarketType","- paper: bool","- testnet: bool"],
        ["+ get_ticker(symbol) → dict",
         "+ place_order(sym,side,qty,lev) → dict",
         "+ get_positions() → list","+ get_funding_rate(sym) → list",
         "+ close_position(symbol) → dict"],
        C['binance'],"#78350F")

    cls(ax,9.0,5.8,4.5,"AlchemyTradingAgent",
        ["- graph: CompiledGraph","- llm: AlchemyLLMRouter",
         "- vol_engine: VolatilityEngine"],
        ["+ build_graph() → CompiledGraph","+ run(ticker,market) → TradingSignal",
         "+ sentiment_node(state) → state","+ decision_node(state) → state"],
        C['orange'],"#BF360C")

    cls(ax,13.9,5.8,4.8,"IBGateway / KiteGateway",
        ["- cfg: IBConfig | KiteConfig","- paper_trading: bool"],
        ["+ connect() → bool","+ execute_signal(sig,nav) → str",
         "+ get_portfolio() → list","+ cancel_all_orders() → int"],
        C['red'],"#B71C1C")

    # Relationships
    def rel(x1,y1,x2,y2,dashed=True,col=C['gray'],lbl=""):
        ax.annotate("",xy=(x2,y2),xytext=(x1,y1),
            arrowprops=dict(arrowstyle="-|>",color=col,lw=1.1,
                           connectionstyle="arc3,rad=0.03",
                           linestyle="dashed" if dashed else "solid"))
        if lbl:
            ax.text((x1+x2)/2+0.1,(y1+y2)/2,lbl,fontsize=5.5,color=col)

    rel(6.3,13.5,10.0,13.5,dashed=True,col=C['gray'],lbl="<<uses>>")
    rel(11.3,9.6,2.1,9.6,dashed=True,col=C['green'],lbl="<<uses>>")
    rel(11.3,9.6,6.3,9.6,dashed=True,col=C['teal'])
    rel(11.3,9.6,8.6,9.6,dashed=True,col=C['sky'])
    rel(9.0,5.8,2.1,8.7,dashed=True,col=C['green'])
    rel(9.0,5.8,4.4,8.7,dashed=True,col=C['teal'])
    rel(9.0,5.8,4.4,13.5,dashed=True,col=C['amber'])
    rel(2.2,5.8,1.2,0.5,dashed=False,col=C['delta'],lbl="paper/live")
    rel(6.6,5.8,5.4,0.5,dashed=False,col=C['binance'],lbl="paper/live")

    save(fig,"04_class_diagram")


# ══════════════════════════════════════════════════════════════════════════════
# 5 — FRONTEND COMPONENT ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
def d5_frontend():
    fig,ax = plt.subplots(figsize=(17,11)); ax.set_xlim(0,17); ax.set_ylim(0,11)
    ax.axis('off'); fig.patch.set_facecolor("#0F172A")

    title_p = fig.add_axes([0,0.91,1,0.09])
    title_p.axis('off')
    title_p.set_facecolor("#1E293B")
    title_p.text(0.5,0.6,"Alchemy Frontend — React Component Architecture",
                 ha='center',va='center',fontsize=13,fontweight='bold',color='white',
                 transform=title_p.transAxes)
    title_p.text(0.5,0.15,"Vite + React 18 + Tailwind CSS + Zustand + React Query",
                 ha='center',va='center',fontsize=8.5,color='#94A3B8',
                 transform=title_p.transAxes)

    def node(x,y,w,h,lbl,sub,fill,edge):
        box(ax,x,y,w,h,fill,edge,lbl,sub,fs=8,radius=0.2,lc='white')

    def conn(x1,y1,x2,y2,col='#475569',lw=1.2):
        ax.annotate("",xy=(x2,y2),xytext=(x1,y1),
            arrowprops=dict(arrowstyle="-|>",color=col,lw=lw,
                           connectionstyle="arc3,rad=0.0"))

    # Entry
    node(7.0,9.2,3.0,0.9,"main.jsx","React.StrictMode entry","#1E40AF","#3B82F6")
    node(7.0,7.8,3.0,0.9,"App.jsx","BrowserRouter + Routes","#1D4ED8","#60A5FA")
    conn(8.5,9.2,8.5,8.7,col='#60A5FA')

    # Layout
    node(7.0,6.4,3.0,0.9,"Layout.jsx","Sidebar + Topbar + Outlet","#6D28D9","#A78BFA")
    conn(8.5,7.8,8.5,7.3,col='#A78BFA')

    # Pages row
    pages=[
        (0.3,"DashboardPage","NAV chart, signals, crypto snap",   "#1E3A5F"),
        (2.7,"PortfolioPage","Allocation, P&L, positions",        "#1E3A5F"),
        (5.1,"CryptoPage",   "Delta + Binance trading",           "#78350F"),
        (7.5,"SignalsPage",  "Agent runner + history",            "#1E3A5F"),
        (9.9,"RiskPage",     "Emergency stop, drawdown",          "#7F1D1D"),
        (12.3,"AnalyticsPage","Returns, metrics, benchmark",      "#1E3A5F"),
        (14.7,"SettingsPage","Broker config, env toggle",         "#1E3A5F"),
    ]
    for x,lbl,sub,fill in pages:
        node(x,4.5,2.2,0.9,lbl,sub,fill,"#475569")
        conn(8.5,6.4,x+1.1,5.4,col='#64748B')

    # Shared layer
    for i,(lbl,sub,fill) in enumerate([
        ("api/client.js","axios + all endpoints","#115E59"),
        ("store/index.js","Zustand global state","#115E59"),
        ("hooks/useAlchemySocket","Socket.IO live feed","#115E59"),
        ("recharts","NAV, P&L, allocation charts","#1C1917"),
        ("@tanstack/react-query","Server state + cache","#1C1917"),
    ]):
        node(0.3+i*3.35,2.8,3.1,0.9,lbl,sub,fill,"#374151")

    # Backend connection
    node(6.5,0.9,4.0,0.9,"FastAPI :8000","REST + WebSocket /ws","#1B3A5C","#2E75B6")
    for x in [1.8,5.15,8.5,11.85,15.2]:
        conn(x,2.8,8.5,1.8,col='#2E75B6')

    # Legend
    for i,(col,lbl) in enumerate([("#1E40AF","Router/Entry"),("#6D28D9","Layout"),
                                    ("#1E3A5F","Pages"),("#78350F","Crypto UI"),
                                    ("#115E59","Shared Hooks/API"),("#1B3A5C","Backend")]):
        ax.add_patch(FancyBboxPatch((0.4+i*2.7,0.1),0.25,0.25,
                     boxstyle="square,pad=0",facecolor=col,edgecolor='white',lw=0.5))
        ax.text(0.75+i*2.7,0.22,lbl,fontsize=6.5,color='#94A3B8',va='center')

    save(fig,"05_frontend_architecture")


# ══════════════════════════════════════════════════════════════════════════════
# 6 — CRYPTO EXECUTION LAYER DETAIL
# ══════════════════════════════════════════════════════════════════════════════
def d6_crypto_execution():
    fig,ax = plt.subplots(figsize=(17,10)); ax.set_xlim(0,17); ax.set_ylim(0,10)
    ax.axis('off'); fig.patch.set_facecolor("#0A0E1A")

    # Background glow
    for x,w,col in [(0.2,7.8,"#1D4ED8"),(8.8,7.8,"#78350F")]:
        ax.add_patch(FancyBboxPatch((x,0.5),w,9.0,
                     boxstyle="round,pad=0,rounding_size=0.3",
                     facecolor=col,edgecolor=col,linewidth=0,alpha=0.08,zorder=0))

    ax.text(4.1,9.6,"DELTA EXCHANGE",ha='center',fontsize=13,fontweight='bold',
            color='#60A5FA',zorder=2)
    ax.text(12.7,9.6,"BINANCE",ha='center',fontsize=13,fontweight='bold',
            color='#F59E0B',zorder=2)
    ax.text(8.5,9.6,"|",ha='center',fontsize=16,color='#374151',zorder=2)

    def blk(x,y,w,lbl,sub,fill,edge):
        box(ax,x,y,w,0.9,fill,edge,lbl,sub,fs=8,radius=0.2,lc='white')

    def con(x1,y1,x2,y2,col,lbl="",lw=1.3):
        ax.annotate("",xy=(x2,y2),xytext=(x1,y1),
            arrowprops=dict(arrowstyle="-|>",color=col,lw=lw,
                           connectionstyle="arc3,rad=0.0"))
        if lbl: ax.text((x1+x2)/2+0.1,(y1+y2)/2+0.05,lbl,fontsize=6.5,color=col)

    # Delta side
    blk(0.4,8.2,7.0,"DeltaGateway","alchemy/execution/crypto/delta_gateway.py","#1E3A8A","#3B82F6")
    for i,(lbl,sub) in enumerate([
        ("Perpetual Futures","BTCUSD · ETHUSD · SOLUSD · BNBUSD"),
        ("Options","Call + Put · Strike-expiry combos"),
        ("MOVE Contracts","Volatility products"),
        ("Spot Markets","BTC-USDT · ETH-USDT"),
    ]):
        blk(0.4,6.8-i*1.1,3.3,lbl,sub,"#1E3A5F","#3B82F6")

    for i,(lbl,sub) in enumerate([
        ("Paper Mode","Simulated fills, no real API calls"),
        ("HMAC-SHA256 Auth","Request signing for all private endpoints"),
        ("Testnet Support","testnet-api.delta.exchange"),
        ("Funding Rates","8-hour perpetual funding"),
    ]):
        blk(3.9,6.8-i*1.1,3.5,lbl,sub,"#1C2A3A","#60A5FA")

    # Endpoints list
    for i,ep in enumerate(["GET /v2/tickers/{symbol}","GET /v2/l2orderbook/{symbol}",
                             "POST /v2/orders","DELETE /v2/orders","GET /v2/positions/margined"]):
        ax.text(0.5,5.3-i*0.32,f"  {ep}",fontsize=6.5,color='#94A3B8',family='monospace',zorder=3)

    # Binance side
    blk(9.2,8.2,7.0,"BinanceGateway","alchemy/execution/crypto/binance_gateway.py","#78350F","#F59E0B")
    for i,(lbl,sub) in enumerate([
        ("Spot Trading","BTCUSDT · ETHUSDT · 300+ pairs"),
        ("USD-M Futures","BTCUSDT perp · ETHUSDT perp"),
        ("COIN-M Futures","BTCUSD_PERP delivery"),
        ("Testnet","testnet.binancefuture.com"),
    ]):
        blk(9.2,6.8-i*1.1,3.3,lbl,sub,"#451A03","#F59E0B")

    for i,(lbl,sub) in enumerate([
        ("Paper Mode","Simulated with live price lookup"),
        ("HMAC-SHA256 Auth","X-MBX-APIKEY header signing"),
        ("Leverage Control","set_leverage() before order"),
        ("Funding History","/fapi/v1/income?incomeType=FUNDING_FEE"),
    ]):
        blk(12.7,6.8-i*1.1,3.3,lbl,sub,"#2C1500","#FBBF24")

    for i,ep in enumerate(["GET /fapi/v1/ticker/24hr","GET /fapi/v1/klines",
                             "POST /fapi/v1/order","DELETE /fapi/v1/allOpenOrders",
                             "GET /fapi/v2/positionRisk"]):
        ax.text(9.3,5.3-i*0.32,f"  {ep}",fontsize=6.5,color='#94A3B8',family='monospace',zorder=3)

    # Risk Manager connection
    blk(6.2,1.3,4.6,"Risk Manager","Validates every signal before execution","#7F1D1D","#EF4444")
    con(4.0,8.2,8.5,2.2,col='#EF4444',lbl="evaluate(signal)")
    con(12.7,8.2,8.5,2.2,col='#EF4444',lbl="evaluate(signal)")

    save(fig,"06_crypto_execution")


# ══════════════════════════════════════════════════════════════════════════════
# 7 — DEPLOYMENT ARCHITECTURE (AWS)
# ══════════════════════════════════════════════════════════════════════════════
def d7_deployment():
    fig,ax = plt.subplots(figsize=(17,11)); ax.set_xlim(0,17); ax.set_ylim(0,11)
    ax.axis('off'); fig.patch.set_facecolor("#E8EAF6")
    title(ax,"Alchemy — AWS Deployment Architecture","UML Deployment · EC2 clusters · RDS/TimescaleDB · S3 · SQS/SNS · CloudFront CDN")

    # Cloud boundary
    ax.add_patch(FancyBboxPatch((0.2,0.4),16.6,10.0,
                 boxstyle="round,pad=0,rounding_size=0.4",
                 facecolor='#EEF2FF',edgecolor='#6366F1',linewidth=2,
                 linestyle='--',zorder=0))
    ax.text(8.5,10.25,"AWS Cloud (ap-south-1 — Mumbai)",ha='center',
            fontsize=9,color='#6366F1',fontstyle='italic')

    # EC2 Instances
    instances=[
        (0.4,5.5,4.5,4.3,"EC2: Frontend + API","t3.large · FastAPI :8000 + React",C['blue'],"#DBEAFE",[
            "Vite build (static files)","FastAPI :8000","uvicorn workers × 4","WebSocket /ws"]),
        (5.2,5.5,4.5,4.3,"EC2: AI Gateway","t3.xlarge · LangGraph + LiteLLM",C['orange'],"#FFF7ED",[
            "LiteLLM proxy :4000","LangGraph agent pool","VolatilityEngine service","Redis :6379 (signals cache)"]),
        (10.0,5.5,4.5,4.3,"EC2: Execution","c5.large · Brokers + Risk",C['red'],"#FEE2E2",[
            "IBController (Java) :7497","Kite Connect service","Delta + Binance gateways","Risk Manager service"]),
        (14.8,5.5,1.8,4.3,"EC2: ML","r6i.xlarge",C['green'],"#DCFCE7",[
            "GARCH workers","Factor pipeline","ML model serve","Backtester"]),
    ]
    for x,y,w,h,name,desc,col,bg,svcs in instances:
        ax.add_patch(FancyBboxPatch((x,y),w,h,
                     boxstyle="round,pad=0,rounding_size=0.2",
                     facecolor=bg,edgecolor=col,linewidth=1.5,zorder=1))
        ax.text(x+w/2,y+h-0.2,name,ha='center',fontsize=8,fontweight='bold',color=col,zorder=2)
        ax.text(x+w/2,y+h-0.5,desc,ha='center',fontsize=6.5,color=C['gray'],zorder=2)
        for j,svc in enumerate(svcs):
            ax.text(x+0.15,y+h-0.85-j*0.55,f"▸ {svc}",fontsize=6.5,color=C['dgray'],zorder=2)

    # Data stores
    stores=[
        (0.4,1.0,3.8,1.4,"TimescaleDB (RDS)","OHLCV · Trades · Positions · P&L",C['green'],"#ECFDF5"),
        (4.5,1.0,3.8,1.4,"S3 + CloudFront","pyfolio reports · React build · Artifacts",C['purple'],"#F5F3FF"),
        (8.6,1.0,3.8,1.4,"SQS + SNS","Trade events · Risk alerts · Notifications",C['amber'],"#FFFBEB"),
        (12.7,1.0,3.8,1.4,"Secrets Manager","API keys · DB passwords · Certs",C['red'],"#FEF2F2"),
    ]
    for x,y,w,h,name,desc,col,bg in stores:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0,rounding_size=0.2",
                     facecolor=bg,edgecolor=col,linewidth=1.5,zorder=1))
        ax.text(x+w/2,y+0.9,name,ha='center',fontsize=8,fontweight='bold',color=col,zorder=2)
        ax.text(x+w/2,y+0.5,desc,ha='center',fontsize=6.5,color=C['gray'],zorder=2)

    # Connections
    for x in [2.6,7.4,12.2]:
        arr(ax,x,5.5,x,2.4,C['gray'],lw=1.2)
    arr(ax,14.9,5.5,14.5,2.4,C['gray'],lw=1.2)
    for x in [2.6,7.4,12.2]:
        arr(ax,x+2.6,5.5,x+2.6,2.4,C['gray'],lw=1.0)

    # Inter-EC2 connections
    arr(ax,4.9,7.7,5.2,7.7,C['orange'],lw=1.5,label="LLM calls")
    arr(ax,9.7,7.7,10.0,7.7,C['red'],lw=1.5,label="Signals")
    arr(ax,14.5,7.7,14.8,7.7,C['green'],lw=1.3,label="Models")

    save(fig,"07_deployment")


# ══════════════════════════════════════════════════════════════════════════════
# 8 — MODULE DEPENDENCY MAP
# ══════════════════════════════════════════════════════════════════════════════
def d8_module_map():
    fig,ax = plt.subplots(figsize=(17,11)); ax.set_xlim(0,17); ax.set_ylim(0,11)
    ax.axis('off'); fig.patch.set_facecolor("#F0FDF4")
    title(ax,"Alchemy — Module Dependency Map","Package structure and inter-module dependencies · Python backend + React frontend")

    # Backend modules
    modules=[
        # (x,y,w,h, pkg, files, fill, edge)
        (0.2,7.5,3.8,3.0,"alchemy.core","state.py\nconfig.py",C['navy'],"#1B3A5C"),
        (4.4,7.5,3.8,3.0,"alchemy.llm","router.py\n(LiteLLM wrapper)",C['amber'],"#78350F"),
        (8.6,7.5,3.8,3.0,"alchemy.agents","graph.py\n(LangGraph pipeline)",C['orange'],"#BF360C"),
        (12.8,7.5,3.8,3.0,"alchemy.strategy","base.py\nsma_crossover.py",C['blue'],"#0D47A1"),
        (0.2,4.2,3.8,2.8,"alchemy.analytics","volatility.py\nportfolio.py",C['green'],"#1B5E20"),
        (4.4,4.2,3.8,2.8,"alchemy.data","adapter.py\n(quantrautil + Redis)",C['gray'],"#37474F"),
        (8.6,4.2,3.8,2.8,"alchemy.pipeline","screen.py\n(zipline-pipeline)",C['sky'],"#01579B"),
        (12.8,4.2,3.8,2.8,"alchemy.risk","manager.py\n(RiskManager)",C['purple'],"#4A148C"),
        (0.2,1.2,3.8,2.5,"alchemy.execution","ib_gateway.py\nkite_gateway.py",C['red'],"#B71C1C"),
        (4.4,1.2,3.8,2.5,"execution.crypto","delta_gateway.py\nbinance_gateway.py",C['delta'],"#1E40AF"),
        (8.6,1.2,3.8,2.5,"alchemy.api","app.py\ncrypto_routes.py",C['blue'],"#0D47A1"),
        (12.8,1.2,3.8,2.5,"frontend","React + Vite\n8 pages · Zustand",C['purple'],"#6D28D9"),
    ]
    for x,y,w,h,pkg,files,fill,edge in modules:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0,rounding_size=0.2",
                     facecolor=fill,edgecolor=edge,linewidth=1.5,alpha=0.9,zorder=2))
        ax.text(x+w/2,y+h-0.3,pkg,ha='center',va='top',fontsize=7.5,
                fontweight='bold',color='white',zorder=3)
        ax.text(x+w/2,y+0.35,files,ha='center',va='bottom',fontsize=6.5,
                color='white',alpha=0.85,zorder=3)

    # Dependencies (arrows)
    deps=[
        ((2.1,7.5),(6.3,10.5),C['amber'],"config"),
        ((2.1,7.5),(10.5,10.5),C['orange'],"state"),
        ((6.3,7.5),(10.5,10.5),C['orange'],"complete()"),
        ((10.5,7.5),(12.8,8.7),C['blue'],"signals"),
        ((2.1,4.2),(2.1,7.5),C['navy'],"uses"),
        ((6.3,4.2),(2.1,7.5),C['navy'],"uses"),
        ((10.5,7.5),(2.1,7.0),C['green'],"vol_engine"),
        ((2.1,1.2),(12.8,5.6),C['purple'],"risk_check"),
        ((4.4+1.9,1.2),(8.6+1.9,4.2+1.4),C['sky'],"data feed"),
        ((8.6+1.9,1.2),(8.6+1.9,4.2),C['blue'],"routes"),
        ((12.8+1.9,1.2),(8.6+1.9,1.2),C['purple'],"REST/WS"),
    ]
    for (x1,y1),(x2,y2),col,lbl in deps:
        ax.annotate("",xy=(x2,y2),xytext=(x1,y1),
            arrowprops=dict(arrowstyle="-|>",color=col,lw=1.1,
                           connectionstyle="arc3,rad=0.1",linestyle="dashed"))

    save(fig,"08_module_dependency")


if __name__=="__main__":
    print("Generating UML diagrams v0.2 …")
    d1_system_context()
    d2_component()
    d3_sequence()
    d4_class()
    d5_frontend()
    d6_crypto_execution()
    d7_deployment()
    d8_module_map()
    print("All 8 diagrams generated!")
