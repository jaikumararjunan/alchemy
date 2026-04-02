"""
Build Alchemy v0.2 Architecture Document using python-docx.
Covers: Frontend, Crypto (Delta + Binance), all 8 UML diagrams.
"""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ARCH = Path("/home/claude/alchemy/docs/architecture")
OUT  = Path("/mnt/user-data/outputs/Alchemy_Architecture_Document_v2.docx")

# ── colours ───────────────────────────────────────────────────────────────────
NAVY   = RGBColor(0x1B, 0x3A, 0x5C)
BLUE   = RGBColor(0x2E, 0x75, 0xB6)
SKY    = RGBColor(0x5B, 0x9B, 0xD5)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
GRAY   = RGBColor(0x60, 0x7D, 0x8B)
GREEN  = RGBColor(0x2E, 0x7D, 0x32)
RED    = RGBColor(0xC6, 0x28, 0x28)
ORANGE = RGBColor(0xE6, 0x51, 0x00)
AMBER  = RGBColor(0xFF, 0xA0, 0x00)
DGRAY  = RGBColor(0x33, 0x33, 0x33)
DELTA  = RGBColor(0x1D, 0x4E, 0xD8)
BNB    = RGBColor(0xF5, 0x9E, 0x0B)
PURPLE = RGBColor(0x6A, 0x1B, 0x9A)
LGRAY  = RGBColor(0xF5, 0xF5, 0xF5)


def set_cell_bg(cell, hex_color):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
    shd.set(qn('w:fill'), hex_color.upper()); tcPr.append(shd)

def cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr()
    mar = OxmlElement('w:tcMar')
    for s,v in [('top',top),('bottom',bottom),('left',left),('right',right)]:
        el = OxmlElement(f'w:{s}'); el.set(qn('w:w'),str(v)); el.set(qn('w:type'),'dxa'); mar.append(el)
    tcPr.append(mar)

def col_width(cell, inches):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr()
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:w'), str(int(inches*1440))); tcW.set(qn('w:type'),'dxa'); tcPr.append(tcW)

def hr(doc, color="2E75B6", space_b=4, space_a=8):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bot  = OxmlElement('w:bottom')
    bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),'6')
    bot.set(qn('w:space'),'1');    bot.set(qn('w:color'),color)
    pBdr.append(bot); pPr.append(pBdr)
    p.paragraph_format.space_before = Pt(space_b)
    p.paragraph_format.space_after  = Pt(space_a)

def h1(doc, text):
    p = doc.add_heading(text, level=1)
    for r in p.runs: r.font.color.rgb=NAVY; r.font.size=Pt(18); r.bold=True
    p.paragraph_format.space_before=Pt(18); p.paragraph_format.space_after=Pt(4)
    hr(doc)

def h2(doc, text):
    p = doc.add_heading(text, level=2)
    for r in p.runs: r.font.color.rgb=BLUE; r.font.size=Pt(14); r.bold=True
    p.paragraph_format.space_before=Pt(12); p.paragraph_format.space_after=Pt(4)

def h3(doc, text):
    p = doc.add_heading(text, level=3)
    for r in p.runs: r.font.color.rgb=GRAY; r.font.size=Pt(11); r.bold=True
    p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(2)

def para(doc, text, bold=False, color=None, size=10.5, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size=Pt(size); r.bold=bold; r.italic=italic
    r.font.color.rgb = color or DGRAY
    p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(3)

def bullet(doc, text):
    p = doc.add_paragraph(style='List Bullet')
    r = p.add_run(text); r.font.size=Pt(10); r.font.color.rgb=DGRAY
    p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(1)

def numbered(doc, text):
    p = doc.add_paragraph(style='List Number')
    r = p.add_run(text); r.font.size=Pt(10); r.font.color.rgb=DGRAY

def code_line(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name='Courier New'; r.font.size=Pt(8.5)
    r.font.color.rgb=RGBColor(0x1B,0x3A,0x5C)
    p.paragraph_format.left_indent=Cm(0.8)
    p.paragraph_format.space_before=Pt(1); p.paragraph_format.space_after=Pt(1)
    pPr=p._p.get_or_add_pPr()
    shd=OxmlElement('w:shd'); shd.set(qn('w:val'),'clear')
    shd.set(qn('w:color'),'auto'); shd.set(qn('w:fill'),'F5F5F5'); pPr.append(shd)

def spacer(doc, pts=8):
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(pts)

def page_break(doc): doc.add_page_break()

def img(doc, path, width=6.0, caption=None):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))
    p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(4)
    if caption:
        cap=doc.add_paragraph(caption)
        cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for r in cap.runs: pass
        r2=cap.add_run('') if not cap.runs else cap.runs[0]
        cap.runs[0].font.size=Pt(9); cap.runs[0].italic=True
        cap.runs[0].font.color.rgb=GRAY
        cap.paragraph_format.space_after=Pt(12)

