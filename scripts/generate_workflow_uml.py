"""Generate 4 workflow UML diagrams for Alchemy v0.3"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np, os

OUT = "/home/claude/alchemy/docs/workflows"
os.makedirs(OUT, exist_ok=True)

C = dict(
    navy="#1B3A5C", blue="#2E75B6", sky="#5B9BD5",  teal="#00B0F0",
    green="#2E7D32",amber="#F59E0B",red="#C62828",   orange="#E65100",
    purple="#7B1FA2",gray="#546E7A",white="#FFFFFF",  dgray="#37474F",
    delta="#1D4ED8", binance="#F59E0B",
    s_pending="#374151", s_validated="#1E40AF", s_risk="#6D28D9",
    s_token="#0F766E", s_routed="#0369A1", s_placed="#B45309",
    s_monitoring="#B45309", s_filled="#065F46", s_settled="#166534",
    s_rejected="#991B1B", s_cancelled="#374151", s_error="#7F1D1D",
)

def save(fig, name):
    path = f"{OUT}/{name}.png"
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {name}.png")

def box(ax, x, y, w, h, fill, edge, label, sub=None, fs=8.5, bold=True,
        lc="white", radius=0.2, lw=1.5, z=2):
    ax.add_patch(FancyBboxPatch((x,y),w,h,
                 boxstyle=f"round,pad=0,rounding_size={radius}",
                 facecolor=fill,edgecolor=edge,linewidth=lw,zorder=z))
    cy = y+h/2+(0.08 if sub else 0)
    ax.text(x+w/2,cy,label,ha='center',va='center',fontsize=fs,
            fontweight='bold' if bold else 'normal',color=lc,zorder=z+1)
    if sub:
        ax.text(x+w/2,y+h/2-0.11,sub,ha='center',va='center',
                fontsize=6.2,color=lc,alpha=0.88,zorder=z+1)

def arr(ax, x1, y1, x2, y2, col="#546E7A", lw=1.4, lbl="", style="-|>", rad=0.0):
    ax.annotate("",xy=(x2,y2),xytext=(x1,y1),
        arrowprops=dict(arrowstyle=style,color=col,lw=lw,
                       connectionstyle=f"arc3,rad={rad}"))
    if lbl:
        ax.text((x1+x2)/2+0.05,(y1+y2)/2+0.06,lbl,fontsize=6.2,color=col)

def title(ax, t, sub=""):
    ax.text(0.5,0.97,t,transform=ax.transAxes,ha='center',va='top',
            fontsize=13,fontweight='bold',color=C['navy'])
    if sub: ax.text(0.5,0.93,sub,transform=ax.transAxes,ha='center',va='top',fontsize=8,color=C['gray'])


# ══════════════════════════════════════════════════════════════════════════════
# 1 — WORKFLOW STATE MACHINE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════
def d_state_machine():
    fig, ax = plt.subplots(figsize=(18,12)); ax.set_xlim(0,18); ax.set_ylim(0,12)
    ax.axis('off'); fig.patch.set_facecolor("#F8FAFF")
    title(ax,"Alchemy — Order Workflow State Machine",
          "LangGraph State Diagram · 9 happy-path states · 3 terminal error states · Retry loop")

    # States (x, y, w, h, fill, edge, label, sub)
    states = [
        (7.5,10.3,3.0,0.8, C['s_pending'],   "#475569", "PENDING",          "Initial state"),
        (7.5, 8.8,3.0,0.8, C['s_validated'], "#3B82F6", "SIGNAL_VALIDATED",  "Symbol · Qty · Type OK"),
        (7.5, 7.3,3.0,0.8, C['s_risk'],      "#A78BFA", "RISK_CHECKED",      "RiskManager approved"),
        (7.5, 5.8,3.0,0.8, C['s_token'],     "#2DD4BF", "TOKEN_VERIFIED",    "Exchange token ACTIVE"),
        (7.5, 4.3,3.0,0.8, C['s_routed'],    "#38BDF8", "ROUTED",            "SmartRouter → exchange"),
        (7.5, 2.8,3.0,0.8, C['s_placed'],    "#FCD34D", "PLACED",            "Order submitted"),
        (7.5, 1.3,3.0,0.8, C['s_monitoring'],"#F59E0B", "MONITORING",        "Polling for fill"),

        # Terminal states - right side
        (13.0,4.3,2.8,0.8, C['s_filled'],    "#10B981", "FILLED",            "Execution confirmed"),
        (13.0,2.8,2.8,0.8, C['s_filled'],    "#065F46", "PARTIALLY_FILLED",  "Partial execution"),
        (13.0,1.3,2.8,0.8, C['s_settled'],   "#14532D", "SETTLED",           "P&L recorded ✓"),

        # Error/cancel - left side
        (1.5, 5.8,2.8,0.8, C['s_rejected'],  "#EF4444", "REJECTED",          "Exchange rejected"),
        (1.5, 4.3,2.8,0.8, C['s_cancelled'], "#6B7280", "CANCELLED",         "Risk/user/system"),
        (1.5, 2.8,2.8,0.8, C['s_error'],     "#7F1D1D", "ERROR",             "Exception raised"),
    ]
    for x,y,w,h,fill,edge,lbl,sub in states:
        box(ax,x,y,w,h,fill,edge,lbl,sub,fs=8,radius=0.2)

    # Happy path arrows
    cx = 9.0
    for y1,y2 in [(10.3,9.6),(9.6,9.0),(9.0,8.2),(8.2,7.6),(7.6,6.7),(6.7,6.1),(6.1,5.2),(5.2,4.5),(4.5,3.6),(3.6,3.0),(3.0,2.1)]:
        arr(ax, cx, y1, cx, y2, C['blue'], lw=2.0)

    # Error exits (from PENDING → each error via handle_error node)
    for y_from, y_to, col in [
        (8.8, 6.2, C['s_rejected']),   # from SIGNAL_VALIDATED → ERROR
        (7.3, 5.3, C['gray']),          # RISK_CHECKED → CANCELLED
        (5.8, 5.1, C['s_error']),       # TOKEN_VERIFIED → ERROR
        (2.8, 3.6, C['s_rejected']),    # PLACED → REJECTED
    ]:
        arr(ax, 7.5, y_from+0.4, 4.3, y_to+0.4, col, lw=1.2, rad=0.2)

    # FILLED/PARTIALLY_FILLED → SETTLED
    arr(ax, 13.0+1.4, 4.3+0.4, 13.0+1.4, 3.1, C['green'], lw=1.4)
    arr(ax, 13.0+1.4, 2.8+0.4, 13.0+1.4, 2.1, C['green'], lw=1.4)
    arr(ax, 15.8,     1.3+0.4, 13.0+1.4, 1.1, C['green'], lw=1.4)

    # MONITORING → FILLED (right branch)
    arr(ax, 10.5, 1.7, 13.0, 4.7, C['green'], lw=1.4, lbl="FILL")
    arr(ax, 10.5, 1.7, 13.0, 3.2, C['teal'],  lw=1.2, lbl="PARTIAL")
    arr(ax, 9.0,  1.3, 4.3,  3.2, C['red'],   lw=1.2, lbl="REJECT")

    # CANCELLED / REJECTED → SETTLED
    arr(ax, 1.5+1.4, 4.3, 1.5+1.4, 3.6, C['gray'],  lw=1.1)
    arr(ax, 1.5+1.4, 2.8, 1.5+1.4, 2.1, C['gray'],  lw=1.1)
    arr(ax, 2.9,     2.1, 13.0,    1.7, C['gray'],  lw=1.0, lbl="→ SETTLED")

    # Retry loop: ERROR → PENDING
    ax.annotate("", xy=(7.5,10.7), xytext=(1.5+1.4,2.8),
        arrowprops=dict(arrowstyle="-|>",color=C['amber'],lw=1.3,
                       connectionstyle="arc3,rad=-0.4"))
    ax.text(4.2,7.5,"retry (max 2)",fontsize=6.5,color=C['amber'],rotation=80)

    # Legend
    for i,(col,lbl) in enumerate([(C['blue'],"Happy Path"),(C['green'],"Fill/Settle"),
                                    (C['red'],"Reject/Error"),(C['gray'],"Cancel"),(C['amber'],"Retry")]):
        ax.plot([0.4+i*3.4, 0.9+i*3.4],[0.5,0.5],color=col,lw=2.5)
        ax.text(1.0+i*3.4,0.5,lbl,fontsize=7,color=col,va='center')

    save(fig,"01_workflow_state_machine")


# ══════════════════════════════════════════════════════════════════════════════
# 2 — BUY/SELL SEQUENCE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════
def d_buy_sell_sequence():
    fig,ax = plt.subplots(figsize=(19,13)); ax.set_xlim(0,19); ax.set_ylim(0,13)
    ax.axis('off'); fig.patch.set_facecolor("#FAFAFA")
    title(ax,"Alchemy — Buy/Sell Order Workflow Sequence",
          "UML Sequence · Frontend order form → workflow engine → smart router → exchange execution")

    parts=[
        (1.2, "React\nWorkflow UI",  C['purple']),
        (3.2, "FastAPI\n:8000",      C['blue']),
        (5.2, "Workflow\nEngine",    C['orange']),
        (7.2, "Validate\nNode",      "#4F46E5"),
        (9.2, "Risk\nNode",          C['purple']),
        (11.2,"Token\nNode",         C['teal']),
        (13.2,"SmartRouter",         C['sky']),
        (15.2,"Exchange\nGateway",   C['delta']),
        (17.2,"Risk\nManager",       C['red']),
    ]
    for x,lbl,col in parts:
        box(ax,x-0.6,11.5,1.2,0.85,col,col,lbl,fs=7,radius=0.15)
        ax.plot([x,x],[11.5,0.4],color='#CBD5E1',lw=1,linestyle='--',zorder=1)

    def msg(x1,x2,y,lbl,col="#546E7A",ret=False,lw=1.4):
        ax.annotate("",xy=(x2,y),xytext=(x1,y),
            arrowprops=dict(arrowstyle="<|-" if ret else "-|>",color=col,lw=lw,
                            linestyle="dashed" if ret else "solid"))
        ax.text((x1+x2)/2,(y+0.08),lbl,ha='center',fontsize=6.2,color=col)

    def act(x,y,h,col):
        ax.add_patch(FancyBboxPatch((x-0.08,y-h),0.16,h,
                     boxstyle="square,pad=0",facecolor=col,edgecolor='white',lw=0.5,alpha=0.9,zorder=2))

    rows=[
        (1.2,3.2,  10.8,"POST /workflows/buy {symbol,exchange,qty,leverage}",     C['purple'],False),
        (3.2,5.2,  10.2,"OrderWorkflowEngine.execute(OrderRequest)",              C['blue'],  False),
        (5.2,7.2,   9.6,"validate_signal_node(state)",                             C['orange'],False),
        (7.2,5.2,   9.0,"signal_valid=True, SIGNAL_VALIDATED",                    "#4F46E5",  True),
        (5.2,9.2,   8.4,"check_risk_node(state)",                                 C['orange'],False),
        (9.2,17.2,  7.8,"RiskManager.evaluate(synthetic_signal)",                 C['purple'],False),
        (17.2,9.2,  7.2,"RiskVeto(vetoed=False, adjusted_pos=3%)",               C['red'],   True),
        (9.2,5.2,   6.6,"risk_approved=True, RISK_CHECKED",                       C['purple'],True),
        (5.2,11.2,  6.0,"verify_token_node(state) → TokenManager.get_token()",   C['orange'],False),
        (11.2,5.2,  5.4,"token_valid=True, TOKEN_VERIFIED",                       C['teal'],  True),
        (5.2,13.2,  4.8,"route_order_node → SmartRouter.route(request)",          C['orange'],False),
        (13.2,5.2,  4.2,"RoutingDecision(exchange='delta', score=0.87)",          C['sky'],   True),
        (5.2,15.2,  3.6,"place_order_node → DeltaGateway.place_order(BTCUSD,BUY)",C['orange'],False),
        (15.2,5.2,  3.0,"OrderResult(id=DX-98312, state=filled, price=68400)",   C['delta'], True),
        (5.2,5.2,   2.4,"monitor_order_node → FILLED @ 68400",                   C['orange'],False),
        (5.2,5.2,   1.8,"settle_order_node → PnL recorded → SETTLED",            C['green'], False),
        (5.2,3.2,   1.2,"OrderWorkflowState.to_summary()",                        C['orange'],True),
        (3.2,1.2,   0.8,"WorkflowResult + WebSocket broadcast 'order_filled'",   C['blue'],  True),
    ]
    for x1,x2,y,lbl,col,ret in rows:
        msg(x1,x2,y,lbl,col,ret)

    act(5.2,10.2,9.5,C['orange'])
    act(9.2, 7.8,0.8,C['purple'])
    act(17.2, 7.8,0.8,C['red'])
    act(15.2, 3.6,0.8,C['delta'])

    save(fig,"02_buy_sell_sequence")


# ══════════════════════════════════════════════════════════════════════════════
# 3 — TOKEN LIFECYCLE DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════
def d_token_lifecycle():
    fig,ax = plt.subplots(figsize=(17,11)); ax.set_xlim(0,17); ax.set_ylim(0,11)
    ax.axis('off'); fig.patch.set_facecolor("#F0F9FF")
    title(ax,"Alchemy — Exchange Token Lifecycle",
          "AES-256-GCM Vault · Per-exchange token types · Auto-refresh scheduler · Validation pipeline")

    # Central vault
    box(ax,6.5,4.5,4.0,2.0,C['navy'],"#00B0F0","TOKEN VAULT","AES-256-GCM Encrypted\n~/.alchemy/vault/",
        fs=10,radius=0.4,lw=3)

    # Token types around vault
    exchanges=[
        (0.5,8.5,3.5,1.6,C['blue'],"#1E40AF","KiteToken","api_key + access_token\nExpires 06:00 IST daily\nOAuth refresh flow"),
        (0.5,5.2,3.5,1.6,C['delta'],"#1E40AF","DeltaToken","api_key + api_secret\nHMAC-SHA256 signed\nRotate every 90 days"),
        (0.5,1.8,3.5,1.6,C['binance'],"#78350F","BinanceToken","api_key + api_secret\nX-MBX-APIKEY header\nIP whitelist recommended"),
        (13.0,5.2,3.5,1.6,C['red'],"#B71C1C","IBToken","TWS TCP session\nNo API token\nib-controller managed"),
    ]
    for x,y,w,h,fill,edge,lbl,sub in exchanges:
        box(ax,x,y,w,h,fill,edge,lbl,sub,fs=8,radius=0.2)
        # Arrow to vault
        cx = x+(3.5/2)
        vx = 8.5
        ax.annotate("",xy=(6.5 if cx<8.5 else 10.5,6.0),xytext=(cx if cx<8.5 else cx,y+h/2),
            arrowprops=dict(arrowstyle="<->",color="#94A3B8",lw=1.3,connectionstyle="arc3,rad=0.1"))

    # Token status states
    statuses = [
        (4.8,2.5,2.0,0.7,C['s_pending'],   "MISSING",    "Not configured"),
        (7.1,2.5,2.0,0.7,C['s_validated'], "ACTIVE",     "Valid + usable"),
        (9.4,2.5,2.0,0.7,C['s_monitoring'],"EXPIRING",   "< 1 hour left"),
        (4.8,1.3,2.0,0.7,C['s_error'],     "EXPIRED",    "Past expiry"),
        (7.1,1.3,2.0,0.7,C['s_rejected'],  "INVALID",    "Auth rejected"),
        (9.4,1.3,2.0,0.7,C['s_token'],     "REFRESHING", "Being renewed"),
    ]
    for x,y,w,h,fill,lbl,sub in statuses:
        box(ax,x,y,w,h,fill,fill,lbl,sub,fs=7,radius=0.15)

    # Auto-refresh scheduler
    box(ax,11.5,8.5,4.5,1.6,"#1C1917","#D97706","Auto-Refresh Scheduler",
        "Background thread · 30min interval\nTriggers on needs_refresh=True",fs=8,radius=0.25)

    # API endpoints
    box(ax,6.0,8.5,4.0,1.8,"#0F172A","#6366F1","Token REST API",
        "POST /tokens/register\nGET  /tokens/status\nPOST /tokens/{ex}/refresh\nPOST /tokens/{ex}/validate",
        fs=7,radius=0.25)

    arr(ax,8.0,8.5,8.0,6.5,C['purple'],lw=1.5,lbl="CRUD ops")
    arr(ax,13.75,8.5,13.75,6.8,C['amber'],lw=1.5,lbl="auto refresh")
    arr(ax,13.0,6.0,10.5,5.5,C['amber'],lw=1.2,rad=0.1)
    arr(ax,10.5,2.5,10.5,4.5,C['teal'],lw=1.0,lbl="states")

    # PBKDF2 key note
    box(ax,0.4,0.3,5.5,0.7,"#1C1917","#6366F1","Key Derivation","PBKDF2-HMAC-SHA256 · 260,000 iterations · Random 32-byte salt",fs=7,radius=0.15)
    arr(ax,3.15,1.0,3.15,0.3,C['purple'],lw=1.0)

    save(fig,"03_token_lifecycle")


# ══════════════════════════════════════════════════════════════════════════════
# 4 — SMART ROUTER DECISION FLOW
# ══════════════════════════════════════════════════════════════════════════════
def d_smart_router():
    fig,ax = plt.subplots(figsize=(16,11)); ax.set_xlim(0,16); ax.set_ylim(0,11)
    ax.axis('off'); fig.patch.set_facecolor("#F0FDF4")
    title(ax,"Alchemy — Smart Order Router Decision Flow",
          "Routes each order to best exchange · Liquidity · Fees · Token validity · Symbol availability")

    def diamond(ax,x,y,w,h,fill,edge,lbl,fs=8):
        pts = [(x+w/2,y+h),(x+w,y+h/2),(x+w/2,y),(x,y+h/2)]
        poly = plt.Polygon(pts,facecolor=fill,edgecolor=edge,lw=1.5,zorder=2)
        ax.add_patch(poly)
        ax.text(x+w/2,y+h/2,lbl,ha='center',va='center',fontsize=fs,
                fontweight='bold',color='white',zorder=3)

    # Entry
    box(ax,6.5,9.8,3.0,0.8,C['navy'],"#00B0F0","ORDER REQUEST","symbol, exchange, side, qty",fs=8)

    # Decision 1: Manual override?
    diamond(ax,6.2,8.4,3.6,1.0,C['orange'],"#BF360C","Manual Exchange?",fs=8)
    box(ax,11.5,8.4,3.5,1.0,"#1C1917","#6366F1","Direct Route","Use specified exchange",fs=8)
    arr(ax,9.8,8.9,11.5,8.9,C['orange'],lbl="Yes")
    arr(ax,8.0,8.4,8.0,7.6,C['gray'],lbl="No")

    # Decision 2: Symbol listed?
    diamond(ax,6.2,6.6,3.6,1.0,C['blue'],"#0D47A1","Symbol Listed?",fs=8)
    box(ax,11.5,6.6,3.5,1.0,C['red'],"#B71C1C","ValueError","Symbol not on any exchange",fs=8)
    arr(ax,9.8,7.1,11.5,7.1,C['red'],lbl="No")
    arr(ax,8.0,6.6,8.0,5.8,C['gray'],lbl="Yes")

    # Decision 3: Valid token?
    diamond(ax,6.2,4.8,3.6,1.0,C['teal'],"#006064","Token Active?",fs=8)
    box(ax,11.5,4.8,3.5,1.0,C['amber'],"#92400E","Warn + Continue","Paper mode fallback",fs=8)
    arr(ax,9.8,5.3,11.5,5.3,C['amber'],lbl="No token")
    arr(ax,8.0,4.8,8.0,4.0,C['gray'],lbl="Yes")

    # Score exchanges
    box(ax,6.2,3.0,3.6,0.8,C['sky'],"#01579B","Score Exchanges","Fee + Spread + Native + Paper",fs=8)
    arr(ax,8.0,3.0,8.0,2.3,C['sky'])

    # Select best
    box(ax,6.2,1.5,3.6,0.8,C['green'],"#1B5E20","Select Best Score","RoutingDecision{exchange, reason}",fs=8)
    arr(ax,8.0,1.5,8.0,0.8,C['green'])

    # Output
    box(ax,6.2,0.1,3.6,0.7,C['navy'],"#00B0F0","Return RoutingDecision","→ place_order_node",fs=8)

    # Scoring factors
    factors=[
        (0.3,3.5,2.5,0.7,C['sky'],"Taker Fee","Lower fee = higher score"),
        (0.3,2.5,2.5,0.7,C['teal'],"Bid-Ask Spread","Live orderbook fetch"),
        (0.3,1.5,2.5,0.7,C['blue'],"Native Listing","Symbol primary exchange"),
        (0.3,0.5,2.5,0.7,C['orange'],"Paper Mode","Dev/test preference"),
    ]
    for x,y,w,h,fill,lbl,sub in factors:
        box(ax,x,y,w,h,fill,fill,lbl,sub,fs=7,radius=0.15)
        arr(ax,2.8,y+0.35,6.2,3.4,C['gray'],lw=0.9)

    # Exchange outcomes
    outcomes=[
        (12.5,3.5,2.8,0.7,C['delta'],"→ Delta","BTC/ETH perps, MOVE"),
        (12.5,2.5,2.8,0.7,C['binance'],"→ Binance","USD-M Futures"),
        (12.5,1.5,2.8,0.7,C['blue'],"→ Kite","NSE/BSE equity"),
        (12.5,0.5,2.8,0.7,C['red'],"→ IB","US equities"),
    ]
    for x,y,w,h,fill,lbl,sub in outcomes:
        box(ax,x,y,w,h,fill,fill,lbl,sub,fs=7,radius=0.15)
        arr(ax,9.8,1.85,12.5,y+0.35,C['green'],lw=0.9)

    save(fig,"04_smart_router")


if __name__ == "__main__":
    print("Generating workflow UML diagrams…")
    d_state_machine()
    d_buy_sell_sequence()
    d_token_lifecycle()
    d_smart_router()
    print("All 4 diagrams generated!")
