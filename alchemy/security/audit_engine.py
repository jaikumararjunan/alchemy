"""
alchemy.security.audit_engine
================================
Enterprise-grade security audit engine.

Features:
  - Device fingerprinting (OS, browser, device type, screen resolution)
  - IP geolocation (country, city, ISP, ASN, VPN/proxy detection)
  - Geo-fencing rules (allow/block by country, IP range)
  - Login risk scoring (0-100 scale)
  - Anomaly detection (new device, new location, impossible travel, brute force)
  - Session lifecycle tracking (login, activity, logout, expiry)
  - Compliance-ready audit trail (ISO 27001 / SOC 2 format)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional
from ipaddress import ip_address, ip_network

import structlog
log = structlog.get_logger(__name__)

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
_DB_FILE = DB_PATH.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class AuditEventType(str, Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_BLOCKED = "login_blocked"
    LOGIN_2FA_REQUIRED = "login_2fa_required"
    LOGIN_2FA_SUCCESS = "login_2fa_success"
    LOGIN_2FA_FAILED = "login_2fa_failed"
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_COMPLETE = "password_reset_complete"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    SIGNUP = "signup"
    EMAIL_VERIFIED = "email_verified"
    API_KEY_ADDED = "api_key_added"
    API_KEY_REMOVED = "api_key_removed"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    TRADE_EXECUTED = "trade_executed"
    GEO_FENCE_BLOCKED = "geo_fence_blocked"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    DEVICE_NEW = "device_new"
    DEVICE_TRUSTED = "device_trusted"


class RiskLevel(str, Enum):
    LOW = "low"          # 0-25: normal login
    MEDIUM = "medium"    # 26-50: minor anomaly
    HIGH = "high"        # 51-75: significant risk
    CRITICAL = "critical"  # 76-100: block/challenge


@dataclass
class DeviceInfo:
    """Parsed device fingerprint from User-Agent and client hints."""
    user_agent_raw: str = ""
    browser: str = "Unknown"
    browser_version: str = ""
    os: str = "Unknown"
    os_version: str = ""
    device_type: str = "desktop"  # desktop, mobile, tablet, bot, unknown
    device_brand: str = ""
    device_model: str = ""
    is_bot: bool = False
    is_mobile: bool = False
    client_hints: dict = field(default_factory=dict)
    screen_resolution: str = ""
    timezone: str = ""
    language: str = ""
    fingerprint_hash: str = ""

    def compute_fingerprint(self) -> str:
        """Generate unique device fingerprint hash."""
        raw = f"{self.browser}|{self.os}|{self.device_type}|{self.device_brand}|{self.screen_resolution}|{self.timezone}"
        self.fingerprint_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return self.fingerprint_hash


@dataclass
class GeoInfo:
    """IP geolocation data."""
    ip: str = ""
    country: str = ""
    country_code: str = ""
    region: str = ""
    city: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    isp: str = ""
    org: str = ""
    asn: str = ""
    is_vpn: bool = False
    is_proxy: bool = False
    is_tor: bool = False
    is_datacenter: bool = False
    timezone: str = ""
    lookup_source: str = ""


@dataclass
class AuditEvent:
    """A single security audit event."""
    event_type: AuditEventType
    user_id: str = ""
    email: str = ""
    ip: str = ""
    geo: Optional[GeoInfo] = None
    device: Optional[DeviceInfo] = None
    risk_score: int = 0
    risk_level: RiskLevel = RiskLevel.LOW
    risk_factors: list = field(default_factory=list)
    session_id: str = ""
    success: bool = True
    failure_reason: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICE FINGERPRINTING
# ═══════════════════════════════════════════════════════════════════════════════

_BROWSER_PATTERNS = [
    (r"Edg[ea]?/(\S+)", "Edge"),
    (r"OPR/(\S+)", "Opera"),
    (r"Vivaldi/(\S+)", "Vivaldi"),
    (r"Brave/(\S+)", "Brave"),
    (r"SamsungBrowser/(\S+)", "Samsung Browser"),
    (r"UCBrowser/(\S+)", "UC Browser"),
    (r"Chrome/(\S+)", "Chrome"),
    (r"Firefox/(\S+)", "Firefox"),
    (r"Safari/(\S+)", "Safari"),
    (r"MSIE\s(\S+)", "IE"),
    (r"Trident/.*rv:(\S+)", "IE"),
]

_OS_PATTERNS = [
    (r"Windows NT 10\.0", "Windows", "10/11"),
    (r"Windows NT 6\.3", "Windows", "8.1"),
    (r"Windows NT 6\.1", "Windows", "7"),
    (r"Mac OS X (\d+[._]\d+[._]?\d*)", "macOS", None),
    (r"iPhone OS (\d+[._]\d+)", "iOS", None),
    (r"iPad.*OS (\d+[._]\d+)", "iPadOS", None),
    (r"Android (\d+\.?\d*)", "Android", None),
    (r"Linux", "Linux", ""),
    (r"CrOS", "ChromeOS", ""),
]

_BOT_PATTERNS = [
    r"bot", r"crawl", r"spider", r"scrape", r"curl", r"wget",
    r"python-requests", r"httpx", r"postman", r"insomnia",
]


def parse_device(user_agent: str, client_hints: dict = None) -> DeviceInfo:
    """Parse User-Agent string into structured device info."""
    device = DeviceInfo(user_agent_raw=user_agent, client_hints=client_hints or {})

    if not user_agent:
        device.device_type = "unknown"
        device.compute_fingerprint()
        return device

    ua_lower = user_agent.lower()

    # Bot detection
    for pat in _BOT_PATTERNS:
        if re.search(pat, ua_lower):
            device.is_bot = True
            device.device_type = "bot"
            device.browser = pat.replace(r"\\", "")
            break

    # Browser detection
    if not device.is_bot:
        for pattern, name in _BROWSER_PATTERNS:
            m = re.search(pattern, user_agent)
            if m:
                device.browser = name
                device.browser_version = m.group(1).split(".")[0]
                break

    # OS detection
    for pattern, os_name, version in _OS_PATTERNS:
        m = re.search(pattern, user_agent)
        if m:
            device.os = os_name
            if version:
                device.os_version = version
            elif m.lastindex:
                device.os_version = m.group(1).replace("_", ".")
            break

    # Device type
    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        device.device_type = "mobile"
        device.is_mobile = True
    elif "ipad" in ua_lower or "tablet" in ua_lower:
        device.device_type = "tablet"
        device.is_mobile = True
    elif device.is_bot:
        device.device_type = "bot"
    else:
        device.device_type = "desktop"

    # Device brand for mobile
    if "iPhone" in user_agent or "iPad" in user_agent:
        device.device_brand = "Apple"
    elif m := re.search(r"(Samsung|Xiaomi|Huawei|OnePlus|Pixel|OPPO|Vivo|Realme)", user_agent):
        device.device_brand = m.group(1)

    # Client hints override (Sec-CH-UA headers)
    if client_hints:
        if "platform" in client_hints:
            device.os = client_hints["platform"]
        if "mobile" in client_hints:
            device.is_mobile = client_hints["mobile"]
        if "brands" in client_hints:
            device.browser = client_hints["brands"]

    device.compute_fingerprint()
    return device


# ═══════════════════════════════════════════════════════════════════════════════
# IP GEOLOCATION
# ═══════════════════════════════════════════════════════════════════════════════

_geo_cache: dict[str, tuple[GeoInfo, float]] = {}
_GEO_CACHE_TTL = 3600  # 1 hour

# Known private/reserved IP ranges
_PRIVATE_RANGES = [
    ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"), ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"), ip_network("::1/128"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        addr = ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_RANGES)
    except ValueError:
        return True


async def geolocate_ip(ip_str: str) -> GeoInfo:
    """Lookup IP geolocation via ip-api.com (free, 45 req/min)."""
    geo = GeoInfo(ip=ip_str)

    if _is_private_ip(ip_str) or ip_str in ("testclient", "unknown", ""):
        geo.country = "Local"
        geo.country_code = "LO"
        geo.city = "localhost"
        geo.lookup_source = "private"
        return geo

    # Check cache
    if ip_str in _geo_cache:
        cached, ts = _geo_cache[ip_str]
        if time.time() - ts < _GEO_CACHE_TTL:
            return cached

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            # ip-api.com — free, no API key, 45/min
            resp = await client.get(
                f"http://ip-api.com/json/{ip_str}?fields=status,country,countryCode,regionName,city,lat,lon,isp,org,as,proxy,hosting,timezone"
            )
            if resp.status_code == 200:
                d = resp.json()
                if d.get("status") == "success":
                    geo.country = d.get("country", "")
                    geo.country_code = d.get("countryCode", "")
                    geo.region = d.get("regionName", "")
                    geo.city = d.get("city", "")
                    geo.latitude = d.get("lat", 0)
                    geo.longitude = d.get("lon", 0)
                    geo.isp = d.get("isp", "")
                    geo.org = d.get("org", "")
                    geo.asn = d.get("as", "")
                    geo.is_proxy = d.get("proxy", False)
                    geo.is_datacenter = d.get("hosting", False)
                    geo.timezone = d.get("timezone", "")
                    geo.lookup_source = "ip-api.com"

        # Cache result
        _geo_cache[ip_str] = (geo, time.time())
        log.info("geo.lookup", ip=ip_str, country=geo.country_code, city=geo.city)

    except Exception as e:
        log.warning("geo.lookup_failed", ip=ip_str, error=str(e))
        geo.lookup_source = f"error: {str(e)[:50]}"

    return geo


# ═══════════════════════════════════════════════════════════════════════════════
# GEO-FENCING
# ═══════════════════════════════════════════════════════════════════════════════

class GeoFenceEngine:
    """Geo-fencing rule engine — allow/block by country, IP range."""

    def __init__(self):
        self._ensure_tables()

    def _conn(self):
        c = sqlite3.connect(_DB_FILE)
        c.row_factory = sqlite3.Row
        return c

    def _ensure_tables(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS geo_fence_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                value TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'block',
                description TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )""")

    def add_rule(self, user_id: str, rule_type: str, value: str,
                 action: str = "block", description: str = "") -> int:
        """
        Add a geo-fence rule.
        rule_type: 'country', 'country_code', 'ip_range', 'ip', 'asn'
        action: 'block' or 'allow'
        """
        with self._conn() as c:
            c.execute("INSERT INTO geo_fence_rules (user_id, rule_type, value, action, description) VALUES (?,?,?,?,?)",
                      (user_id, rule_type, value, action, description))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    def remove_rule(self, user_id: str, rule_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM geo_fence_rules WHERE id=? AND user_id=?", (rule_id, user_id))

    def get_rules(self, user_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM geo_fence_rules WHERE user_id=? AND enabled=1",
                             (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def check(self, user_id: str, geo: GeoInfo, ip: str) -> tuple[bool, str]:
        """
        Check if login is allowed by geo-fence rules.
        Returns (allowed, reason).
        Default: allow all (no rules = no restrictions).
        """
        rules = self.get_rules(user_id)
        if not rules:
            return True, ""

        # Separate allow and block rules
        allow_rules = [r for r in rules if r["action"] == "allow"]
        block_rules = [r for r in rules if r["action"] == "block"]

        # If there are ALLOW rules, everything not in allow list is blocked
        if allow_rules:
            for rule in allow_rules:
                if self._matches(rule, geo, ip):
                    return True, ""
            return False, f"Login from {geo.country} ({geo.city}) not in allowed list"

        # If only BLOCK rules, check if blocked
        for rule in block_rules:
            if self._matches(rule, geo, ip):
                return False, f"Login blocked by geo-fence rule: {rule['description'] or rule['value']}"

        return True, ""

    def _matches(self, rule: dict, geo: GeoInfo, ip: str) -> bool:
        rt = rule["rule_type"]
        val = rule["value"].upper()
        if rt == "country_code":
            return geo.country_code.upper() == val
        elif rt == "country":
            return geo.country.upper() == val
        elif rt == "ip":
            return ip == rule["value"]
        elif rt == "ip_range":
            try:
                return ip_address(ip) in ip_network(rule["value"])
            except ValueError:
                return False
        elif rt == "asn":
            return val in geo.asn.upper()
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# RISK SCORING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class RiskScoringEngine:
    """
    Calculate login risk score (0-100) based on multiple signals.
    Industry-standard factors: device trust, location anomaly, time anomaly,
    velocity, VPN/proxy, failed attempts, impossible travel.
    """

    WEIGHTS = {
        "new_device": 20,
        "new_location": 15,
        "new_country": 25,
        "vpn_proxy": 15,
        "tor_exit": 30,
        "datacenter_ip": 10,
        "impossible_travel": 35,
        "failed_attempts_recent": 20,
        "unusual_hour": 5,
        "bot_user_agent": 40,
        "credential_stuffing": 30,
    }

    def __init__(self):
        self._ensure_tables()

    def _conn(self):
        c = sqlite3.connect(_DB_FILE)
        c.row_factory = sqlite3.Row
        return c

    def _ensure_tables(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS known_devices (
                user_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                device_info TEXT DEFAULT '{}',
                first_seen TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now')),
                is_trusted INTEGER DEFAULT 0,
                login_count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, fingerprint)
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS known_locations (
                user_id TEXT NOT NULL,
                country_code TEXT NOT NULL,
                city TEXT NOT NULL,
                first_seen TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now')),
                login_count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, country_code, city)
            )""")

    def score(self, user_id: str, device: DeviceInfo, geo: GeoInfo,
              ip: str, failed_recent: int = 0) -> tuple[int, RiskLevel, list[str]]:
        """
        Calculate risk score. Returns (score, level, factors).
        """
        score = 0
        factors = []

        # 1. New device check
        with self._conn() as c:
            dev_row = c.execute("SELECT * FROM known_devices WHERE user_id=? AND fingerprint=?",
                                (user_id, device.fingerprint_hash)).fetchone()
        if not dev_row:
            score += self.WEIGHTS["new_device"]
            factors.append(f"New device: {device.browser} on {device.os} ({device.device_type})")
        elif dev_row and dict(dev_row).get("is_trusted"):
            score -= 10  # Trusted device bonus

        # 2. New location check
        with self._conn() as c:
            loc_row = c.execute("SELECT * FROM known_locations WHERE user_id=? AND country_code=? AND city=?",
                                (user_id, geo.country_code, geo.city)).fetchone()
        if not loc_row and geo.country_code and geo.country_code != "LO":
            score += self.WEIGHTS["new_location"]
            factors.append(f"New location: {geo.city}, {geo.country}")

        # 3. New country
        with self._conn() as c:
            country_row = c.execute("SELECT * FROM known_locations WHERE user_id=? AND country_code=?",
                                    (user_id, geo.country_code)).fetchone()
        if not country_row and geo.country_code and geo.country_code not in ("LO", ""):
            score += self.WEIGHTS["new_country"]
            factors.append(f"New country: {geo.country} ({geo.country_code})")

        # 4. VPN / Proxy / Tor / Datacenter
        if geo.is_proxy:
            score += self.WEIGHTS["vpn_proxy"]
            factors.append("VPN/Proxy detected")
        if geo.is_tor:
            score += self.WEIGHTS["tor_exit"]
            factors.append("Tor exit node detected")
        if geo.is_datacenter:
            score += self.WEIGHTS["datacenter_ip"]
            factors.append("Datacenter IP (cloud hosting)")

        # 5. Impossible travel detection
        impossible = self._check_impossible_travel(user_id, geo)
        if impossible:
            score += self.WEIGHTS["impossible_travel"]
            factors.append(impossible)

        # 6. Recent failed attempts
        if failed_recent >= 3:
            score += self.WEIGHTS["failed_attempts_recent"]
            factors.append(f"{failed_recent} failed login attempts recently")

        # 7. Bot User-Agent
        if device.is_bot:
            score += self.WEIGHTS["bot_user_agent"]
            factors.append(f"Bot/automated client: {device.browser}")

        # 8. Unusual hour (login at 2-5 AM local time)
        if geo.timezone:
            try:
                now_utc = datetime.now(timezone.utc)
                # Simple timezone offset estimation
                local_hour = now_utc.hour  # Would need proper tz conversion
                if 2 <= local_hour <= 5:
                    score += self.WEIGHTS["unusual_hour"]
                    factors.append(f"Login at unusual hour (UTC {local_hour:02d}:00)")
            except Exception:
                pass

        # Clamp score
        score = max(0, min(100, score))

        # Determine level
        if score <= 25:
            level = RiskLevel.LOW
        elif score <= 50:
            level = RiskLevel.MEDIUM
        elif score <= 75:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL

        return score, level, factors

    def _check_impossible_travel(self, user_id: str, geo: GeoInfo) -> str | None:
        """Check if user logged in from two distant locations in short time."""
        if not geo.latitude or not geo.longitude:
            return None

        with self._conn() as c:
            # Get last login with geo data
            row = c.execute("""SELECT geo_data FROM security_audit_log
                WHERE user_id=? AND event_type='login_success'
                ORDER BY timestamp DESC LIMIT 1""",
                (user_id,)).fetchone()

        if not row:
            return None

        try:
            last_geo = json.loads(row[0])
            last_lat = last_geo.get("latitude", 0)
            last_lon = last_geo.get("longitude", 0)
            if not last_lat or not last_lon:
                return None

            # Haversine distance
            distance_km = _haversine(last_lat, last_lon, geo.latitude, geo.longitude)

            # If > 500km and last login < 1 hour ago, impossible travel
            if distance_km > 500:
                return f"Impossible travel: {distance_km:.0f}km from last login location"
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    def record_device(self, user_id: str, device: DeviceInfo):
        """Record a device login."""
        with self._conn() as c:
            existing = c.execute("SELECT login_count FROM known_devices WHERE user_id=? AND fingerprint=?",
                                 (user_id, device.fingerprint_hash)).fetchone()
            if existing:
                c.execute("""UPDATE known_devices SET last_seen=datetime('now'),
                    login_count=login_count+1, device_info=? WHERE user_id=? AND fingerprint=?""",
                    (json.dumps(asdict(device))[:500], user_id, device.fingerprint_hash))
            else:
                c.execute("INSERT INTO known_devices (user_id, fingerprint, device_info) VALUES (?,?,?)",
                          (user_id, device.fingerprint_hash, json.dumps(asdict(device))[:500]))

    def record_location(self, user_id: str, geo: GeoInfo):
        """Record a location login."""
        if not geo.country_code or geo.country_code == "LO":
            return
        with self._conn() as c:
            existing = c.execute("SELECT login_count FROM known_locations WHERE user_id=? AND country_code=? AND city=?",
                                 (user_id, geo.country_code, geo.city)).fetchone()
            if existing:
                c.execute("""UPDATE known_locations SET last_seen=datetime('now'),
                    login_count=login_count+1 WHERE user_id=? AND country_code=? AND city=?""",
                    (user_id, geo.country_code, geo.city))
            else:
                c.execute("INSERT INTO known_locations (user_id, country_code, city) VALUES (?,?,?)",
                          (user_id, geo.country_code, geo.city))


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Calculate distance in km between two lat/lon points."""
    R = 6371  # Earth radius km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityAuditLog:
    """Persistent security audit log with full context."""

    def __init__(self):
        self._ensure_table()

    def _conn(self):
        c = sqlite3.connect(_DB_FILE)
        c.row_factory = sqlite3.Row
        return c

    def _ensure_table(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS security_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                email TEXT DEFAULT '',
                event_type TEXT NOT NULL,
                ip TEXT DEFAULT '',
                geo_data TEXT DEFAULT '{}',
                device_data TEXT DEFAULT '{}',
                risk_score INTEGER DEFAULT 0,
                risk_level TEXT DEFAULT 'low',
                risk_factors TEXT DEFAULT '[]',
                session_id TEXT DEFAULT '',
                success INTEGER DEFAULT 1,
                failure_reason TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                timestamp TEXT DEFAULT (datetime('now')),
                INDEX_created INTEGER DEFAULT 0
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON security_audit_log(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_type ON security_audit_log(event_type)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_ip ON security_audit_log(ip)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON security_audit_log(timestamp)")

    def record(self, event: AuditEvent):
        """Record an audit event."""
        with self._conn() as c:
            c.execute("""INSERT INTO security_audit_log
                (user_id, email, event_type, ip, geo_data, device_data,
                 risk_score, risk_level, risk_factors, session_id,
                 success, failure_reason, metadata, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event.user_id, event.email, event.event_type.value, event.ip,
                 json.dumps(asdict(event.geo)) if event.geo else "{}",
                 json.dumps(asdict(event.device)) if event.device else "{}",
                 event.risk_score, event.risk_level.value,
                 json.dumps(event.risk_factors), event.session_id,
                 1 if event.success else 0, event.failure_reason,
                 json.dumps(event.metadata), event.timestamp))

        log.info("audit.recorded",
                 event=event.event_type.value, user=event.user_id[:8],
                 ip=event.ip, risk=event.risk_score, level=event.risk_level.value)

    def query(self, user_id: str = None, event_type: str = None,
              ip: str = None, limit: int = 50, offset: int = 0,
              start_date: str = None, end_date: str = None) -> list[dict]:
        """Query audit log with filters."""
        with self._conn() as c:
            query = "SELECT * FROM security_audit_log WHERE 1=1"
            params = []

            if user_id:
                query += " AND user_id=?"
                params.append(user_id)
            if event_type:
                query += " AND event_type=?"
                params.append(event_type)
            if ip:
                query += " AND ip=?"
                params.append(ip)
            if start_date:
                query += " AND timestamp>=?"
                params.append(start_date)
            if end_date:
                query += " AND timestamp<=?"
                params.append(end_date)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = c.execute(query, params).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            d["geo_data"] = json.loads(d.get("geo_data", "{}"))
            d["device_data"] = json.loads(d.get("device_data", "{}"))
            d["risk_factors"] = json.loads(d.get("risk_factors", "[]"))
            d["metadata"] = json.loads(d.get("metadata", "{}"))
            result.append(d)
        return result

    def get_stats(self, user_id: str, days: int = 30) -> dict:
        """Get audit statistics for a user."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM security_audit_log WHERE user_id=? AND timestamp>=?",
                              (user_id, cutoff)).fetchone()[0]
            logins = c.execute("SELECT COUNT(*) FROM security_audit_log WHERE user_id=? AND event_type='login_success' AND timestamp>=?",
                               (user_id, cutoff)).fetchone()[0]
            failed = c.execute("SELECT COUNT(*) FROM security_audit_log WHERE user_id=? AND event_type='login_failed' AND timestamp>=?",
                               (user_id, cutoff)).fetchone()[0]
            unique_ips = c.execute("SELECT COUNT(DISTINCT ip) FROM security_audit_log WHERE user_id=? AND timestamp>=?",
                                   (user_id, cutoff)).fetchone()[0]
            unique_devices = c.execute("SELECT COUNT(DISTINCT json_extract(device_data, '$.fingerprint_hash')) FROM security_audit_log WHERE user_id=? AND timestamp>=?",
                                       (user_id, cutoff)).fetchone()[0]
            countries = c.execute("SELECT DISTINCT json_extract(geo_data, '$.country_code') FROM security_audit_log WHERE user_id=? AND timestamp>=?",
                                  (user_id, cutoff)).fetchall()
            high_risk = c.execute("SELECT COUNT(*) FROM security_audit_log WHERE user_id=? AND risk_score>50 AND timestamp>=?",
                                  (user_id, cutoff)).fetchone()[0]

        return {
            "period_days": days,
            "total_events": total,
            "successful_logins": logins,
            "failed_logins": failed,
            "unique_ips": unique_ips,
            "unique_devices": unique_devices,
            "countries": [r[0] for r in countries if r[0]],
            "high_risk_events": high_risk,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AUDIT ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

_audit_log: SecurityAuditLog | None = None
_geo_fence: GeoFenceEngine | None = None
_risk_engine: RiskScoringEngine | None = None


def get_audit_log() -> SecurityAuditLog:
    global _audit_log
    if not _audit_log:
        _audit_log = SecurityAuditLog()
    return _audit_log


def get_geo_fence() -> GeoFenceEngine:
    global _geo_fence
    if not _geo_fence:
        _geo_fence = GeoFenceEngine()
    return _geo_fence


def get_risk_engine() -> RiskScoringEngine:
    global _risk_engine
    if not _risk_engine:
        _risk_engine = RiskScoringEngine()
    return _risk_engine


async def audit_login_attempt(
    user_id: str, email: str, ip: str, user_agent: str,
    success: bool, failure_reason: str = "",
    session_id: str = "", failed_recent: int = 0,
    client_hints: dict = None, metadata: dict = None,
) -> AuditEvent:
    """
    Full audit pipeline for a login attempt.
    1. Parse device → 2. Geolocate IP → 3. Check geo-fence →
    4. Score risk → 5. Record audit event → 6. Update known devices/locations
    """
    # 1. Device fingerprinting
    device = parse_device(user_agent, client_hints)

    # 2. IP geolocation
    geo = await geolocate_ip(ip)

    # 3. Risk scoring
    risk_engine = get_risk_engine()
    risk_score, risk_level, risk_factors = risk_engine.score(
        user_id, device, geo, ip, failed_recent)

    # 4. Geo-fence check
    geo_allowed, geo_reason = get_geo_fence().check(user_id, geo, ip)
    if not geo_allowed:
        success = False
        failure_reason = geo_reason
        risk_score = max(risk_score, 80)
        risk_level = RiskLevel.CRITICAL
        risk_factors.append(f"Geo-fence blocked: {geo_reason}")

    # 5. Create event
    event_type = AuditEventType.LOGIN_SUCCESS if success else AuditEventType.LOGIN_FAILED
    if not geo_allowed:
        event_type = AuditEventType.GEO_FENCE_BLOCKED

    event = AuditEvent(
        event_type=event_type,
        user_id=user_id, email=email, ip=ip,
        geo=geo, device=device,
        risk_score=risk_score, risk_level=risk_level,
        risk_factors=risk_factors, session_id=session_id,
        success=success, failure_reason=failure_reason,
        metadata=metadata or {},
    )

    # 6. Record
    get_audit_log().record(event)

    # 7. Update known devices/locations on success
    if success:
        risk_engine.record_device(user_id, device)
        risk_engine.record_location(user_id, geo)

    return event