def tbl(doc, headers, rows, widths, hdr_bg="1B3A5C"):
    t=doc.add_table(rows=1+len(rows), cols=len(headers))
    t.style='Table Grid'; t.alignment=WD_TABLE_ALIGNMENT.CENTER
    hr_=t.rows[0]
    for i,(h,w) in enumerate(zip(headers,widths)):
        c=hr_.cells[i]; c.text=''
        r=c.paragraphs[0].add_run(h)
        r.bold=True; r.font.color.rgb=WHITE; r.font.size=Pt(9.5)
        set_cell_bg(c,hdr_bg); cell_margins(c); col_width(c,w)
        c.vertical_alignment=WD_ALIGN_VERTICAL.CENTER
    for ri,row in enumerate(rows):
        ro=t.rows[ri+1]
        fill="F8F9FA" if ri%2==0 else "FFFFFF"
        for ci,(val,w) in enumerate(zip(row,widths)):
            c=ro.cells[ci]; c.text=''
            r=c.paragraphs[0].add_run(str(val))
            if ci==0:
                r.bold=True; r.font.color.rgb=NAVY; r.font.size=Pt(9)
                set_cell_bg(c,"E3EFF8")
            else:
                r.font.color.rgb=DGRAY; r.font.size=Pt(9)
                set_cell_bg(c,fill)
            cell_margins(c); col_width(c,w)
    spacer(doc,10)

def setup(doc):
    s=doc.sections[0]
    s.page_width=Inches(8.5); s.page_height=Inches(11)
    s.left_margin=s.right_margin=Inches(1.0)
    s.top_margin=s.bottom_margin=Inches(0.8)
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    # Header
    hdr=s.header; hp=hdr.paragraphs[0]; hp.clear()
    hp.add_run("ALCHEMY PLATFORM v0.2  |  Architecture Document  |  Frontend + Crypto + AI Trading").font.size=Pt(8)
    hp.runs[0].font.color.rgb=GRAY; hp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    pPr=hp._p.get_or_add_pPr(); pBdr=OxmlElement('w:pBdr')
    bot=OxmlElement('w:bottom'); bot.set(qn('w:val'),'single')
    bot.set(qn('w:sz'),'4'); bot.set(qn('w:space'),'1'); bot.set(qn('w:color'),'2E75B6')
    pBdr.append(bot); pPr.append(pBdr)
    # Footer
    ftr=s.footer; fp=ftr.paragraphs[0]; fp.clear()
    fp.add_run("Alchemy Architecture Document  |  April 2026  |  Page ").font.size=Pt(8)
    fp.runs[0].font.color.rgb=GRAY
    fld1=OxmlElement('w:fldChar'); fld1.set(qn('w:fldCharType'),'begin')
    it=OxmlElement('w:instrText'); it.text=' PAGE '
    fld3=OxmlElement('w:fldChar'); fld3.set(qn('w:fldCharType'),'end')
    re_=OxmlElement('w:r'); re_.append(fld1); re_.append(it); re_.append(fld3)
    fp._p.append(re_)
    fp.alignment=WD_ALIGN_PARAGRAPH.CENTER

# ── BUILD ─────────────────────────────────────────────────────────────────────

doc = Document()
setup(doc)

# ── COVER ─────────────────────────────────────────────────────────────────────
spacer(doc,100)
for txt,sz,col in [
    ("🔮  ALCHEMY PLATFORM", 30, NAVY),
    ("Architecture Document  v0.2", 18, BLUE),
]:
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(txt); r.bold=True; r.font.size=Pt(sz); r.font.color.rgb=col

