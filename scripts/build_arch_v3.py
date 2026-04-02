"""
Build Alchemy v0.3 Complete Architecture Document
Covers all modules: tokens, workflows, crypto, frontend, AI agents.
"""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ARCH = Path("/home/claude/alchemy/docs/architecture")
WKFL = Path("/home/claude/alchemy/docs/workflows")
OUT  = Path("/mnt/user-data/outputs/Alchemy_Complete_Architecture_v3.docx")

NAVY=RGBColor(0x1B,0x3A,0x5C); BLUE=RGBColor(0x2E,0x75,0xB6); SKY=RGBColor(0x5B,0x9B,0xD5)
WHITE=RGBColor(0xFF,0xFF,0xFF); GRAY=RGBColor(0x60,0x7D,0x8B); GREEN=RGBColor(0x2E,0x7D,0x32)
RED=RGBColor(0xC6,0x28,0x28); ORANGE=RGBColor(0xE6,0x51,0x00); AMBER=RGBColor(0xFF,0xA0,0x00)
DGRAY=RGBColor(0x33,0x33,0x33); DELTA=RGBColor(0x1D,0x4E,0xD8); BNB=RGBColor(0xF5,0x9E,0x0B)
PURPLE=RGBColor(0x6A,0x1B,0x9A); TEAL=RGBColor(0x00,0x6D,0x6D); LGRAY=RGBColor(0xF5,0xF5,0xF5)

def shd(cell, hex_color):
    tc=cell._tc; p=tc.get_or_add_tcPr(); s=OxmlElement('w:shd')
    s.set(qn('w:val'),'clear'); s.set(qn('w:color'),'auto')
    s.set(qn('w:fill'),hex_color.upper()); p.append(s)

def cm(cell, t=80, b=80, l=120, r=120):
    tc=cell._tc; p=tc.get_or_add_tcPr(); m=OxmlElement('w:tcMar')
    for side,v in [('top',t),('bottom',b),('left',l),('right',r)]:
        el=OxmlElement(f'w:{side}'); el.set(qn('w:w'),str(v)); el.set(qn('w:type'),'dxa'); m.append(el)
    p.append(m)

def cw(cell, inches):
    tc=cell._tc; p=tc.get_or_add_tcPr(); w=OxmlElement('w:tcW')
    w.set(qn('w:w'),str(int(inches*1440))); w.set(qn('w:type'),'dxa'); p.append(w)

def hr(doc, color="2E75B6"):
    p=doc.add_paragraph(); pp=p._p.get_or_add_pPr()
    pb=OxmlElement('w:pBdr'); bot=OxmlElement('w:bottom')
    bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),'6')
    bot.set(qn('w:space'),'1'); bot.set(qn('w:color'),color)
    pb.append(bot); pp.append(pb)
    p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(6)

def h1(doc,t):
    p=doc.add_heading(t,1)
    for r in p.runs: r.font.color.rgb=NAVY; r.font.size=Pt(18); r.bold=True
    p.paragraph_format.space_before=Pt(18); p.paragraph_format.space_after=Pt(4)
    hr(doc)

def h2(doc,t):
    p=doc.add_heading(t,2)
    for r in p.runs: r.font.color.rgb=BLUE; r.font.size=Pt(14); r.bold=True
    p.paragraph_format.space_before=Pt(12); p.paragraph_format.space_after=Pt(4)

def h3(doc,t):
    p=doc.add_heading(t,3)
    for r in p.runs: r.font.color.rgb=GRAY; r.font.size=Pt(11); r.bold=True
    p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(2)

def para(doc, text, bold=False, color=None, size=10.5, italic=False):
    p=doc.add_paragraph(); r=p.add_run(text)
    r.font.size=Pt(size); r.bold=bold; r.italic=italic
    r.font.color.rgb=color or DGRAY
    p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(3)

def blt(doc, text):
    p=doc.add_paragraph(style='List Bullet')
    r=p.add_run(text); r.font.size=Pt(10); r.font.color.rgb=DGRAY
    p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(1)

def num(doc, text):
    p=doc.add_paragraph(style='List Number')
    r=p.add_run(text); r.font.size=Pt(10); r.font.color.rgb=DGRAY

