-- ─────────────────────────────────────────────────────────────────────────────
-- Alchemy Platform v0.4 — Initial Database Schema
-- Run on PostgreSQL 15+ / TimescaleDB
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email                 VARCHAR(255) NOT NULL UNIQUE,
    username              VARCHAR(64)  NOT NULL UNIQUE,
    full_name             VARCHAR(255) NOT NULL,
    password_hash         VARCHAR(255) NOT NULL,

    -- RBAC
    role                  VARCHAR(32)  NOT NULL DEFAULT 'trader',
    status                VARCHAR(32)  NOT NULL DEFAULT 'pending',

    -- 2FA
    totp_secret_enc       TEXT,
    totp_enabled          BOOLEAN      NOT NULL DEFAULT FALSE,
    totp_backup_codes     TEXT,
    totp_verified_at      TIMESTAMPTZ,

    -- Security tracking
    failed_login_count    INTEGER      NOT NULL DEFAULT 0,
    locked_until          TIMESTAMPTZ,
    last_login_at         TIMESTAMPTZ,
    last_login_ip         VARCHAR(45),
    last_password_change  TIMESTAMPTZ,
    must_change_password  BOOLEAN      NOT NULL DEFAULT FALSE,

    -- Email verification
    email_verified        BOOLEAN      NOT NULL DEFAULT FALSE,
    email_verify_token    VARCHAR(128),
    email_verify_expires  TIMESTAMPTZ,

    -- Password reset
    reset_token           VARCHAR(128),
    reset_token_expires   TIMESTAMPTZ,

    -- Profile
    avatar_url            VARCHAR(512),
    timezone_str          VARCHAR(64)  NOT NULL DEFAULT 'Asia/Kolkata',
    preferred_exchange    VARCHAR(32)  NOT NULL DEFAULT 'paper',

    -- Timestamps
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_email     ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_username  ON users (username);
CREATE INDEX IF NOT EXISTS ix_users_status    ON users (status);
CREATE INDEX IF NOT EXISTS ix_users_role      ON users (role);

-- ── user_sessions ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_sessions (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash    VARCHAR(128) NOT NULL UNIQUE,
    access_jti            VARCHAR(128),
    ip_address            VARCHAR(45),
    user_agent            VARCHAR(512),
    device_type           VARCHAR(64),
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at            TIMESTAMPTZ  NOT NULL,
    last_used_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_sessions_user_id      ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_sessions_refresh_hash ON user_sessions (refresh_token_hash);
CREATE INDEX IF NOT EXISTS ix_sessions_access_jti   ON user_sessions (access_jti);
CREATE INDEX IF NOT EXISTS ix_sessions_active       ON user_sessions (is_active, expires_at);

-- ── audit_logs ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(128) NOT NULL,
    resource    VARCHAR(128),
    ip_address  VARCHAR(45),
    user_agent  VARCHAR(512),
    status      VARCHAR(32)  NOT NULL,
    detail      TEXT,
    risk_score  INTEGER      NOT NULL DEFAULT 0,
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_user_timestamp ON audit_logs (user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_audit_action         ON audit_logs (action);
CREATE INDEX IF NOT EXISTS ix_audit_risk_score     ON audit_logs (risk_score) WHERE risk_score >= 50;

-- Convert audit_logs to hypertable for efficient time-series queries (TimescaleDB)
-- SELECT create_hypertable('audit_logs', 'timestamp', if_not_exists => TRUE);

-- ── update_updated_at trigger ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── Roles check constraint ────────────────────────────────────────────────────
ALTER TABLE users ADD CONSTRAINT chk_users_role
    CHECK (role IN ('super_admin', 'admin', 'trader', 'analyst', 'viewer'));

ALTER TABLE users ADD CONSTRAINT chk_users_status
    CHECK (status IN ('active', 'inactive', 'locked', 'pending', 'banned'));

-- ── Bootstrap super admin (change password immediately!) ─────────────────────
-- INSERT INTO users (email, username, full_name, password_hash, role, status, email_verified)
-- VALUES (
--     'admin@alchemy.in',
--     'superadmin',
--     'Super Admin',
--     crypt('CHANGE_ME_ON_FIRST_LOGIN', gen_salt('bf', 12)),
--     'super_admin',
--     'active',
--     TRUE
-- ) ON CONFLICT (email) DO NOTHING;