hr(doc,"00B0F0",4,10)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=p.add_run("React Dashboard  ·  Delta Exchange  ·  Binance  ·  LangGraph AI Agents  ·  QuantInsti Analytics")
r.font.size=Pt(10); r.italic=True; r.font.color.rgb=GRAY
spacer(doc,30)

meta=[("Product","Alchemy AI-Powered Algorithmic Trading Platform"),
      ("Version","0.2.0 — Frontend + Crypto Integration"),
      ("Author","Jai  |  Principal AI Solution Architect"),
      ("Repo","https://github.com/jaikumararjunan/alchemy"),
      ("Date","April 3, 2026"),
      ("Stack","Python 3.12 · FastAPI · React 18 · Vite · LangGraph · LiteLLM")]
t=doc.add_table(rows=len(meta),cols=2); t.style='Table Grid'
t.alignment=WD_TABLE_ALIGNMENT.CENTER
for ri,(k,v) in enumerate(meta):
    cs=t.rows[ri].cells
    cs[0].text=''; r1=cs[0].paragraphs[0].add_run(k)
    r1.bold=True; r1.font.color.rgb=WHITE; r1.font.size=Pt(10)
    set_cell_bg(cs[0],"1B3A5C"); cell_margins(cs[0]); col_width(cs[0],1.8)
    cs[1].text=''; r2=cs[1].paragraphs[0].add_run(v)
    r2.font.color.rgb=DGRAY; r2.font.size=Pt(10)
    set_cell_bg(cs[1],"F0F4F8"); cell_margins(cs[1]); col_width(cs[1],5.2)

page_break(doc)

# ── 1. EXECUTIVE SUMMARY ──────────────────────────────────────────────────────
h1(doc,"1. Executive Summary")
para(doc,"Alchemy v0.2 extends the initial platform with a production-grade React dashboard, Delta Exchange crypto derivatives gateway, and Binance spot/futures adapter. This document covers the complete architecture of all 14 modules across 6 layers with 8 UML diagrams.")
spacer(doc,6)
h2(doc,"What's New in v0.2")
for x in ["React 18 frontend — 8-page dashboard with live WebSocket feed, portfolio analytics, crypto trading panel",
           "Delta Exchange gateway — perpetual futures, options, MOVE contracts with HMAC-SHA256 auth",
           "Binance gateway — spot trading, USD-M futures, COIN-M futures with leverage control",
           "Crypto FastAPI routes — /crypto/delta/* and /crypto/binance/* REST endpoints",
           "WebSocket broadcast — real-time signal, risk alert, order fill events pushed to frontend",
           "8 new UML diagrams — updated system context, component diagram, crypto sequence, frontend architecture, module map"]:
    bullet(doc,x)

spacer(doc,8)
h2(doc,"Complete Module Inventory")
tbl(doc,["Module","Layer","Key File(s)","Source / Pattern"],
    [("AlchemyTradingState",       "Core",      "core/state.py",               "Pydantic v2 BaseModel — LangGraph schema"),
     ("AlchemyConfig",             "Core",      "core/config.py",              "pydantic-settings — env + yaml"),
     ("AlchemyLLMRouter",          "AI",        "llm/router.py",               "litellm fork — 100+ providers"),
     ("LangGraph Agent Pipeline",  "AI",        "agents/graph.py",             "AI-in-Trading-Workflow"),
     ("AlchemyStrategyBase",       "Strategy",  "strategy/base.py",            "blueshift-developer-kit"),
     ("SMACrossoverStrategy",      "Strategy",  "strategy/sma_crossover.py",   "blueshift-demo-strategies"),
     ("AlchemyPipelineScreen",     "Strategy",  "pipeline/screen.py",          "zipline-pipeline"),
     ("VolatilityEngine",          "Analytics", "analytics/volatility.py",     "arch (GARCH/EGARCH)"),
     ("PortfolioAnalytics",        "Analytics", "analytics/portfolio.py",      "pyfolio (Quantopian fork)"),
     ("MarketDataAdapter",         "Data",      "data/adapter.py",             "quantrautil + Redis"),
     ("IBGateway",                 "Execution", "execution/ib_gateway.py",     "ib-controller + ib_insync"),
     ("KiteGateway",               "Execution", "execution/kite_gateway.py",   "kiteconnect3 → Python"),
     ("DeltaGateway",              "Crypto",    "execution/crypto/delta_gateway.py",   "Delta Exchange API v2"),
     ("BinanceGateway",            "Crypto",    "execution/crypto/binance_gateway.py", "Binance REST API"),
     ("RiskManager",               "Risk",      "risk/manager.py",             "Live-Algo-Trading-Setups"),
     ("FastAPI App",               "API",       "api/app.py",                  "FastAPI + WebSocket"),
     ("Crypto Router",             "API",       "api/crypto_routes.py",        "FastAPI APIRouter"),
     ("React Dashboard",           "Frontend",  "frontend/src/",               "React 18 + Vite + Tailwind"),
    ],
    [2.0,1.0,2.2,2.8])