def code(doc, text):
    p=doc.add_paragraph(); r=p.add_run(text)
    r.font.name='Courier New'; r.font.size=Pt(8.5)
    r.font.color.rgb=RGBColor(0x1B,0x3A,0x5C)
    p.paragraph_format.left_indent=Cm(0.8)
    p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(1)
    pp=p._p.get_or_add_pPr(); s=OxmlElement('w:shd')
    s.set(qn('w:val'),'clear'); s.set(qn('w:color'),'auto')
    s.set(qn('w:fill'),'F5F5F5'); pp.append(s)

def sp(doc, pts=8):
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(pts)

def pb(doc): doc.add_page_break()

def img(doc, path, width=6.0, caption=None):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    if Path(path).exists():
        p.add_run().add_picture(str(path), width=Inches(width))
    else:
        p.add_run(f"[Image: {path}]")
    p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(4)
    if caption:
        cap=doc.add_paragraph(caption); cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
        if cap.runs: cap.runs[0].font.size=Pt(9); cap.runs[0].italic=True; cap.runs[0].font.color.rgb=GRAY
        cap.paragraph_format.space_after=Pt(10)

def tbl(doc, headers, rows, widths, hbg="1B3A5C"):
    t=doc.add_table(rows=1+len(rows),cols=len(headers)); t.style='Table Grid'
    t.alignment=WD_TABLE_ALIGNMENT.CENTER
    hr_=t.rows[0]
    for i,(h,w) in enumerate(zip(headers,widths)):
        c=hr_.cells[i]; c.text=''
        r=c.paragraphs[0].add_run(h)
        r.bold=True; r.font.color.rgb=WHITE; r.font.size=Pt(9.5)
        shd(c,hbg); cm(c); cw(c,w); c.vertical_alignment=WD_ALIGN_VERTICAL.CENTER
    for ri,row in enumerate(rows):
        ro=t.rows[ri+1]; fill="F8F9FA" if ri%2==0 else "FFFFFF"
        for ci,(val,w) in enumerate(zip(row,widths)):
            c=ro.cells[ci]; c.text=''
            r=c.paragraphs[0].add_run(str(val))
            if ci==0: r.bold=True; r.font.color.rgb=NAVY; r.font.size=Pt(9); shd(c,"E3EFF8")
            else:     r.font.color.rgb=DGRAY; r.font.size=Pt(9); shd(c,fill)
            cm(c); cw(c,w)
    sp(doc,10)

def setup(doc):
    s=doc.sections[0]
    s.page_width=Inches(8.5); s.page_height=Inches(11)
    s.left_margin=s.right_margin=Inches(1.0)
    s.top_margin=s.bottom_margin=Inches(0.8)
    hdr=s.header; hp=hdr.paragraphs[0]; hp.clear()
    hp.add_run("ALCHEMY PLATFORM v0.3  |  Complete Architecture Document  |  Token Management + Workflows").font.size=Pt(8)
    hp.runs[0].font.color.rgb=GRAY; hp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    pp=hp._p.get_or_add_pPr(); pb_=OxmlElement('w:pBdr'); b=OxmlElement('w:bottom')
    b.set(qn('w:val'),'single'); b.set(qn('w:sz'),'4'); b.set(qn('w:space'),'1'); b.set(qn('w:color'),'2E75B6')
    pb_.append(b); pp.append(pb_)
    ftr=s.footer; fp=ftr.paragraphs[0]; fp.clear()
    fp.add_run("Alchemy Architecture v0.3  |  April 2026  |  Page ").font.size=Pt(8)
    fp.runs[0].font.color.rgb=GRAY
    f1=OxmlElement('w:fldChar'); f1.set(qn('w:fldCharType'),'begin')
    it=OxmlElement('w:instrText'); it.text=' PAGE '
    f3=OxmlElement('w:fldChar'); f3.set(qn('w:fldCharType'),'end')
    re_=OxmlElement('w:r'); re_.append(f1); re_.append(it); re_.append(f3)
    fp._p.append(re_); fp.alignment=WD_ALIGN_PARAGRAPH.CENTER

doc = Document()
setup(doc)

