"""Generate 4 auth/security UML diagrams for Alchemy v0.4"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import os

OUT = "/home/claude/alchemy/docs/auth"
os.makedirs(OUT, exist_ok=True)

C = dict(
    navy="#1B3A5C", blue="#2E75B6", sky="#5B9BD5", teal="#00B0F0",
    green="#2E7D32", amber="#F59E0B", red="#C62828", orange="#E65100",
    purple="#7B1FA2", gray="#546E7A", white="#FFFFFF", dgray="#37474F",
    s_ok="#065F46", s_err="#7F1D1D", s_warn="#78350F",
)

def save(fig, name):
    path = f"{OUT}/{name}.png"
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {name}.png")

def box(ax, x, y, w, h, fill, edge, label, sub=None, fs=8.5, bold=True,
        lc="white", radius=0.2, lw=1.5, z=2):
    ax.add_patch(FancyBboxPatch((x,y), w, h,
                 boxstyle=f"round,pad=0,rounding_size={radius}",
                 facecolor=fill, edgecolor=edge, linewidth=lw, zorder=z))
    cy = y + h/2 + (0.07 if sub else 0)
    ax.text(x+w/2, cy, label, ha='center', va='center', fontsize=fs,
            fontweight='bold' if bold else 'normal', color=lc, zorder=z+1)
    if sub:
        ax.text(x+w/2, y+h/2-0.12, sub, ha='center', va='center',
                fontsize=6.2, color=lc, alpha=0.85, zorder=z+1)

def arr(ax, x1, y1, x2, y2, col="#546E7A", lw=1.4, lbl="", rad=0.0):
    ax.annotate("", xy=(x2,y2), xytext=(x1,y1),
        arrowprops=dict(arrowstyle="-|>", color=col, lw=lw,
                       connectionstyle=f"arc3,rad={rad}"))
    if lbl:
        ax.text((x1+x2)/2+0.05, (y1+y2)/2+0.06, lbl, fontsize=6, color=col)

def title(ax, t, sub=""):
    ax.text(0.5, 0.97, t, transform=ax.transAxes, ha='center', va='top',
            fontsize=13, fontweight='bold', color=C['navy'])
    if sub:
        ax.text(0.5, 0.93, sub, transform=ax.transAxes, ha='center', va='top',
                fontsize=8, color=C['gray'])


# ══════════════════════════════════════════════════════════════════════════════
# 1 — LOGIN / AUTH SEQUENCE
# ══════════════════════════════════════════════════════════════════════════════
def d1_auth_sequence():
    fig, ax = plt.subplots(figsize=(18,12))
    ax.set_xlim(0,18); ax.set_ylim(0,12); ax.axis('off')
    fig.patch.set_facecolor("#FAFAFA")
    title(ax, "Alchemy v0.4 — Login + 2FA Authentication Sequence",
          "UML Sequence · Email/password → bcrypt verify → rate limit → TOTP → JWT issue → httpOnly cookie")

    actors = [
        (1.3, "React\nLoginPage",   C['purple']),
        (3.4, "FastAPI\n:8000",     C['blue']),
        (5.5, "AuthService",        C['orange']),
        (7.6, "Rate\nLimiter",      "#0F766E"),
        (9.7, "bcrypt\nVerify",     C['gray']),
        (11.8,"2FA\nTOTP",          C['amber']),
        (13.9,"TokenVault\n+JWT",   C['navy']),
        (16.0,"AuditLog",           C['red']),
    ]
    for x, lbl, col in actors:
        box(ax, x-0.6, 11.0, 1.2, 0.85, col, col, lbl, fs=7, radius=0.15)
        ax.plot([x, x], [11.0, 0.4], color='#CBD5E1', lw=1, linestyle='--', zorder=1)

    def msg(x1, x2, y, lbl, col, ret=False, lw=1.4):
        ax.annotate("", xy=(x2,y), xytext=(x1,y),
            arrowprops=dict(arrowstyle="<|-" if ret else "-|>", color=col, lw=lw,
                            linestyle="dashed" if ret else "solid"))
        ax.text((x1+x2)/2, y+0.07, lbl, ha='center', fontsize=6.2, color=col)

    def act(x, y, h, col, alpha=0.9):
        ax.add_patch(FancyBboxPatch((x-0.08, y-h), 0.16, h,
            boxstyle="square,pad=0", facecolor=col, edgecolor='white', lw=0.5, alpha=alpha, zorder=2))

    rows = [
        (1.3,3.4,  10.2, "POST /auth/login {email,password,totp_code}",       C['purple'],False),
        (3.4,7.6,   9.6, "check_rate_limit('auth.login', ip)",                C['teal'],  False),
        (7.6,3.4,   9.0, "allowed=True (4/5 remaining)",                       C['teal'],  True),
        (3.4,5.5,   8.4, "AuthService.login(email,pwd,ip,ua)",                C['blue'],  False),
        (5.5,9.7,   7.8, "bcrypt.checkpw(password, user.password_hash)",      C['gray'],  False),
        (9.7,5.5,   7.2, "password_valid=True (timing-safe)",                  C['gray'],  True),
        (5.5,11.8,  6.6, "TOTPManager.verify(secret,totp_code)",              C['amber'], False),
        (11.8,5.5,  6.0, "totp_valid=True (±30s window)",                     C['amber'], True),
        (5.5,13.9,  5.4, "create_access_token(15min) + create_refresh_token()",C['navy'],  False),
        (13.9,5.5,  4.8, "access_jwt + refresh_raw (SHA-256 hash stored)",     C['navy'],  True),
        (5.5,16.0,  4.2, "AuditLog.write(auth.login, success, ip, risk=0)",   C['red'],   False),
        (5.5,3.4,   3.6, "login result {access_token, refresh_raw, user}",    C['orange'],True),
        (3.4,1.3,   3.0, "set refresh_token=httpOnly;Secure;SameSite=Strict",  C['blue'],  True),
        (3.4,1.3,   2.4, "return {access_token, user} (never refresh in body)",C['blue'],  True),
        (1.3,1.3,   1.8, "Store access_token in React state (NOT localStorage)",C['purple'],False),
        (1.3,1.3,   1.2, "Schedule auto-refresh 2min before expiry",           C['purple'],False),
    ]
    for x1, x2, y, lbl, col, ret in rows:
        msg(x1, x2, y, lbl, col, ret)

    act(5.5, 8.4, 4.5, C['orange'])
    act(9.7, 7.8, 0.5, C['gray'])
    act(11.8, 6.6, 0.5, C['amber'])
    act(13.9, 5.4, 0.5, C['navy'])

    save(fig, "01_auth_login_sequence")


# ══════════════════════════════════════════════════════════════════════════════
# 2 — SECURITY ARCHITECTURE LAYERS
# ══════════════════════════════════════════════════════════════════════════════
def d2_security_layers():
    fig, ax = plt.subplots(figsize=(17,11))
    ax.set_xlim(0,17); ax.set_ylim(0,11); ax.axis('off')
    fig.patch.set_facecolor("#F0F4F8")
    title(ax, "Alchemy v0.4 — Security Architecture Layers",
          "Defence in depth · 7 security layers · Industry-grade implementation")

    layers = [
        (0.3, 9.5, 16.4, 1.1, "#0F172A", "#00B0F0", "LAYER 1 — TLS/HTTPS Transport",
         "Nginx SSL termination · TLS 1.3 only · HSTS preload · OCSP stapling · Perfect Forward Secrecy"),
        (0.3, 8.1, 16.4, 1.1, "#1B3A5C", "#2E75B6", "LAYER 2 — Network Rate Limiting",
         "Nginx: 5 logins/min · 3 signups/hr · FastAPI InMemoryRateLimiter · Redis sliding window (production)"),
        (0.3, 6.7, 16.4, 1.1, "#1C1917", "#F59E0B", "LAYER 3 — Input Validation",
         "Pydantic v2 schemas · EmailStr · regex username · NIST SP 800-63B password policy · Length limits"),
        (0.3, 5.3, 16.4, 1.1, "#1B3A5C", "#7C3AED", "LAYER 4 — Authentication",
         "JWT HS256 (15min access) · bcrypt cost=12 · TOTP RFC 6238 (±30s) · 5-attempt lockout · 30min ban"),
        (0.3, 3.9, 16.4, 1.1, "#1A2E1A", "#10B981", "LAYER 5 — Authorization (RBAC)",
         "5 roles: super_admin > admin > trader > analyst > viewer · require_permission() on every endpoint"),
        (0.3, 2.5, 16.4, 1.1, "#1C1917", "#EF4444", "LAYER 6 — Security Headers",
         "X-Frame-Options: DENY · CSP nonce · X-Content-Type-Options · Referrer-Policy · Permissions-Policy"),
        (0.3, 1.1, 16.4, 1.1, "#1A1A2E", "#818CF8", "LAYER 7 — Audit & Monitoring",
         "Immutable AuditLog · risk_score 0–100 · failed_login tracking · session revocation · IP logging"),
    ]
    for x, y, w, h, fill, edge, lbl, sub in layers:
        ax.add_patch(FancyBboxPatch((x,y), w, h, boxstyle="round,pad=0,rounding_size=0.15",
                     facecolor=fill, edgecolor=edge, linewidth=2, zorder=2))
        ax.text(x+0.3, y+h/2+0.12, lbl, ha='left', va='center', fontsize=9,
                fontweight='bold', color='white', zorder=3)
        ax.text(x+0.3, y+h/2-0.18, sub, ha='left', va='center', fontsize=7,
                color='#94A3B8', zorder=3)

    # Threat arrows
    for i, (threat, y) in enumerate([("DDoS/Brute Force",9.8),("Credential Stuffing",8.4),("SQL Injection/XSS",7.0),
                                       ("Stolen Credentials",5.6),("Privilege Escalation",4.2),("Clickjacking/CSRF",2.8),("Data Breach",1.4)]):
        ax.text(16.8, y, f"← {threat}", ha='right', va='center', fontsize=6.5,
                color='#EF4444', style='italic')

    save(fig, "02_security_layers")


# ══════════════════════════════════════════════════════════════════════════════
# 3 — RBAC PERMISSION MATRIX
# ══════════════════════════════════════════════════════════════════════════════
def d3_rbac_matrix():
    fig, ax = plt.subplots(figsize=(16,9))
    ax.set_xlim(0,16); ax.set_ylim(0,9); ax.axis('off')
    fig.patch.set_facecolor("#F8FBFF")
    title(ax, "Alchemy v0.4 — RBAC Permission Matrix",
          "Role-Based Access Control · 5 roles · 16 permission gates on all endpoints")

    roles = ["super_admin", "admin", "trader", "analyst", "viewer"]
    role_colors = ["#7C3AED", "#2563EB", "#059669", "#D97706", "#6B7280"]
    perms = [
        ("trading:read",      [1,1,1,1,1]),
        ("trading:write",     [1,1,1,0,0]),
        ("trading:execute",   [1,1,1,0,0]),
        ("signals:read",      [1,1,1,1,1]),
        ("signals:generate",  [1,1,1,0,0]),
        ("workflows:read",    [1,1,1,1,0]),
        ("workflows:write",   [1,1,1,0,0]),
        ("tokens:read",       [1,1,1,1,0]),
        ("tokens:write",      [1,1,1,0,0]),
        ("users:read",        [1,1,0,0,0]),
        ("users:write",       [1,1,0,0,0]),
        ("users:delete",      [1,1,0,0,0]),
        ("admin:dashboard",   [1,1,0,0,0]),
        ("admin:audit",       [1,1,0,0,0]),
        ("admin:ban_user",    [1,0,0,0,0]),
        ("* (all)",           [1,0,0,0,0]),
    ]

    # Headers
    xs = [4.0 + i*2.2 for i in range(5)]
    for i, (role, col) in enumerate(zip(roles, role_colors)):
        box(ax, xs[i]-0.9, 7.8, 1.8, 0.8, col, col, role.replace("_","\n"), fs=8, radius=0.15)

    # Permission rows
    for ri, (perm, grants) in enumerate(perms):
        y = 6.9 - ri * 0.42
        ax.text(0.2, y+0.15, perm, ha='left', va='center', fontsize=7.5,
                color='#1B3A5C', family='monospace')
        for ci, (granted, xs_i) in enumerate(zip(grants, xs)):
            color = role_colors[ci] if granted else "#374151"
            symbol = "✓" if granted else "✗"
            t_color = "white" if granted else "#6B7280"
            ax.add_patch(FancyBboxPatch((xs_i-0.3, y-0.1), 0.6, 0.4,
                boxstyle="round,pad=0,rounding_size=0.08",
                facecolor=color, edgecolor='none', alpha=0.9, zorder=2))
            ax.text(xs_i, y+0.1, symbol, ha='center', va='center',
                    fontsize=9, color=t_color, fontweight='bold', zorder=3)

    # Legend
    ax.text(0.2, 0.5, "✓ = Permission granted    ✗ = Denied    All routes protected by require_permission() dependency",
            fontsize=8, color=C['gray'], style='italic')

    save(fig, "03_rbac_matrix")


# ══════════════════════════════════════════════════════════════════════════════
# 4 — JWT + SESSION LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════════
def d4_jwt_lifecycle():
    fig, ax = plt.subplots(figsize=(16,10))
    ax.set_xlim(0,16); ax.set_ylim(0,10); ax.axis('off')
    fig.patch.set_facecolor("#0F172A")

    # Background panels
    for x, w, col, lbl in [(0.2,7.2,"#1E293B","BROWSER (React SPA)"),(8.0,7.8,"#1A1A2E","SERVER (FastAPI + DB)")]:
        ax.add_patch(FancyBboxPatch((x,0.5), w, 9.0, boxstyle="round,pad=0,rounding_size=0.3",
            facecolor=col, edgecolor='#334155', linewidth=1.5, zorder=0))
        ax.text(x+w/2, 9.3, lbl, ha='center', fontsize=9, fontweight='bold', color='#94A3B8')

    title_p = ax.text(8, 9.7, "Alchemy v0.4 — JWT Token + Session Lifecycle",
                      ha='center', fontsize=13, fontweight='bold', color='white')
    ax.text(8, 9.4, "Access token in React memory · Refresh token in httpOnly cookie · Server-side session tracking",
            ha='center', fontsize=8, color='#64748B')

    def blk(x, y, w, h, fill, edge, lbl, sub=None):
        box(ax, x, y, w, h, fill, edge, lbl, sub, fs=8, radius=0.2, lc='white')

    def con(x1, y1, x2, y2, col, lbl="", lw=1.4):
        ax.annotate("", xy=(x2,y2), xytext=(x1,y1),
            arrowprops=dict(arrowstyle="-|>", color=col, lw=lw, connectionstyle="arc3,rad=0.0"))
        if lbl: ax.text((x1+x2)/2, (y1+y2)/2+0.1, lbl, fontsize=6.5, color=col, ha='center')

    # Browser components
    blk(0.4, 7.5, 3.0, 0.9, "#1D4ED8", "#60A5FA", "AuthContext", "access_token in useState()")
    blk(0.4, 5.9, 3.0, 0.9, "#0F766E", "#2DD4BF", "httpOnly Cookie", "refresh_token (auto-sent)")
    blk(0.4, 4.3, 3.0, 0.9, "#7C3AED", "#A78BFA", "API Client", "axios + Bearer header")
    blk(0.4, 2.7, 3.0, 0.9, "#92400E", "#FCD34D", "Auto-Refresh Timer", "setTimeout 13min (15-2)")
    blk(0.4, 1.1, 3.0, 0.9, "#1E3A5F", "#38BDF8", "Protected Routes", "redirect if no token")

    # Server components
    blk(8.2, 7.5, 3.2, 0.9, "#1B3A5C", "#2E75B6", "JWT Middleware", "decode_access_token()")
    blk(8.2, 5.9, 3.2, 0.9, "#2E7D32", "#4CAF50", "UserSession Table", "refresh_token_hash, jti, ip")
    blk(8.2, 4.3, 3.2, 0.9, "#7F1D1D", "#EF4444", "AuditLog Table",   "action, ip, risk_score")
    blk(8.2, 2.7, 3.2, 0.9, "#1C1917", "#F59E0B", "Token Rotation",   "new refresh on every use")
    blk(8.2, 1.1, 3.2, 0.9, "#4A148C", "#CE93D8", "Session Revoke",   "logout: is_active=False")
    blk(11.7, 5.9, 3.2, 0.9, "#065F46","#10B981", "Refresh Endpoint", "POST /auth/refresh")
    blk(11.7, 7.5, 3.2, 0.9, "#1B3A5C","#60A5FA", "Protected APIs",   "require_permission()")

    # Flows
    con(1.9, 7.5, 1.9, 6.8, "#60A5FA", "")
    con(1.9, 5.9, 1.9, 5.2, "#2DD4BF", "")
    con(1.9, 4.3, 1.9, 3.6, "#A78BFA", "")
    con(1.9, 2.7, 1.9, 2.0, "#FCD34D", "")
    con(3.4, 7.9, 8.2, 7.9, "#60A5FA", "Authorization: Bearer {jwt}")
    con(3.4, 6.3, 11.7, 6.3, "#2DD4BF", "cookie auto-sent → /auth/refresh")
    con(11.7, 6.8, 8.2, 6.8, "#4CAF50", "verify SHA-256(refresh) in DB")
    con(11.7, 7.9, 8.2, 7.9, "#2E75B6", "validate JWT signature + exp")
    con(8.2, 3.1, 8.2, 3.6, "#EF4444", "log every auth event")
    con(9.8, 2.7, 9.8, 2.0, "#F59E0B", "rotate on each use")
    con(9.8, 1.1, 9.8, 0.6, "#CE93D8", "logout → invalidate all")

    # Token spec boxes
    for x, y, w, lbl, col in [
        (4.0, 8.2, 3.5, "Access Token: JWT HS256 · exp=15min · sub+email+role+jti", "#1E40AF"),
        (4.0, 7.0, 3.5, "Refresh Token: 48-byte urlsafe · SHA-256 hash in DB · 7 days", "#065F46"),
    ]:
        ax.add_patch(FancyBboxPatch((x,y), w, 0.55, boxstyle="round,pad=0,rounding_size=0.1",
            facecolor=col, edgecolor='none', alpha=0.8, zorder=2))
        ax.text(x+w/2, y+0.27, lbl, ha='center', va='center', fontsize=6.5, color='white', zorder=3)

    save(fig, "04_jwt_session_lifecycle")


if __name__ == "__main__":
    print("Generating auth security UML diagrams…")
    d1_auth_sequence()
    d2_security_layers()
    d3_rbac_matrix()
    d4_jwt_lifecycle()
    print("All 4 diagrams generated!")
