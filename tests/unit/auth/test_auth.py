"""
tests/unit/auth/test_auth.py
Unit tests for auth security primitives, password policy, TOTP, and JWT.
"""
import pytest
import time
from datetime import datetime, timezone, timedelta


# ── PasswordPolicy ────────────────────────────────────────────────────────────
class TestPasswordPolicy:
    def test_strong_password_passes(self):
        from alchemy.auth.security import PasswordPolicy
        errors = PasswordPolicy.validate("Tr@d3rAlch3my!2024")
        assert errors == []

    def test_too_short_fails(self):
        from alchemy.auth.security import PasswordPolicy
        errors = PasswordPolicy.validate("Sh0rt!1")
        assert any("12" in e for e in errors)

    def test_no_uppercase_fails(self):
        from alchemy.auth.security import PasswordPolicy
        errors = PasswordPolicy.validate("lowercase123!@#abc")
        assert any("uppercase" in e.lower() for e in errors)

    def test_no_digit_fails(self):
        from alchemy.auth.security import PasswordPolicy
        errors = PasswordPolicy.validate("NoDigitsHere!@#ABCDE")
        assert any("digit" in e.lower() for e in errors)

    def test_no_special_fails(self):
        from alchemy.auth.security import PasswordPolicy
        errors = PasswordPolicy.validate("NoSpecialChar1234ABC")
        assert any("special" in e.lower() for e in errors)

    def test_common_password_rejected(self):
        from alchemy.auth.security import PasswordPolicy
        errors = PasswordPolicy.validate("password123")
        assert len(errors) > 0

    def test_strength_score_strong(self):
        from alchemy.auth.security import PasswordPolicy
        score = PasswordPolicy.strength_score("Tr@d3rAlch3my!2024")
        assert score >= 75

    def test_strength_score_weak(self):
        from alchemy.auth.security import PasswordPolicy
        score = PasswordPolicy.strength_score("abc")
        assert score < 40

    def test_max_length_enforced(self):
        from alchemy.auth.security import PasswordPolicy
        long_pwd = "A" * 150 + "!1a"
        errors = PasswordPolicy.validate(long_pwd)
        assert any("128" in e for e in errors)


# ── bcrypt password hashing ───────────────────────────────────────────────────
class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        from alchemy.auth.security import hash_password
        h = hash_password("MySecureP@ss123")
        assert h != "MySecureP@ss123"
        assert h.startswith("$2b$")

    def test_verify_correct_password(self):
        from alchemy.auth.security import hash_password, verify_password
        h = hash_password("Alchemy#2024!")
        assert verify_password("Alchemy#2024!", h) is True

    def test_verify_wrong_password(self):
        from alchemy.auth.security import hash_password, verify_password
        h = hash_password("CorrectP@ss123")
        assert verify_password("WrongP@ss456", h) is False

    def test_hash_is_different_each_time(self):
        from alchemy.auth.security import hash_password
        h1 = hash_password("SamePwd!123ABC")
        h2 = hash_password("SamePwd!123ABC")
        assert h1 != h2   # Different salts

    def test_timing_safe_wrong_hash(self):
        from alchemy.auth.security import verify_password
        # Should not raise even on malformed hash
        result = verify_password("anything", "not_a_valid_hash")
        assert result is False