# ── COVER ─────────────────────────────────────────────────────────────────────
sp(doc, 100)
for txt,sz,col in [("🔮  ALCHEMY PLATFORM",30,NAVY),("Complete Architecture Document  v0.3",18,BLUE)]:
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(txt); r.bold=True; r.font.size=Pt(sz); r.font.color.rgb=col
hr(doc,"00B0F0")
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=p.add_run("Token Management  ·  Buy/Sell Workflow Engine  ·  Smart Order Router  ·  Crypto Execution  ·  React Dashboard")
r.font.size=Pt(10); r.italic=True; r.font.color.rgb=GRAY
sp(doc,30)

meta=[("Version","0.3.0 — Token Management + Order Workflow + Crypto Execution"),
      ("Repository","https://github.com/jaikumararjunan/alchemy"),
      ("Author","Jai  |  Principal AI Solution Architect"),
      ("Date","April 3, 2026"),
      ("Total Modules","17 Python modules + React frontend (10 pages)"),
      ("Test Coverage","62 unit tests · 100% passing"),
      ("UML Diagrams","12 diagrams (4 workflow + 8 architecture)")]
t=doc.add_table(rows=len(meta),cols=2); t.style='Table Grid'; t.alignment=WD_TABLE_ALIGNMENT.CENTER
for ri,(k,v) in enumerate(meta):
    cs=t.rows[ri].cells
    cs[0].text=''; r1=cs[0].paragraphs[0].add_run(k)
    r1.bold=True; r1.font.color.rgb=WHITE; r1.font.size=Pt(10)
    shd(cs[0],"1B3A5C"); cm(cs[0]); cw(cs[0],1.8)
    cs[1].text=''; r2=cs[1].paragraphs[0].add_run(v)
    r2.font.color.rgb=DGRAY; r2.font.size=Pt(10)
    shd(cs[1],"F0F4F8"); cm(cs[1]); cw(cs[1],5.2)
pb(doc)

# ── 1. EXECUTIVE SUMMARY ─────────────────────────────────────────────────────
h1(doc,"1. Executive Summary")
para(doc,"Alchemy v0.3 completes the platform with secure exchange token management, a LangGraph-powered order workflow engine with Smart Order Router, and 62 passing unit tests. The platform now covers the full trading lifecycle from AI signal generation to order execution across 4 exchanges.")
sp(doc,6)
h2(doc,"Complete Module Inventory — v0.3")
tbl(doc,["Module","Package","Key Capability","Version"],
    [("State + Config",     "alchemy.core",              "Pydantic v2 LangGraph schema, pydantic-settings",         "v0.1"),
     ("AI Agent Pipeline",  "alchemy.agents",            "LangGraph 5-node: news→sentiment→vol→decision",          "v0.1"),
     ("LLM Router",         "alchemy.llm",               "LiteLLM: 100+ providers, fallback, budget tracking",      "v0.1"),
     ("Portfolio Analytics","alchemy.analytics",         "pyfolio tear sheets + ARCH GARCH volatility engine",      "v0.1"),
     ("Market Data",        "alchemy.data",              "quantrautil adapter + Redis cache (NSE/BSE/US)",          "v0.1"),
     ("Strategy Factory",   "alchemy.strategy",          "Blueshift base class + SMA crossover template",           "v0.1"),
     ("Factor Pipeline",    "alchemy.pipeline",          "zipline-pipeline: universe screen + momentum factors",    "v0.1"),
     ("Risk Manager",       "alchemy.risk",              "Pre-trade: drawdown, vol-scale, daily loss, emergency stop","v0.1"),
     ("IB Gateway",         "alchemy.execution",         "Interactive Brokers ib_insync, paper mode",               "v0.1"),
     ("Kite Gateway",       "alchemy.execution",         "Zerodha Kite Connect NSE/BSE, CNC/MIS",                   "v0.1"),
     ("Delta Gateway",      "alchemy.execution.crypto",  "Delta Exchange: perps, options, MOVE, HMAC-SHA256",       "v0.2"),
     ("Binance Gateway",    "alchemy.execution.crypto",  "Binance: spot + USD-M futures + COIN-M, leverage",        "v0.2"),
     ("Token Models",       "alchemy.tokens",            "KiteToken/DeltaToken/BinanceToken/IBToken models",        "v0.3"),
     ("Token Vault",        "alchemy.tokens",            "AES-256-GCM encrypted storage, PBKDF2 key derivation",    "v0.3"),
     ("Token Manager",      "alchemy.tokens",            "Registry: register/validate/refresh/auto-rotate",         "v0.3"),
     ("Workflow States",    "alchemy.workflows",         "13-state LangGraph schema + guarded transitions",         "v0.3"),
     ("Workflow Engine",    "alchemy.workflows",         "9-node buy/sell pipeline: validate→risk→token→route→place","v0.3"),
     ("Smart Router",       "alchemy.workflows",         "Routes by fee + spread + token validity + listing",       "v0.3"),
     ("FastAPI App",        "alchemy.api",               "REST + WebSocket, CORS, static serving",                  "v0.3"),
     ("Crypto Routes",      "alchemy.api",               "16 Delta + Binance REST endpoints",                       "v0.2"),
     ("Token Routes",       "alchemy.api",               "Token CRUD + validate + refresh API",                     "v0.3"),
     ("React Dashboard",    "frontend/",                 "10 pages: Dashboard/Portfolio/Crypto/Tokens/Workflows",   "v0.3"),
    ],
    [1.8,1.6,3.4,0.7])