page_break(doc)

# ── 2. UML DIAGRAMS ───────────────────────────────────────────────────────────
h1(doc,"2. UML Architecture Diagrams")
para(doc,"Eight UML diagrams covering all architectural concerns: C4 context/component, trade sequence, class relationships, frontend components, crypto execution detail, AWS deployment, and module dependencies.")

diagrams=[
    ("2.1  System Context (C4 Level 1)",
     ARCH/"01_system_context.png", 5.8,
     "Figure 1: Alchemy in ecosystem — actors, brokers (IB/Kite/Delta/Binance), LLM providers, QuantInsti libs, React frontend",
     "Updated System Context now shows four broker/exchange connections: Interactive Brokers (US equities), Zerodha Kite (NSE/BSE India), Delta Exchange (crypto perpetuals + options), and Binance (spot + USD-M futures). The React Frontend is shown as an external system consuming the FastAPI REST and WebSocket endpoints."),
    ("2.2  Component Architecture (C4 Level 2)",
     ARCH/"02_component_architecture.png", 5.8,
     "Figure 2: Six-layer decomposition — Frontend, AI Agent, Strategy, Analytics, Execution, Infrastructure",
     "The component diagram now shows six horizontal layers. The new Frontend Layer hosts the React Dashboard, Crypto Panel (Delta + Binance), Risk Monitor, Analytics View, and Strategy Builder. The Execution Layer is expanded with DeltaGateway and BinanceGateway alongside the existing IB and Kite connectors. All layers communicate via vertical arrows representing data flow and service calls."),
    ("2.3  Crypto Trade Sequence Diagram",
     ARCH/"03_sequence_crypto_trade.png", 5.8,
     "Figure 3: Full crypto trade lifecycle — React frontend → LangGraph → GARCH → Risk → Delta + Binance",
     "The sequence diagram traces a complete crypto trade lifecycle. The React frontend POSTs to /signal, FastAPI invokes the LangGraph agent, which calls LiteLLM for sentiment analysis, then the GARCH Volatility Engine for regime classification, then the Decision Agent for signal generation. The Risk Manager validates the signal before the execution layer places orders on both Delta Exchange and Binance simultaneously. Order confirmations are broadcast via WebSocket to the frontend."),
    ("2.4  Class Diagram",
     ARCH/"04_class_diagram.png", 5.8,
     "Figure 4: 10 core classes — state, router, strategy, analytics, crypto gateways, risk, agent",
     "The class diagram shows 10 core integration classes. DeltaGateway and BinanceGateway are new additions, both inheriting from a common paper-trading pattern. AlchemyTradingAgent (LangGraph) uses VolatilityEngine for GARCH vol, AlchemyLLMRouter for sentiment/decision LLM calls, and triggers IBGateway/KiteGateway/DeltaGateway/BinanceGateway through RiskManager validation."),
    ("2.5  Frontend Component Architecture",
     ARCH/"05_frontend_architecture.png", 5.8,
     "Figure 5: React component tree — main.jsx → App → Layout → 7 pages → shared API/store/hooks",
     "The frontend architecture shows the React component hierarchy from main.jsx (React StrictMode entry) through App.jsx (BrowserRouter + Routes) to Layout.jsx (sidebar + topbar + outlet), then branching into 7 page components. All pages share api/client.js (axios endpoints), store/index.js (Zustand global state), and useAlchemySocket (Socket.IO live feed). The CryptoPage uniquely uses both Delta and Binance API endpoints."),
    ("2.6  Crypto Execution Layer",
     ARCH/"06_crypto_execution.png", 5.8,
     "Figure 6: Delta Exchange + Binance gateway detail — endpoints, auth, paper mode, products",
     "The crypto execution diagram provides a detailed view of both gateways side by side. Delta Exchange supports perpetual futures (BTCUSD, ETHUSD, SOLUSD, BNBUSD), options (calls and puts), MOVE contracts, and spot markets. Binance supports spot trading (300+ pairs), USD-M perpetual futures, and COIN-M delivery futures. Both gateways implement HMAC-SHA256 request signing, testnet support, and paper trading mode with live price simulation."),
    ("2.7  AWS Deployment Architecture",
     ARCH/"07_deployment.png", 5.8,
     "Figure 7: AWS ap-south-1 (Mumbai) — 4 EC2 instances, RDS, S3, SQS/SNS, Secrets Manager",
     "The deployment diagram shows Alchemy running on AWS ap-south-1. Four EC2 instances: Frontend+API (t3.large — FastAPI + React static files), AI Gateway (t3.xlarge — LangGraph + LiteLLM + Redis), Execution (c5.large — all broker gateways + Risk Manager), and ML (r6i.xlarge — GARCH workers + factor pipeline + ML model serving). Persistent stores: TimescaleDB for time-series data, S3/CloudFront for pyfolio reports and React build, SQS/SNS for trade event routing."),
    ("2.8  Module Dependency Map",
     ARCH/"08_module_dependency.png", 5.8,
     "Figure 8: Package structure and inter-module dependency arrows across all 12 Python + Frontend modules",
     "The module dependency map shows how all 12 modules relate. alchemy.core is the root dependency (config + state). alchemy.agents depends on llm, analytics, and data. alchemy.api exposes all modules as REST endpoints and includes the new crypto_routes. The frontend communicates exclusively through alchemy.api via REST and WebSocket. alchemy.risk is consumed by the execution layer as a gate before any order reaches a broker."),
]

