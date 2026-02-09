#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
共通入力サニタイザー
====================
プロンプトインジェクション対策の共通ユーティリティ。
player_validator.py / store_investigator.py / 新機能で共通使用。
"""

import asyncio
import re
from urllib.parse import urlparse

import requests


# プロンプトインジェクション検出パターン
DANGEROUS_PATTERNS = [
    r"ignore.*instructions?",
    r"forget.*instructions?",
    r"system.*prompt",
    r"<\|.*\|>",
    r"\{\{.*\}\}",
    r"```.*system",
]


def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    プロンプトインジェクション対策の共通サニタイザー

    【処理内容】
    1. 危険パターンの検出・除去
    2. 改行・タブの正規化
    3. プロンプト区切り文字のエスケープ
    4. 長さ制限

    Args:
        text: サニタイズ対象のテキスト
        max_length: 最大文字数（デフォルト500）

    Returns:
        サニタイズされたテキスト
    """
    if not text:
        return ""

    sanitized = text.strip()

    # 危険なパターンを検出・除去
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, sanitized, re.IGNORECASE):
            sanitized = re.sub(pattern, "[REMOVED]", sanitized, flags=re.IGNORECASE)

    # 改行・タブを空白に置換
    sanitized = sanitized.replace('\r\n', '\n')
    sanitized = sanitized.replace('\r', ' ')
    sanitized = sanitized.replace('\t', ' ')

    # 連続する改行を最大2つに制限
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

    # 連続する空白を1つに
    sanitized = re.sub(r'[ ]{2,}', ' ', sanitized)

    # プロンプト区切り文字をエスケープ
    sanitized = sanitized.replace('```', '`‵`')
    sanitized = sanitized.replace('【', '[').replace('】', ']')

    # 長さ制限
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized.strip()


# ファイル拡張子のブロックリスト（URLではなくファイル名と判定）
_FILE_EXTENSION_BLOCKLIST = {
    "txt", "pdf", "xlsx", "xls", "csv", "doc", "docx",
    "ppt", "pptx", "zip", "rar", "7z", "tar", "gz",
    "png", "jpg", "jpeg", "gif", "bmp", "svg",
    "mp3", "mp4", "avi", "mov", "wmv",
    "py", "js", "ts", "java", "c", "cpp", "h", "rb", "go", "rs",
    "json", "yaml", "yml", "xml", "toml", "ini", "cfg", "conf",
    "log", "md", "rst",
}


def sanitize_url(url: str) -> str:
    """
    URL専用サニタイザー

    【処理内容】
    1. 空白・改行の除去
    2. ファイル拡張子チェック（"test.txt" → URL化しない）
    3. スキーム検証（http/https のみ許可）
    4. 危険な文字列の除去
    5. 長さ制限（2000文字）

    Args:
        url: サニタイズ対象のURL

    Returns:
        サニタイズされたURL。無効な場合は空文字列
    """
    if not url:
        return ""

    # 空白・改行を除去
    sanitized = url.strip().replace('\n', '').replace('\r', '').replace('\t', '')

    # スキーム検証
    try:
        parsed = urlparse(sanitized)
        if parsed.scheme not in ("http", "https", ""):
            return ""
        # スキームがない場合
        if not parsed.scheme and parsed.netloc:
            sanitized = f"https://{sanitized}"
        elif not parsed.scheme and not parsed.netloc:
            # "example.com/path" のようなケース
            host_part = sanitized.split("/")[0]
            if "." in host_part:
                # ファイル拡張子ブロックリストをチェック
                # "test.txt" → URLではなくファイル名
                ext = host_part.rsplit(".", 1)[-1].lower() if "." in host_part else ""
                if ext in _FILE_EXTENSION_BLOCKLIST:
                    return ""
                sanitized = f"https://{sanitized}"
            else:
                return ""
    except Exception:
        return ""

    # JavaScript/data スキームの除去
    lower_url = sanitized.lower()
    if any(scheme in lower_url for scheme in ["javascript:", "data:", "vbscript:"]):
        return ""

    # 長さ制限
    if len(sanitized) > 2000:
        return ""

    return sanitized


async def verify_url(url: str) -> dict:
    """
    URLの有効性をチェック（共通ユーティリティ）

    newcomer_detector._verify_url() と player_validator._check_url_status() を統合。

    Args:
        url: チェック対象のURL

    Returns:
        dict: {
            "status_code": int,
            "final_url": str,
            "is_redirect": bool,
            "error": str (optional)
        }
    """
    if not url:
        return {"status_code": 0, "error": "empty_url"}

    try:
        response = await asyncio.to_thread(
            requests.head,
            url,
            timeout=10,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        return {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "is_redirect": len(response.history) > 0,
        }
    except requests.exceptions.Timeout:
        return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "timeout"}
    except requests.exceptions.SSLError:
        return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "ssl_error"}
    except requests.exceptions.ConnectionError:
        return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "connection_error"}
    except requests.exceptions.RequestException:
        return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "request_error"}