pb(doc)

# ── 2. WORKFLOW UML DIAGRAMS ──────────────────────────────────────────────────
h1(doc,"2. Workflow Architecture — UML Diagrams")
para(doc,"Four UML diagrams covering the complete order workflow: state machine, buy/sell sequence, token lifecycle, and smart router decision flow.")

workflow_diags = [
    ("2.1  Order Workflow State Machine", WKFL/"01_workflow_state_machine.png", 5.8,
     "Figure 1: 13-state LangGraph machine — happy path, error branches, and retry loop",
     "The state machine defines the complete lifecycle of every order. The happy path traverses 9 states: PENDING → SIGNAL_VALIDATED → RISK_CHECKED → TOKEN_VERIFIED → ROUTED → PLACED → MONITORING → FILLED → SETTLED. Three terminal error branches handle REJECTED (exchange declined), CANCELLED (risk/user/system triggered), and ERROR (exception raised). A retry loop allows up to 2 automatic retries from ERROR back to PENDING. All transitions are guarded — invalid transitions raise ValueError rather than silently succeeding."),
    ("2.2  Buy/Sell Order Sequence", WKFL/"02_buy_sell_sequence.png", 5.8,
     "Figure 2: Complete buy/sell sequence from React frontend through 9 workflow nodes to exchange",
     "The sequence traces a BUY order for BTCUSD. React POSTs to /workflows/buy. FastAPI invokes OrderWorkflowEngine.execute(). Each LangGraph node processes the state in sequence: validate_signal (symbol/qty/type validation), check_risk (RiskManager.evaluate() with synthetic TradingSignal), verify_token (TokenManager.get_token()), route_order (SmartRouter scores exchanges), place_order (DeltaGateway.place_order()), monitor_order (fill confirmation), settle_order (P&L recording). Final result is broadcast via WebSocket as 'order_filled' event to all connected frontend clients."),
    ("2.3  Token Lifecycle", WKFL/"03_token_lifecycle.png", 5.8,
     "Figure 3: Exchange token types, AES-256-GCM vault, status states, and auto-refresh scheduler",
     "Each exchange has a distinct token type with different authentication patterns. KiteToken uses OAuth with daily expiry at 06:00 IST — requires browser automation (Playwright) for auto-refresh. DeltaToken and BinanceToken are long-lived with per-request HMAC-SHA256 signing — rotate manually every 90 days. IBToken manages a TCP session with no API token. All tokens are stored in an AES-256-GCM encrypted vault with PBKDF2-HMAC-SHA256 key derivation (260,000 iterations). The background auto-refresh scheduler runs every 30 minutes and triggers refresh when seconds_to_expiry < 3600."),
    ("2.4  Smart Order Router", WKFL/"04_smart_router.png", 5.8,
     "Figure 4: Router decision flow — manual override → symbol lookup → token check → score → route",
     "The Smart Order Router follows a strict decision hierarchy. Step 1: manual override (request.exchange != 'auto') bypasses all scoring. Step 2: symbol lookup against SYMBOL_EXCHANGE_MAP — ValueError if not listed. Step 3: filter candidates by token validity — paper mode fallback if no valid tokens. Step 4: score each exchange by taker fee (lower = better), live bid-ask spread (tighter = better), native listing bonus, and paper mode preference. The highest-scoring exchange is chosen. RoutingDecision includes exchange, reason string, fee estimate, alternatives, and score."),
]