# ── JWT tokens ────────────────────────────────────────────────────────────────
class TestJWT:
    def test_create_and_decode_access_token(self):
        from alchemy.auth.security import create_access_token, decode_access_token
        token = create_access_token("user-123", "test@example.com", "trader")
        payload = decode_access_token(token)
        assert payload["sub"]   == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["role"]  == "trader"
        assert payload["type"]  == "access"

    def test_expired_token_raises(self):
        import jwt
        from alchemy.auth.security import decode_access_token, _get_jwt_secret, JWT_ALGORITHM
        # Create already-expired token
        payload = {
            "sub": "u1", "email": "e@e.com", "role": "trader",
            "jti": "test", "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=1),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=30),
        }
        expired_token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(expired_token)

    def test_tampered_token_raises(self):
        import jwt
        from alchemy.auth.security import create_access_token, decode_access_token
        token = create_access_token("u1", "e@e.com", "trader")
        # Tamper with signature
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".invalidsignature"
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(tampered)

    def test_wrong_token_type_raises(self):
        import jwt
        from alchemy.auth.security import _get_jwt_secret, JWT_ALGORITHM, decode_access_token
        payload = {
            "sub": "u1", "email": "e@e.com", "role": "trader",
            "jti": "test", "type": "refresh",  # wrong type
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_refresh_token_hash_consistent(self):
        from alchemy.auth.security import create_refresh_token, hash_refresh_token
        raw, hashed = create_refresh_token()
        assert hash_refresh_token(raw) == hashed

    def test_refresh_tokens_are_unique(self):
        from alchemy.auth.security import create_refresh_token
        raw1, _ = create_refresh_token()
        raw2, _ = create_refresh_token()
        assert raw1 != raw2


# ── TOTP 2FA ─────────────────────────────────────────────────────────────────
class TestTOTP:
    def test_generate_valid_secret(self):
        from alchemy.auth.security import TOTPManager
        secret = TOTPManager.generate_secret()
        assert len(secret) >= 16
        # Should be valid base32
        import base64
        base64.b32decode(secret, casefold=True)

    def test_verify_current_code(self):
        from alchemy.auth.security import TOTPManager
        secret = TOTPManager.generate_secret()
        totp   = TOTPManager.get_totp(secret)
        code   = totp.now()
        assert TOTPManager.verify(secret, code) is True

    def test_reject_wrong_code(self):
        from alchemy.auth.security import TOTPManager
        secret = TOTPManager.generate_secret()
        assert TOTPManager.verify(secret, "000000") is False or \
               TOTPManager.verify(secret, "999999") is False

    def test_verify_backup_code(self):
        from alchemy.auth.security import TOTPManager
        secret  = TOTPManager.generate_secret()
        backups = ["ABCD-EFGH-IJKL"]
        assert TOTPManager.verify(secret, "ABCD-EFGH-IJKL", backups) is True

    def test_generate_backup_codes(self):
        from alchemy.auth.security import TOTPManager
        codes = TOTPManager.generate_backup_codes(10)
        assert len(codes) == 10
        assert all(len(c) == 14 for c in codes)  # XXXX-XXXX-XXXX
        assert len(set(codes)) == 10              # All unique

    def test_qr_code_is_data_url(self):
        from alchemy.auth.security import TOTPManager
        secret = TOTPManager.generate_secret()
        qr = TOTPManager.generate_qr_code(secret, "test@alchemy.in")
        assert qr.startswith("data:image/png;base64,")
        assert len(qr) > 100


# ── SecretEncryptor ───────────────────────────────────────────────────────────
class TestSecretEncryptor:
    def test_encrypt_decrypt_round_trip(self):
        from alchemy.auth.security import SecretEncryptor
        enc = SecretEncryptor()
        original = "JBSWY3DPEHPK3PXP"  # TOTP secret
        encrypted = enc.encrypt(original)
        assert encrypted != original
        assert enc.decrypt(encrypted) == original

    def test_different_ciphertext_each_time(self):
        """Fernet uses random IV — same plaintext → different ciphertext."""
        from alchemy.auth.security import SecretEncryptor
        enc = SecretEncryptor()
        if enc._fernet:   # Only if cryptography installed
            c1 = enc.encrypt("secret")
            c2 = enc.encrypt("secret")
            assert c1 != c2


# ── RBAC ─────────────────────────────────────────────────────────────────────
class TestRBAC:
    def test_super_admin_has_all_permissions(self):
        from alchemy.users.models import UserRole, has_permission
        assert has_permission(UserRole.SUPER_ADMIN, "trading:execute") is True
        assert has_permission(UserRole.SUPER_ADMIN, "admin:dashboard") is True
        assert has_permission(UserRole.SUPER_ADMIN, "any:permission")  is True

    def test_trader_can_execute(self):
        from alchemy.users.models import UserRole, has_permission
        assert has_permission(UserRole.TRADER, "trading:execute") is True
        assert has_permission(UserRole.TRADER, "workflows:write") is True

    def test_trader_cannot_admin(self):
        from alchemy.users.models import UserRole, has_permission
        assert has_permission(UserRole.TRADER, "admin:dashboard") is False
        assert has_permission(UserRole.TRADER, "users:delete")    is False

    def test_viewer_readonly(self):
        from alchemy.users.models import UserRole, has_permission
        assert has_permission(UserRole.VIEWER, "trading:read")  is True
        assert has_permission(UserRole.VIEWER, "trading:write") is False
        assert has_permission(UserRole.VIEWER, "trading:execute") is False

    def test_analyst_no_execution(self):
        from alchemy.users.models import UserRole, has_permission
        assert has_permission(UserRole.ANALYST, "trading:read")    is True
        assert has_permission(UserRole.ANALYST, "trading:execute") is False

    def test_invalid_role_no_permission(self):
        from alchemy.users.models import UserRole, has_permission
        assert has_permission(UserRole.VIEWER, "nonexistent:perm") is False


# ── User Model ────────────────────────────────────────────────────────────────
class TestUserModel:
    def _make_user(self, **kwargs):
        from alchemy.users.models import User, UserStatus
        import uuid
        return User(
            id=uuid.uuid4(),
            email="test@alchemy.in",
            username="testuser",
            full_name="Test User",
            password_hash="$2b$12$dummyhash",
            **kwargs
        )

    def test_user_not_locked_initially(self):
        user = self._make_user()
        assert user.is_locked() is False

    def test_user_locked_after_max_attempts(self):
        user = self._make_user()
        for _ in range(4):
            should_lock = user.increment_failed_logins(5)
        should_lock = user.increment_failed_logins(5)
        assert should_lock is True

    def test_reset_failed_logins(self):
        user = self._make_user()
        user.failed_login_count = 4
        user.reset_failed_logins()
        assert user.failed_login_count == 0
        assert user.locked_until is None

    def test_safe_dict_no_password(self):
        user = self._make_user()
        d = user.safe_dict()
        assert "password_hash" not in d
        assert "totp_secret_enc" not in d
        assert "email" in d
        assert "role" in d

    def test_locked_until_respected(self):
        user = self._make_user()
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)
        assert user.is_locked() is True

    def test_expired_lock_not_locked(self):
        user = self._make_user()
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert user.is_locked() is False


# ── Rate Limiter ──────────────────────────────────────────────────────────────
class TestRateLimiter:
    def test_allows_under_limit(self):
        from alchemy.auth.middleware import InMemoryRateLimiter
        rl = InMemoryRateLimiter()
        for _ in range(4):
            allowed, _ = rl.is_allowed("test:ip", 5, 60)
            assert allowed is True

    def test_blocks_at_limit(self):
        from alchemy.auth.middleware import InMemoryRateLimiter
        rl = InMemoryRateLimiter()
        for _ in range(5):
            rl.is_allowed("block:ip", 5, 60)
        allowed, retry = rl.is_allowed("block:ip", 5, 60)
        assert allowed is False
        assert retry > 0

    def test_different_keys_independent(self):
        from alchemy.auth.middleware import InMemoryRateLimiter
        rl = InMemoryRateLimiter()
        for _ in range(5):
            rl.is_allowed("ip1:key", 5, 60)
        allowed, _ = rl.is_allowed("ip2:key", 5, 60)
        assert allowed is True
