"""
alchemy.tokens.vault
====================
AES-256-GCM encrypted token vault.

Tokens are encrypted at rest using a master key derived from
PBKDF2-HMAC-SHA256. The vault stores encrypted JSON on disk
(or Redis for distributed deployments).

Usage::

    vault = TokenVault(master_key="your-32-byte-key")
    vault.store("kite", token.model_dump())
    data = vault.retrieve("kite")
    vault.delete("kite")
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

import structlog

log = structlog.get_logger(__name__)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    log.warning("vault.crypto_missing", hint="pip install cryptography")


VAULT_DIR  = Path.home() / ".alchemy" / "vault"
SALT_FILE  = VAULT_DIR  / ".salt"


class TokenVault:
    """
    AES-256-GCM encrypted persistent token vault.

    Each token is stored as a separate encrypted file named
    {exchange}.enc inside ~/.alchemy/vault/.

    Falls back to plaintext JSON if cryptography is unavailable
    (development mode only — never use in production).
    """

    def __init__(
        self,
        master_key: Optional[str] = None,
        vault_dir:  Optional[Path] = None,
    ) -> None:
        self._vault_dir = vault_dir or VAULT_DIR
        self._vault_dir.mkdir(parents=True, exist_ok=True)
        self._key = self._derive_key(master_key or self._get_master_key())
        log.info("vault.ready", path=str(self._vault_dir),
                 encrypted=CRYPTO_AVAILABLE)

    # ── Public API ────────────────────────────────────────────────────────────

    def store(self, exchange: str, data: dict) -> None:
        """Encrypt and persist a token dict."""
        payload = json.dumps(data, default=str).encode()
        if CRYPTO_AVAILABLE and self._key:
            ciphertext = self._encrypt(payload)
            self._write(exchange, ciphertext, binary=True)
        else:
            self._write(exchange, payload, binary=False)
        log.info("vault.stored", exchange=exchange)

    def retrieve(self, exchange: str) -> Optional[dict]:
        """Decrypt and return a token dict, or None if not found."""
        raw = self._read(exchange)
        if raw is None:
            return None
        try:
            if CRYPTO_AVAILABLE and self._key:
                plaintext = self._decrypt(raw)
            else:
                plaintext = raw
            return json.loads(plaintext)
        except Exception as e:
            log.error("vault.decrypt_failed", exchange=exchange, error=str(e))
            return None

    def delete(self, exchange: str) -> bool:
        """Delete a stored token. Returns True if deleted."""
        path = self._path(exchange)
        if path.exists():
            path.unlink()
            log.info("vault.deleted", exchange=exchange)
            return True
        return False

    def list_exchanges(self) -> list[str]:
        """Return list of exchanges with stored tokens."""
        return [p.stem for p in self._vault_dir.glob("*.enc")]

    def exists(self, exchange: str) -> bool:
        return self._path(exchange).exists()

    def rotate_key(self, new_master_key: str) -> int:
        """Re-encrypt all tokens with a new master key. Returns count."""
        count = 0
        exchanges = self.list_exchanges()
        old_key = self._key
        new_key = self._derive_key(new_master_key)
        for ex in exchanges:
            raw  = self._read(ex)
            if raw is None:
                continue
            try:
                plaintext = self._decrypt_with(raw, old_key) if CRYPTO_AVAILABLE else raw
                data = json.loads(plaintext)
                self._key = new_key
                self.store(ex, data)
                count += 1
            except Exception as e:
                log.error("vault.rotate_error", exchange=ex, error=str(e))
        self._key = new_key
        log.info("vault.key_rotated", tokens_re_encrypted=count)
        return count

    # ── Crypto ────────────────────────────────────────────────────────────────

    def _derive_key(self, master: str) -> Optional[bytes]:
        if not CRYPTO_AVAILABLE:
            return None
        salt = self._get_or_create_salt()
        kdf  = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=260_000,
            backend=default_backend(),
        )
        return kdf.derive(master.encode())

    def _encrypt(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(12)
        aes   = AESGCM(self._key)
        ct    = aes.encrypt(nonce, plaintext, None)
        return nonce + ct   # Prepend nonce

    def _decrypt(self, ciphertext: bytes) -> bytes:
        return self._decrypt_with(ciphertext, self._key)

    def _decrypt_with(self, ciphertext: bytes, key: bytes) -> bytes:
        nonce = ciphertext[:12]
        ct    = ciphertext[12:]
        aes   = AESGCM(key)
        return aes.decrypt(nonce, ct, None)

    # ── Storage ───────────────────────────────────────────────────────────────

    def _path(self, exchange: str) -> Path:
        return self._vault_dir / f"{exchange}.enc"

    def _write(self, exchange: str, data: bytes, binary: bool) -> None:
        path = self._path(exchange)
        mode = "wb" if binary else "w"
        with open(path, mode) as f:
            f.write(data if binary else data.decode())

    def _read(self, exchange: str) -> Optional[bytes]:
        path = self._path(exchange)
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return f.read()

    def _get_or_create_salt(self) -> bytes:
        if SALT_FILE.exists():
            return SALT_FILE.read_bytes()
        salt = os.urandom(32)
        SALT_FILE.write_bytes(salt)
        return salt

    def _get_master_key(self) -> str:
        """Get master key from env or generate a default (dev mode)."""
        key = os.environ.get("ALCHEMY_VAULT_KEY")
        if key:
            return key
        log.warning("vault.no_master_key",
                    msg="Set ALCHEMY_VAULT_KEY env var for production security")
        return hashlib.sha256(b"alchemy-dev-key-CHANGE-IN-PRODUCTION").hexdigest()