for title, path, width, caption, desc in workflow_diags:
    h2(doc, title)
    para(doc, desc, color=RGBColor(0x44,0x44,0x44))
    sp(doc,6)
    img(doc, path, width, caption)
    hr(doc,"5B9BD5"); sp(doc,4)
pb(doc)

# ── 3. ARCHITECTURE UML DIAGRAMS ─────────────────────────────────────────────
h1(doc,"3. Platform Architecture — UML Diagrams")
para(doc,"Eight C4/UML diagrams covering system context, component layers, crypto execution, frontend components, class relationships, and AWS deployment.")

arch_diags = [
    ("3.1  System Context (C4 L1)", ARCH/"01_system_context.png", 5.6,
     "Figure 5: Alchemy in its ecosystem — 4 exchange connections, LLM providers, React frontend, 3 actor types"),
    ("3.2  Component Architecture (C4 L2)", ARCH/"02_component_architecture.png", 5.6,
     "Figure 6: Six-layer decomposition — Frontend, AI Agent, Strategy, Analytics, Execution, Infrastructure"),
    ("3.3  Crypto Trade Sequence", ARCH/"03_sequence_crypto_trade.png", 5.6,
     "Figure 7: Full crypto trade lifecycle — React → LangGraph → GARCH → Risk → Delta + Binance"),
    ("3.4  Class Diagram", ARCH/"04_class_diagram.png", 5.6,
     "Figure 8: 10 core integration classes — state, router, strategy, analytics, crypto gateways, risk, agent"),
    ("3.5  Frontend Architecture", ARCH/"05_frontend_architecture.png", 5.6,
     "Figure 9: React component tree — main.jsx → App → Layout → 10 pages → shared API/store/hooks"),
    ("3.6  Crypto Execution Detail", ARCH/"06_crypto_execution.png", 5.6,
     "Figure 10: Delta Exchange + Binance side-by-side — endpoints, auth, products, paper mode"),
    ("3.7  AWS Deployment", ARCH/"07_deployment.png", 5.6,
     "Figure 11: AWS ap-south-1 — 4 EC2 instances, TimescaleDB, S3, SQS/SNS, Secrets Manager"),
    ("3.8  Module Dependency Map", ARCH/"08_module_dependency.png", 5.6,
     "Figure 12: Package dependency arrows — all 17 Python modules + React frontend"),
]

for title, path, width, caption in arch_diags:
    h2(doc, title)
    img(doc, path, width, caption)
    sp(doc,6)
pb(doc)

# ── 4. TOKEN MANAGEMENT ───────────────────────────────────────────────────────
h1(doc,"4. Exchange Token Management")
para(doc,"Secure credential lifecycle management for all 4 exchanges using AES-256-GCM encryption. The TokenManager provides a unified interface consumed by all gateways and the order workflow engine.")
sp(doc,6)

h2(doc,"4.1  Token Types")
tbl(doc,["Exchange","Class","Auth Pattern","Expiry","Refresh Method"],
    [("Zerodha Kite","KiteToken","OAuth access_token","Daily 06:00 IST","Browser login (Playwright)"),
     ("Delta Exchange","DeltaToken","HMAC-SHA256 per request","Long-lived","Manual rotation 90 days"),
     ("Binance","BinanceToken","X-MBX-APIKEY + HMAC","Long-lived","Manual rotation"),
     ("Interactive Brokers","IBToken","TCP session (no token)","Session-based","TWS reconnect"),
    ],
    [1.5,1.5,2.0,1.5,2.0])

h2(doc,"4.2  Vault Security")
for item in [
    "Encryption: AES-256-GCM authenticated encryption",
    "Key derivation: PBKDF2-HMAC-SHA256, 260,000 iterations (NIST SP 800-132 compliant)",
    "Salt: 32-byte random salt stored separately in ~/.alchemy/vault/.salt",
    "Master key: Set via ALCHEMY_VAULT_KEY env var (never committed to source control)",
    "Storage: ~/.alchemy/vault/{exchange}.enc — one file per exchange",
    "Key rotation: vault.rotate_key(new_key) re-encrypts all tokens atomically",
]:
    blt(doc, item)