for sec_title, img_path, width, caption, desc in diagrams:
    h2(doc, sec_title)
    para(doc, desc, color=RGBColor(0x44,0x44,0x44))
    spacer(doc,6)
    if img_path.exists():
        img(doc, img_path, width, caption=caption)
    else:
        para(doc, f"[Diagram not found: {img_path}]", color=RED)
    hr(doc,"5B9BD5")
    spacer(doc,4)

page_break(doc)

# ── 3. FRONTEND ARCHITECTURE ──────────────────────────────────────────────────
h1(doc,"3. Frontend Architecture")
para(doc,"A full-featured React 18 dashboard built with Vite, Tailwind CSS, Zustand state management, React Query for server state, and Socket.IO for real-time WebSocket data.")

h2(doc,"3.1  Technology Stack")
tbl(doc,["Layer","Technology","Purpose"],
    [("Build Tool",       "Vite 5.3",              "Ultra-fast dev server + optimised production bundler"),
     ("UI Library",       "React 18.3",             "Component tree with concurrent features"),
     ("Styling",          "Tailwind CSS 3.4",       "Utility-first CSS — dark theme throughout"),
     ("Routing",          "React Router 6",         "Client-side SPA routing — 8 routes"),
     ("Server State",     "@tanstack/react-query",  "Async data fetching, caching, background refetch"),
     ("Global State",     "Zustand 4",              "Live prices, signals, risk status, portfolio NAV"),
     ("Charts",           "Recharts 2.12",          "NAV curves, P&L bars, allocation pie charts"),
     ("WebSocket",        "socket.io-client 4.7",   "Real-time price ticks, signals, risk alerts, fills"),
     ("HTTP Client",      "axios 1.7",              "All REST API calls to FastAPI backend"),
     ("Icons",            "lucide-react",           "Consistent icon set throughout UI"),
    ],
    [1.6,1.8,4.6])

h2(doc,"3.2  Page Structure")
tbl(doc,["Page","Route","Key Components","Data Sources"],
    [("Dashboard",  "/dashboard","NAV chart, signal feed, crypto snap, risk footer","/health, /risk/status, Zustand signals"),
     ("Portfolio",  "/portfolio","Allocation pie, daily P&L bar, positions table",  "/portfolio/positions (mock + live)"),
     ("Crypto",     "/crypto",   "Tab: Delta/Binance · Order form · Positions · Funding", "/crypto/delta/* and /crypto/binance/*"),
     ("AI Signals", "/signals",  "Agent runner form, signal history list",           "POST /signal → WebSocket 'signal'"),
     ("Risk",       "/risk",     "Emergency stop, drawdown meter, blocked tickers",  "GET /risk/status, POST/DELETE /risk/emergency-stop"),
     ("Analytics",  "/analytics","Cumulative returns chart, Sharpe/Sortino/Calmar",  "/analytics/metrics (future)"),
     ("Strategy",   "/strategy", "Strategy library grid, backtest launcher",         "/strategies (future)"),
     ("Settings",   "/settings", "Broker connection status, env toggle",             "Local state + config"),
    ],
    [1.1,1.1,2.4,3.4])

