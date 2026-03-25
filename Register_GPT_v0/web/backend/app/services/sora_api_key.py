import hashlib
import secrets
from typing import Dict, Optional

from fastapi import Depends, Header, HTTPException

from app.database import get_db, init_db
from app.routers.auth import get_optional_user


SORA_API_KEY_SCOPE_TEXT = "text_to_video"
SORA_API_KEY_SCOPE_IMAGE = "image_to_video"
SORA_API_KEY_SCOPE_ALL = "all_video"

_SORA_API_KEY_SCOPE_ALIASES = {
    "text": SORA_API_KEY_SCOPE_TEXT,
    "text_to_video": SORA_API_KEY_SCOPE_TEXT,
    "text-video": SORA_API_KEY_SCOPE_TEXT,
    "text2video": SORA_API_KEY_SCOPE_TEXT,
    "文生视频": SORA_API_KEY_SCOPE_TEXT,
    "image": SORA_API_KEY_SCOPE_IMAGE,
    "image_to_video": SORA_API_KEY_SCOPE_IMAGE,
    "image-video": SORA_API_KEY_SCOPE_IMAGE,
    "image2video": SORA_API_KEY_SCOPE_IMAGE,
    "图生视频": SORA_API_KEY_SCOPE_IMAGE,
    "all": SORA_API_KEY_SCOPE_ALL,
    "all_video": SORA_API_KEY_SCOPE_ALL,
    "both": SORA_API_KEY_SCOPE_ALL,
    "combined": SORA_API_KEY_SCOPE_ALL,
    "hybrid": SORA_API_KEY_SCOPE_ALL,
    "文生+图生": SORA_API_KEY_SCOPE_ALL,
}

_SORA_API_KEY_SCOPE_LABELS = {
    SORA_API_KEY_SCOPE_TEXT: "文生视频",
    SORA_API_KEY_SCOPE_IMAGE: "图生视频",
    SORA_API_KEY_SCOPE_ALL: "文生+图生",
}

_SORA_API_KEY_SCOPE_CAPABILITIES = {
    SORA_API_KEY_SCOPE_TEXT: {SORA_API_KEY_SCOPE_TEXT},
    SORA_API_KEY_SCOPE_IMAGE: {SORA_API_KEY_SCOPE_IMAGE},
    SORA_API_KEY_SCOPE_ALL: {SORA_API_KEY_SCOPE_TEXT, SORA_API_KEY_SCOPE_IMAGE},
}


def generate_sora_api_key() -> str:
    # 32 bytes random -> 43 chars base64url；统一加前缀方便识别
    token = secrets.token_urlsafe(32).replace("-", "").replace("_", "")
    return f"srk_{token}"


def hash_sora_api_key(raw_key: str) -> str:
    return hashlib.sha256((raw_key or "").encode("utf-8")).hexdigest()


def mask_sora_api_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if not key:
        return ""
    if len(key) <= 14:
        return f"{key[:4]}***{key[-2:]}"
    return f"{key[:12]}...{key[-4:]}"


def normalize_sora_api_key_scope(scope: str) -> str:
    value = (scope or "").strip().lower()
    return _SORA_API_KEY_SCOPE_ALIASES.get(value, SORA_API_KEY_SCOPE_TEXT)


def sora_api_key_scope_label(scope: str) -> str:
    normalized = normalize_sora_api_key_scope(scope)
    return _SORA_API_KEY_SCOPE_LABELS.get(normalized, _SORA_API_KEY_SCOPE_LABELS[SORA_API_KEY_SCOPE_TEXT])


def sora_api_key_scope_allows(scope: str, capability: str) -> bool:
    normalized_scope = normalize_sora_api_key_scope(scope)
    normalized_capability = normalize_sora_api_key_scope(capability)
    return normalized_capability in _SORA_API_KEY_SCOPE_CAPABILITIES.get(normalized_scope, set())


def _extract_api_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
    x_sora_api_key: Optional[str],
) -> str:
    key = (x_sora_api_key or "").strip() or (x_api_key or "").strip()
    if key:
        return key
    auth = (authorization or "").strip()
    if not auth:
        return ""
    parts = auth.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        candidate = parts[1].strip()
    else:
        candidate = auth
    if candidate.startswith("srk_"):
        return candidate
    return ""


def authenticate_sora_api_key(raw_key: str) -> Optional[Dict]:
    key = (raw_key or "").strip()
    if not key:
        return None
    key_hash = hash_sora_api_key(key)
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """SELECT id, account_id, name, is_active, COALESCE(scope, ?)
               FROM sora_api_keys
               WHERE key_hash = ?
               LIMIT 1""",
            (SORA_API_KEY_SCOPE_TEXT, key_hash),
        )
        row = c.fetchone()
        if not row:
            return None
        if not bool(row[3]):
            return None
        c.execute("UPDATE sora_api_keys SET last_used_at = datetime('now') WHERE id = ?", (row[0],))
    return {
        "id": row[0],
        "account_id": row[1] if row[1] != 0 else None,  # 0 = 池模式 → None
        "name": row[2] or "",
        "scope": normalize_sora_api_key_scope(row[4] or SORA_API_KEY_SCOPE_TEXT),
    }


def get_sora_api_caller(
    username: Optional[str] = Depends(get_optional_user),
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_sora_api_key: Optional[str] = Header(default=None, alias="X-Sora-Api-Key"),
):
    """
    Sora 调用支持两种鉴权：
    1) 管理员 JWT（Authorization: Bearer <admin_token>）
    2) 本地 Sora API Key（Authorization: Bearer srk_xxx / X-API-Key / X-Sora-Api-Key）
    """
    if username:
        return {
            "auth_type": "admin",
            "username": username,
            "api_key_id": None,
            "account_id": None,
        }

    raw_key = _extract_api_key(authorization=authorization, x_api_key=x_api_key, x_sora_api_key=x_sora_api_key)
    if not raw_key:
        raise HTTPException(status_code=401, detail="Not authenticated")

    key_row = authenticate_sora_api_key(raw_key)
    if not key_row:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return {
        "auth_type": "api_key",
        "username": "",
        "api_key_id": key_row["id"],
        "account_id": key_row["account_id"],
        "api_key_scope": key_row["scope"],
        "api_key_scope_label": sora_api_key_scope_label(key_row["scope"]),
    }
