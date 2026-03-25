from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database import get_db, init_db
from app.routers.auth import get_current_user
from app.services.sora_api_key import (
    SORA_API_KEY_SCOPE_TEXT,
    generate_sora_api_key,
    hash_sora_api_key,
    mask_sora_api_key,
    normalize_sora_api_key_scope,
    sora_api_key_scope_label,
)

router = APIRouter(prefix="/api/sora-keys", tags=["sora-keys"])


class CreateSoraKeyBody(BaseModel):
    account_id: int = 0  # 0 = 池模式（自动轮换）
    name: str = ""
    scope: str = SORA_API_KEY_SCOPE_TEXT


@router.get("")
def list_sora_api_keys(
    username: str = Depends(get_current_user),
    account_id: Optional[int] = Query(None, ge=0),
    active_only: bool = Query(True),
    scope: str = Query(""),
    key_mode: str = Query(""),
):
    init_db()
    where = []
    params = []
    if account_id is not None:
        where.append("k.account_id = ?")
        params.append(account_id)
    if active_only:
        where.append("k.is_active = 1")
    normalized_scope = ""
    if (scope or "").strip():
        normalized_scope = normalize_sora_api_key_scope(scope)
        where.append("COALESCE(k.scope, ?) = ?")
        params.extend([SORA_API_KEY_SCOPE_TEXT, normalized_scope])
    mode = (key_mode or "").strip().lower()
    if mode == "pool":
        where.append("k.account_id = 0")
    elif mode == "bound":
        where.append("k.account_id != 0")
    where_sql = " AND ".join(where) if where else "1=1"
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            f"""SELECT k.id, k.account_id, a.email, k.name, k.key_prefix, k.key_mask,
                       k.is_active, k.last_used_at, k.created_at, k.created_by,
                       COALESCE(k.scope, ?)
                FROM sora_api_keys k
                LEFT JOIN accounts a ON a.id = k.account_id
                WHERE {where_sql}
                ORDER BY k.id DESC
                LIMIT 500""",
            [SORA_API_KEY_SCOPE_TEXT] + params,
        )
        rows = c.fetchall()
    items = []
    for r in rows:
        email_display = r[2] or ""
        if r[1] == 0:
            email_display = "[自动轮换池]"
        items.append(
            {
                "id": r[0],
                "account_id": r[1],
                "email": email_display,
                "name": r[3] or "",
                "key_prefix": r[4] or "",
                "key_mask": r[5] or "",
                "is_active": bool(r[6]),
                "last_used_at": r[7] or "",
                "created_at": r[8] or "",
                "created_by": r[9] or "",
                "scope": normalize_sora_api_key_scope(r[10] or SORA_API_KEY_SCOPE_TEXT),
                "scope_label": sora_api_key_scope_label(r[10] or SORA_API_KEY_SCOPE_TEXT),
                "key_mode": "pool" if int(r[1] or 0) == 0 else "bound",
            }
        )
    return {"items": items}


@router.post("")
def create_sora_api_key(body: CreateSoraKeyBody, username: str = Depends(get_current_user)):
    account_id = int(body.account_id if body.account_id is not None else -1)
    if account_id < 0:
        raise HTTPException(status_code=400, detail="account_id 无效")
    scope = normalize_sora_api_key_scope(body.scope)

    raw_key = generate_sora_api_key()
    key_hash = hash_sora_api_key(raw_key)
    key_mask = mask_sora_api_key(raw_key)
    key_prefix = raw_key[:12]
    name = (body.name or "").strip()

    init_db()
    with get_db() as conn:
        c = conn.cursor()
        email_display = ""
        if account_id == 0:
            # 池模式：不绑定固定账号，自动轮换
            email_display = "[自动轮换池]"
        else:
            c.execute("SELECT id, email FROM accounts WHERE id = ?", (account_id,))
            account = c.fetchone()
            if not account:
                raise HTTPException(status_code=404, detail="账号不存在")
            email_display = account[1] or ""

        c.execute(
            """INSERT INTO sora_api_keys
               (account_id, name, key_hash, key_prefix, key_mask, created_by, scope, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))""",
            (account_id, name, key_hash, key_prefix, key_mask, username, scope),
        )
        key_id = c.lastrowid
        c.execute("SELECT created_at FROM sora_api_keys WHERE id = ?", (key_id,))
        created_at = (c.fetchone() or [""])[0] or ""

    return {
        "id": key_id,
        "account_id": account_id,
        "email": email_display,
        "name": name,
        "api_key": raw_key,
        "key_mask": key_mask,
        "created_at": created_at,
        "scope": scope,
        "scope_label": sora_api_key_scope_label(scope),
        "key_mode": "pool" if account_id == 0 else "bound",
    }


@router.delete("/{key_id}")
def disable_sora_api_key(key_id: int, username: str = Depends(get_current_user)):
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE sora_api_keys SET is_active = 0 WHERE id = ?", (key_id,))
        if c.rowcount <= 0:
            raise HTTPException(status_code=404, detail="API Key 不存在")
    return {"ok": True}
