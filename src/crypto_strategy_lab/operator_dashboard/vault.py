"""Current-user Windows DPAPI credential vault with no plaintext fallback."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CRYPTPROTECT_UI_FORBIDDEN: Final = 0x1


class CredentialVaultUnavailable(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


@dataclass(frozen=True, slots=True)
class BinanceCredentials:
    api_key: str
    api_secret: str


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _require_windows() -> None:
    if sys.platform != "win32":
        raise CredentialVaultUnavailable("WINDOWS_DPAPI_REQUIRED_NO_PLAINTEXT_FALLBACK")


def _protect(plaintext: bytes) -> bytes:
    _require_windows()
    input_blob, input_buffer = _blob(plaintext)
    output_blob = _DataBlob()
    try:
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "CryptoChange Binance credentials",
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        if not ok:
            raise CredentialVaultUnavailable(f"DPAPI_PROTECT_FAILED_{ctypes.get_last_error()}")
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.memset(input_buffer, 0, len(plaintext))
        if output_blob.pbData:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _unprotect(ciphertext: bytes) -> bytes:
    _require_windows()
    input_blob, input_buffer = _blob(ciphertext)
    output_blob = _DataBlob()
    try:
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        if not ok:
            raise CredentialVaultUnavailable(f"DPAPI_UNPROTECT_FAILED_{ctypes.get_last_error()}")
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.memset(input_buffer, 0, len(ciphertext))
        if output_blob.pbData:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)


class DpapiCredentialVault:
    """Persist one opaque, current-user protected blob outside version control."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, api_key: str, api_secret: str) -> None:
        if not api_key.strip() or not api_secret:
            raise ValueError("API_KEY_AND_SECRET_REQUIRED")
        payload = json.dumps(
            {"api_key": api_key.strip(), "api_secret": api_secret},
            separators=(",", ":"),
        ).encode()
        protected = _protect(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(protected)
        os.replace(temporary, self.path)

    def load(self) -> BinanceCredentials:
        try:
            protected = self.path.read_bytes()
        except FileNotFoundError as error:
            raise CredentialVaultUnavailable("CREDENTIALS_NOT_CONFIGURED") from error
        plaintext = bytearray(_unprotect(protected))
        try:
            payload = json.loads(plaintext.decode())
            api_key = payload.get("api_key")
            api_secret = payload.get("api_secret")
            if not isinstance(api_key, str) or not isinstance(api_secret, str):
                raise CredentialVaultUnavailable("CREDENTIAL_VAULT_CORRUPT")
            return BinanceCredentials(api_key=api_key, api_secret=api_secret)
        finally:
            for index in range(len(plaintext)):
                plaintext[index] = 0

    def delete(self) -> bool:
        if not self.path.exists():
            return False
        self.path.unlink()
        return True

    def configured(self) -> bool:
        return self.path.is_file() and self.path.stat().st_size > 0