h2(doc,"4.3  REST API — Token Endpoints")
tbl(doc,["Method","Endpoint","Body / Params","Response"],
    [("POST","  /tokens/register",    "exchange, api_key, api_secret, paper_mode","Token status (secrets redacted)"),
     ("GET", "  /tokens/status",      "—",                                         "All exchanges: status, expiry, use_count"),
     ("GET", "  /tokens/status/{ex}", "—",                                         "Single exchange status"),
     ("POST","  /tokens/{ex}/validate","—",                                         "{ok, message}"),
     ("POST","  /tokens/{ex}/refresh", "—",                                         "{ok, exchange}"),
     ("DELETE","  /tokens/{ex}",       "—",                                         "{ok, exchange}"),
     ("PUT", "  /tokens/kite/access-token","access_token",                          "{ok, message}"),
     ("GET", "  /tokens/history",      "limit=20",                                  "Refresh event log"),
     ("POST","  /tokens/validate-all", "—",                                         "{exchange: valid}"),
    ],
    [0.7,2.2,2.2,2.9])

h2(doc,"4.4  Usage Example")
for line in [
    "from alchemy.tokens.models import DeltaToken, BinanceToken, KiteToken",
    "from alchemy.tokens.manager import get_token_manager",
    "",
    "manager = get_token_manager()",
    "",
    "# Register Delta Exchange (paper mode)",
    "manager.register(DeltaToken(",
    "    api_key='your_delta_api_key',",
    "    api_secret='your_delta_secret',",
    "    testnet=True, paper_mode=True",
    "))",
    "",
    "# Get validated token before placing order",
    "token = manager.get_token(ExchangeID.DELTA)    # raises TokenError if invalid",
    "",
    "# Check all token statuses",
    "status = manager.status()   # safe — no secrets exposed",
    "print(status['delta']['status'])   # 'active' | 'expiring' | 'expired' | 'missing'",
    "",
    "# Start background auto-refresh (call once at startup)",
    "manager.start_auto_refresh()   # daemon thread, 30-min check interval",
]:
    code(doc, line)
pb(doc)

# ── 5. ORDER WORKFLOW ENGINE ──────────────────────────────────────────────────
h1(doc,"5. Order Workflow Engine")
para(doc,"LangGraph state machine that every buy/sell order passes through. Provides validation, risk gating, token verification, smart routing, and execution in a fully auditable, retry-capable pipeline.")
sp(doc,6)

h2(doc,"5.1  Workflow Nodes")
tbl(doc,["Node","Function","State Transition","Key Logic"],
    [("validate_signal", "validate_signal_node()", "PENDING → SIGNAL_VALIDATED",
      "Symbol non-empty, qty bounds, order_type supported, price fields present, leverage 1–125"),
     ("check_risk",      "check_risk_node()",       "SIGNAL_VALIDATED → RISK_CHECKED",
      "RiskManager.evaluate(synthetic_signal) — drawdown, vol, daily loss, position count"),
     ("verify_token",    "verify_token_node()",     "RISK_CHECKED → TOKEN_VERIFIED",
      "TokenManager.get_token(exchange) — raises TokenError if expired or missing"),
     ("route_order",     "route_order_node()",      "TOKEN_VERIFIED → ROUTED",
      "SmartRouter.route(request) — scores by fee, spread, token, native listing"),
     ("place_order",     "place_order_node()",      "ROUTED → PLACED",
      "_execute_on_exchange() dispatches to delta/binance/kite/ib gateway"),
     ("monitor_order",   "monitor_order_node()",    "PLACED → MONITORING → FILLED",
      "Market orders: immediate fill. Limit orders: PARTIALLY_FILLED pending"),
     ("settle_order",    "settle_order_node()",     "FILLED → SETTLED",
      "Record fill price, calculate P&L (sell side), update workflow audit trail"),
     ("handle_error",    "handle_error_node()",     "ERROR → PENDING (retry)",
      "Up to max_retries=2 automatic retries. After limit: stays in ERROR state"),
    ],
    [1.5,2.0,2.3,2.2])