h2(doc,"3.3  WebSocket Event Schema")
for line in [
    "// Events broadcast from FastAPI → React via /ws endpoint",
    "",
    "{ event: 'signal',      ticker, signal, position_pct, sentiment_score, forecast_vol, reasoning }",
    "{ event: 'risk_alert',  emergency_stop, daily_pnl, open_positions, current_drawdown }",
    "{ event: 'price_tick',  symbol, mark_price, spot_price, change_24h, volume }",
    "{ event: 'order_filled',symbol, side, quantity, avg_fill_price, order_id, broker }",
    "{ event: 'subscribed',  symbols: ['BTCUSD', 'ETHUSD', ...] }",
]:
    code_line(doc, line)

h2(doc,"3.4  Quick Start")
for line in ["cd frontend","npm install","npm run dev    # → http://localhost:3000","","# Production build","npm run build  # → ../static/ (served by FastAPI)"]:
    code_line(doc, line)

page_break(doc)

# ── 4. CRYPTO EXECUTION ───────────────────────────────────────────────────────
h1(doc,"4. Crypto Execution — Delta Exchange + Binance")

h2(doc,"4.1  Delta Exchange Gateway")
para(doc,"Delta Exchange is India's largest crypto derivatives exchange offering perpetual futures, options, MOVE contracts, and spot trading. Alchemy's DeltaGateway wraps the Delta REST API v2 with full HMAC-SHA256 authentication, testnet support, and paper trading simulation.")
spacer(doc,6)

h3(doc,"Supported Products")
tbl(doc,["Product Type","Examples","Use Case"],
    [("Perpetual Futures","BTCUSD, ETHUSD, SOLUSD, BNBUSD","Leveraged long/short positions, no expiry"),
     ("Call Options","BTC-31MAY24-70000-C","Upside exposure, defined risk"),
     ("Put Options","ETH-28JUN24-3500-P","Downside protection, hedging"),
     ("MOVE Contracts","BTCMOVE-2024W18","Volatility trading — profits from large moves"),
     ("Spot Markets","BTC-USDT, ETH-USDT","Direct crypto purchase without leverage"),
    ],
    [1.8,2.4,3.8])

h3(doc,"Key API Methods")
for line in [
    "from alchemy.execution.crypto.delta_gateway import DeltaGateway",
    "",
    "gw = DeltaGateway(api_key='...', api_secret='...', testnet_mode=True)",
    "",
    "# Market data",
    "ticker   = gw.get_ticker('BTCUSD')          # mark_price, funding_rate, OI",
    "book     = gw.get_orderbook('BTCUSD', depth=20)",
    "klines   = gw.get_klines('ETHUSD', '1h')    # OHLCV candles",
    "funding  = gw.get_funding_rate('BTCUSD')    # current + predicted rate",
    "",
    "# Trading",
    "order = gw.place_order('BTCUSD', side='buy', size=1,",
    "                        order_type='market_order', leverage=10)",
    "gw.cancel_all_orders('BTCUSD')",
    "gw.close_position('ETHUSD')                 # market close entire position",
    "",
    "# Account",
    "balance   = gw.get_wallet_balance()         # USDT, BTC, ETH balances",
    "positions = gw.get_positions()              # open margined positions",
]:
    code_line(doc, line)

spacer(doc,10)
h2(doc,"4.2  Binance Gateway")
para(doc,"BinanceGateway supports all three Binance market types: Spot (direct crypto purchase), USD-M Futures (USDT-settled perpetuals and delivery), and COIN-M Futures (coin-settled contracts). Automatic HMAC-SHA256 signing, leverage control, and paper trading with live price lookup.")

