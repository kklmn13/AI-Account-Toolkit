"""
注册 OTP：通过 Hotmail007 拉信，从邮件正文/标题解析 6 位验证码。
与参考 chatgpt_register.py 对齐：多模式优先匹配（code:、verify、>xxx<、纯 6 位），只返回 6 位数字。
"""
import re
import time
from typing import Callable, Optional

from app.services.hotmail007 import get_first_mail

# 与参考一致：优先匹配 OpenAI 邮件里常见格式，再回退到任意 6 位
_OTP_PATTERNS = [
    r">\s*(\d{6})\s*<",       # HTML 中 >123456<
    r"(\d{6})\s*\n",          # 行末 6 位
    r"code[:\s]+(\d{6})",     # code: 123456 / code 123456
    r"verify.*?(\d{6})",      # verify...123456
    r"\b(\d{6})\b",           # 独立 6 位数字
    r"(\d{6})",               # 任意 6 位（最后回退）
]


def _extract_otp_from_mail(data: Optional[dict]) -> Optional[str]:
    """从 get_first_mail 返回的 data 中解析 6 位验证码，与参考提取顺序一致。"""
    if not data or not isinstance(data, dict):
        return None
    texts = []
    for key in ("Subject", "subject", "Text", "text", "Body", "body", "Html", "html", "Content", "content"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            texts.append(v)
    combined = " ".join(texts)
    for pattern in _OTP_PATTERNS:
        m = re.search(pattern, combined, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1)
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 6:
                return digits[:6]
    return None


def get_otp_for_email(
    base_url: str,
    client_key: str,
    account_str: str,
    timeout_sec: float = 120,
    interval_sec: float = 5,
    folder: str = "inbox",
    folders=None,
    exclude_codes=None,
    stop_check=None,
) -> Optional[str]:
    """
    轮询该邮箱最新一封邮件，解析 6 位验证码，超时返回 None。
    stop_check: 可调用对象，返回 True 时立即结束并返回 None。
    """
    if not client_key or not account_str:
        return None
    excluded = set(exclude_codes or [])
    folder_list = [f for f in (folders or [folder]) if isinstance(f, str) and f.strip()]
    if not folder_list:
        folder_list = ["inbox"]
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if stop_check and callable(stop_check) and stop_check():
            return None
        for current_folder in folder_list:
            data = get_first_mail(base_url, client_key, account_str, folder=current_folder)
            otp = _extract_otp_from_mail(data)
            if otp and otp not in excluded:
                return otp
        for _ in range(int(interval_sec)):
            if stop_check and callable(stop_check) and stop_check():
                return None
            time.sleep(1)
    return None


def peek_latest_otps(
    base_url: str,
    client_key: str,
    account_str: str,
    folder: str = "inbox",
    folders=None,
) -> set[str]:
    """
    读取指定文件夹当前“最新一封”邮件里的验证码，用于在发起新 OTP 前先排除旧码。
    """
    if not client_key or not account_str:
        return set()
    folder_list = [f for f in (folders or [folder]) if isinstance(f, str) and f.strip()]
    if not folder_list:
        folder_list = ["inbox"]
    out: set[str] = set()
    for current_folder in folder_list:
        data = get_first_mail(base_url, client_key, account_str, folder=current_folder)
        otp = _extract_otp_from_mail(data)
        if otp:
            out.add(otp)
    return out


def build_otp_fetcher(
    base_url: str,
    client_key: str,
    account_str: str,
    timeout_sec: float = 120,
    interval_sec: float = 5,
    stop_check=None,
) -> Callable[[], Optional[str]]:
    """
    构造带状态的 OTP 获取器。
    - 自动排除已使用过的验证码
    - 可在登录二次验证前预先排除收件箱/垃圾箱当前顶上的旧验证码
    """
    used_otps: set[str] = set()

    def seed_current_otps(folder: str = "inbox", folders=None) -> set[str]:
        current = peek_latest_otps(
            base_url,
            client_key,
            account_str,
            folder=folder,
            folders=folders,
        )
        used_otps.update(current)
        return set(current)

    def get_used_otps() -> set[str]:
        return set(used_otps)

    def get_otp_fn() -> Optional[str]:
        search_folders = ["inbox"] if not used_otps else ["junkemail", "inbox"]
        otp = get_otp_for_email(
            base_url,
            client_key,
            account_str,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            folders=search_folders,
            exclude_codes=used_otps,
            stop_check=stop_check,
        )
        # 首次取码可兜底一次；后续步骤必须拿“新码”，避免复用旧码导致 401。
        if not otp and not used_otps:
            otp = get_otp_for_email(
                base_url,
                client_key,
                account_str,
                timeout_sec=20,
                interval_sec=3,
                folders=["inbox", "junkemail"],
                stop_check=stop_check,
            )
        if otp:
            used_otps.add(otp)
        return otp

    setattr(get_otp_fn, "seed_current_otps", seed_current_otps)
    setattr(get_otp_fn, "get_used_otps", get_used_otps)
    return get_otp_fn