h2(doc,"5.2  Smart Order Router Scoring")
tbl(doc,["Factor","Weight","Logic"],
    [("Taker Fee",      "High",   "score -= fee × 100. Delta: 0.05%, Binance: 0.04%, Kite: 0.03%, IB: 0.10%"),
     ("Bid-Ask Spread", "High",   "score += max(0, 0.5 - spread×100). Fetched live from exchange order book"),
     ("Native Listing", "Medium", "score += 0.5 if symbol's primary exchange. Avoids unnecessary routing"),
     ("Paper Mode",     "Low",    "score += 0.2 if exchange token is in paper mode. Prefer consistent dev env"),
    ],
    [1.5,1.0,5.5])

h2(doc,"5.3  Usage Example")
for line in [
    "from alchemy.workflows.engine import buy, sell, OrderWorkflowEngine",
    "from alchemy.workflows.states import OrderRequest, OrderSide, OrderType",
    "",
    "# Simple buy — async",
    "result = await buy('BTCUSD', exchange='auto', quantity=1, leverage=5)",
    "print(result.status.value)     # 'settled'",
    "print(result.routed_to)        # 'delta'",
    "print(result.fill_price)       # 68400.0",
    "print(result.duration_ms)      # 423.1",
    "",
    "# Sell with limit order",
    "result = await sell('ETHUSDT', exchange='binance', quantity=0.5,",
    "                     order_type=OrderType.LIMIT, limit_price=3900.0)",
    "",
    "# Full workflow engine with history",
    "engine = OrderWorkflowEngine()",
    "request = OrderRequest(symbol='RELIANCE', exchange='kite',",
    "                        side=OrderSide.BUY, quantity=10,",
    "                        order_type=OrderType.MARKET)",
    "result = await engine.execute(request)",
    "history = engine.get_history(limit=10)",
]:
    code(doc, line)
pb(doc)

# ── 6. TEST COVERAGE ──────────────────────────────────────────────────────────
h1(doc,"6. Test Coverage — 62 Tests · 100% Passing")
h2(doc,"6.1  Test Summary")
tbl(doc,["Test File","Tests","Covers"],
    [("tests/unit/test_core.py",                   "27","AlchemyTradingState, RiskManager, VolatilityEngine, PortfolioAnalytics"),
     ("tests/unit/crypto/test_gateways.py",         "16","DeltaGateway (paper, signing, context), BinanceGateway (paper, sign, qty)"),
     ("tests/unit/workflows/test_token_workflow.py","19","TokenVault, TokenModels, TokenManager, WorkflowStates, validate_signal node"),
    ],
    [3.5,0.7,4.8])

h2(doc,"6.2  Run Tests")
for line in ["# Install dependencies","pip install pytest pytest-asyncio arch cryptography pydantic langgraph","",
             "# Run all unit tests","pytest tests/unit/ -v",
             "","# With coverage report","pytest tests/unit/ --cov=alchemy --cov-report=html"]:
    code(doc, line)
pb(doc)

# ── 7. API REFERENCE ──────────────────────────────────────────────────────────
h1(doc,"7. Complete REST API Reference  (v0.3)")
h2(doc,"7.1  Core Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("GET","  /health","Platform health check — version, env"),
     ("POST","  /signal","Run LangGraph AI agent → TradingSignal + WebSocket broadcast"),
     ("WS",  "  /ws",   "Real-time WebSocket: signal · risk_alert · price_tick · order_filled"),
    ],
    [0.7,2.2,5.1])

h2(doc,"7.2  Risk Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("GET",    "  /risk/status","Current risk manager state"),
     ("POST",   "  /risk/emergency-stop","Activate emergency stop — halts all trading"),
     ("DELETE", "  /risk/emergency-stop","Clear emergency stop"),
     ("POST",   "  /risk/block","Block a ticker: {ticker: 'BTCUSD'}"),
    ],
    [0.7,2.2,5.1])

h2(doc,"7.3  Token Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("POST","  /tokens/register",           "Register exchange credentials (encrypted in vault)"),
     ("GET", "  /tokens/status",             "All exchange token statuses — secrets always redacted"),
     ("POST","  /tokens/{ex}/validate",       "Validate token against live exchange API (async)"),
     ("POST","  /tokens/{ex}/refresh",        "Manual token refresh"),
     ("DELETE","  /tokens/{ex}",              "Remove token from vault"),
     ("PUT", "  /tokens/kite/access-token",  "Update Kite access_token after OAuth login"),
    ],
    [0.7,2.5,4.8])