h3(doc,"Market Type Selection")
tbl(doc,["market=","Base URL","Products","Use Case"],
    [("spot",          "api.binance.com",           "BTCUSDT, ETHUSDT spot",    "Direct crypto buy/sell"),
     ("futures_usdm",  "fapi.binance.com",          "BTCUSDT perp, ETHUSDT perp","USDT-margined leveraged trading"),
     ("futures_coinm", "dapi.binance.com",          "BTCUSD_PERP, ETHUSD_PERP", "Coin-margined leveraged trading"),
    ],
    [1.4,2.2,2.2,2.2])

h3(doc,"Key API Methods")
for line in [
    "from alchemy.execution.crypto.binance_gateway import BinanceGateway",
    "",
    "gw = BinanceGateway(api_key='...', api_secret='...',",
    "                     market='futures_usdm', testnet=True)",
    "",
    "# Market data",
    "ticker   = gw.get_ticker('BTCUSDT')         # 24h stats: price, volume, change",
    "klines   = gw.get_klines('ETHUSDT', '4h', limit=200)",
    "funding  = gw.get_funding_rate('BTCUSDT')   # historical 8h rates",
    "mark     = gw.get_mark_price('BTCUSDT')     # mark price + predicted funding",
    "",
    "# Trading",
    "order = gw.place_order('BTCUSDT', side='BUY', quantity=0.001,",
    "                        order_type='MARKET', leverage=10)",
    "gw.set_margin_type('BTCUSDT', 'ISOLATED')  # CROSSED | ISOLATED",
    "gw.close_position('ETHUSDT')               # full market close",
    "",
    "# Account",
    "balance   = gw.get_balance()               # USDT, BTC, ETH balances",
    "positions = gw.get_positions()             # non-zero open positions",
    "income    = gw.get_income_history()        # funding fee P&L history",
]:
    code_line(doc, line)

spacer(doc,10)
h2(doc,"4.3  Paper Trading Mode")
para(doc,"Both gateways default to paper_trading=True. In paper mode:")
for x in ["Orders return a simulated filled response immediately (no real API calls for order placement)",
           "Market data (tickers, klines, order books) still fetches live prices from the exchange",
           "Positions are not tracked server-side — use Zustand frontend state for position tracking",
           "Switch to live mode: DeltaGateway(paper_trading=False, testnet_mode=False)"]:
    bullet(doc,x)

page_break(doc)

# ── 5. API REFERENCE ──────────────────────────────────────────────────────────
h1(doc,"5. REST API Reference")
para(doc,"FastAPI application running on :8000. All endpoints return JSON. WebSocket on /ws.")
spacer(doc,6)

h2(doc,"5.1  Core Endpoints")
tbl(doc,["Method","Endpoint","Description","Auth"],
    [("GET",    "/health",                  "Health check — version + env",           "None"),
     ("POST",   "/signal",                  "Run LangGraph agent → TradingSignal",    "None"),
     ("GET",    "/risk/status",             "Current risk manager state",             "None"),
     ("POST",   "/risk/emergency-stop",     "Activate emergency stop",                "None"),
     ("DELETE", "/risk/emergency-stop",     "Clear emergency stop",                   "None"),
     ("POST",   "/risk/block",              "Block a ticker from trading",            "None"),
     ("WS",     "/ws",                      "Real-time event stream",                 "None"),
    ],
    [0.7,2.0,4.0,0.8])

h2(doc,"5.2  Delta Exchange Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("GET",    "/crypto/delta/products",           "List all available products"),
     ("GET",    "/crypto/delta/ticker/{symbol}",    "Real-time ticker (mark price, funding, OI)"),
     ("GET",    "/crypto/delta/orderbook/{symbol}", "L2 order book snapshot"),
     ("GET",    "/crypto/delta/positions",          "Open margined positions"),
     ("GET",    "/crypto/delta/balance",            "Wallet balances (USDT/BTC/ETH)"),
     ("GET",    "/crypto/delta/funding/{symbol}",   "Current + predicted funding rate"),
     ("POST",   "/crypto/delta/order",              "Place order (market/limit/stop)"),
     ("DELETE", "/crypto/delta/orders/{symbol}",    "Cancel all orders for symbol"),
    ],
    [0.7,2.8,4.5])