h2(doc,"7.4  Workflow Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("POST","  /workflows/buy",           "Execute buy — full 9-node pipeline"),
     ("POST","  /workflows/sell",          "Execute sell — full 9-node pipeline"),
     ("GET", "  /workflows/history",       "Recent workflow executions (default last 50)"),
     ("GET", "  /workflows/states",        "State machine definition: states, transitions, terminals"),
     ("GET", "  /workflows/route-preview", "Preview routing without execution: ?symbol=BTCUSD&exchange=auto"),
    ],
    [0.7,2.5,4.8])

h2(doc,"7.5  Crypto Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("GET", "  /crypto/delta/ticker/{symbol}",  "Delta live ticker — mark price, funding, OI"),
     ("GET", "  /crypto/delta/positions",        "Open margined positions"),
     ("POST","  /crypto/delta/order",            "Place Delta order"),
     ("GET", "  /crypto/binance/ticker/{symbol}","Binance 24hr ticker"),
     ("GET", "  /crypto/binance/klines/{symbol}","OHLCV klines (interval, limit params)"),
     ("POST","  /crypto/binance/order",          "Place Binance spot/futures order"),
     ("POST","  /crypto/binance/close/{symbol}", "Market-close entire Binance position"),
    ],
    [0.7,2.8,4.5])
pb(doc)

# ── 8. QUICK START ────────────────────────────────────────────────────────────
h1(doc,"8. Quick Start — v0.3")
h2(doc,"8.1  Backend")
for i,line in enumerate([
    "git clone https://github.com/jaikumararjunan/alchemy.git && cd alchemy",
    "python -m venv .venv && source .venv/bin/activate",
    "pip install -r requirements.txt",
    "pip install cryptography arch pydantic-settings langgraph",
    "cp config/settings.example.yaml config/settings.yaml",
    "export ALCHEMY_VAULT_KEY='your-secure-32-char-key-here'",
    "uvicorn alchemy.api.app:app --reload --port 8000",
],1):
    p=doc.add_paragraph(style='List Number'); p.add_run(line).font.name='Courier New'
    p.runs[0].font.size=Pt(8.5); p.paragraph_format.space_before=Pt(2)

h2(doc,"8.2  Register Exchange Tokens")
for line in [
    "# Register Delta Exchange (paper/testnet mode)",
    'curl -X POST http://localhost:8000/tokens/register \\',
    '  -H "Content-Type: application/json" \\',
    '  -d \'{"exchange":"delta","api_key":"your_key","api_secret":"your_secret","paper_mode":true}\'',
    "",
    "# Register Binance (paper mode)",
    '  -d \'{"exchange":"binance","api_key":"your_key","api_secret":"your_secret","paper_mode":true}\'',
]:
    code(doc, line)

h2(doc,"8.3  Execute a Buy/Sell Workflow")
for line in [
    "# BUY 1 BTCUSD perpetual on Delta Exchange (auto-routed)",
    'curl -X POST http://localhost:8000/workflows/buy \\',
    '  -H "Content-Type: application/json" \\',
    '  -d \'{"symbol":"BTCUSD","exchange":"auto","side":"buy","quantity":1,"leverage":5}\'',
    "",
    "# Response:",
    '{"workflow_id":"WF-A3B2C1D4E5F6","symbol":"BTCUSD","status":"settled",',
    ' "routed_to":"delta","fill_price":68400.0,"fill_quantity":1.0,',
    ' "duration_ms":423.1,"steps":[...]}',
    "",
    "# Preview routing before executing",
    'curl "http://localhost:8000/workflows/route-preview?symbol=BTCUSD&exchange=auto&side=buy"',
]:
    code(doc, line)

h2(doc,"8.4  Frontend")
for line in ["cd frontend","npm install","npm run dev   # → http://localhost:3000",
             "# Navigate to /tokens to manage exchange credentials",
             "# Navigate to /workflows to execute buy/sell orders"]:
    code(doc, line)

# Save
doc.save(str(OUT))
print(f"✅ Saved: {OUT}")
print(f"   Size: {OUT.stat().st_size/1024:.0f} KB")