h2(doc,"5.3  Binance Endpoints")
tbl(doc,["Method","Endpoint","Description"],
    [("GET",    "/crypto/binance/ticker/{symbol}",   "24hr ticker statistics"),
     ("GET",    "/crypto/binance/klines/{symbol}",   "OHLCV klines (interval, limit params)"),
     ("GET",    "/crypto/binance/balance",           "Account wallet balances"),
     ("GET",    "/crypto/binance/positions",         "Open futures positions (non-zero)"),
     ("GET",    "/crypto/binance/funding/{symbol}",  "Historical funding rates"),
     ("POST",   "/crypto/binance/order",             "Place spot or futures order"),
     ("DELETE", "/crypto/binance/orders/{symbol}",   "Cancel all open orders"),
     ("POST",   "/crypto/binance/close/{symbol}",    "Market close entire position"),
    ],
    [0.7,2.8,4.5])

page_break(doc)

# ── 6. TESTING ────────────────────────────────────────────────────────────────
h1(doc,"6. Testing Strategy")
h2(doc,"6.1  Test Coverage")
tbl(doc,["Test File","Tests","Coverage Area"],
    [("tests/unit/test_core.py",           "20 tests","State schema, RiskManager, VolatilityEngine, PortfolioAnalytics"),
     ("tests/unit/crypto/test_gateways.py","16 tests","DeltaGateway paper mode, signing, BinanceGateway paper mode, formatting"),
     ("tests/integration/",               "Planned","End-to-end: data fetch → agent → paper order"),
     ("tests/e2e/",                        "Planned","Playwright: frontend UI + WebSocket flow"),
    ],
    [3.0,1.0,4.0])

h2(doc,"6.2  Running Tests")
for line in ["# Install test deps","pip install pytest pytest-asyncio pytest-cov","",
             "# Run all unit tests","pytest tests/unit/ -v --tb=short","",
             "# Run with coverage","pytest tests/ --cov=alchemy --cov-report=html","",
             "# Run only crypto tests","pytest tests/unit/crypto/ -v"]:
    code_line(doc, line)

page_break(doc)

# ── 7. QUICK START ────────────────────────────────────────────────────────────
h1(doc,"7. Quick Start Guide")
h2(doc,"7.1  Backend Setup")
for step,cmd in enumerate([
    "git clone https://github.com/jaikumararjunan/alchemy.git && cd alchemy",
    "python -m venv .venv && source .venv/bin/activate   # Windows: .venv\\Scripts\\activate",
    "pip install -r requirements.txt",
    "pip install git+https://github.com/QuantInsti/pyfolio.git",
    "pip install git+https://github.com/QuantInsti/zipline-pipeline.git",
    "cp config/settings.example.yaml config/settings.yaml   # edit with your keys",
    "uvicorn alchemy.api.app:app --reload --port 8000",
],1):
    p=doc.add_paragraph(style='List Number')
    p.add_run(cmd).font.name='Courier New'
    p.runs[0].font.size=Pt(8.5); p.paragraph_format.space_before=Pt(2)

h2(doc,"7.2  Frontend Setup")
for line in ["cd frontend","npm install","npm run dev         # → http://localhost:3000","",
             "# The Vite proxy routes /api → localhost:8000 automatically"]:
    code_line(doc, line)

h2(doc,"7.3  Docker Compose (Full Stack)")
for line in ["# Starts: FastAPI + LiteLLM + Redis + TimescaleDB",
             "docker-compose up -d","","# Frontend dev server (separate terminal)",
             "cd frontend && npm run dev"]:
    code_line(doc, line)

h2(doc,"7.4  Run a Crypto AI Signal")
for line in ["# POST to generate a signal for BTC on Delta Exchange",
             'curl -X POST http://localhost:8000/signal \\',
             '  -H "Content-Type: application/json" \\',
             '  -d \'{"ticker":"BTCUSD","market":"CRYPTO","broker":"PAPER"}\'',
             "",
             "# Response:",
             '{"ticker":"BTCUSD","signal":"BUY","position_pct":0.03,',
             ' "sentiment_score":0.72,"forecast_vol":0.54,"reasoning":"..."}']:
    code_line(doc, line)

# ── SAVE ─────────────────────────────────────────────────────────────────────
doc.save(str(OUT))
print(f"Saved: {OUT}")
print(f"Size:  {OUT.stat().st_size/1024:.0f} KB")
