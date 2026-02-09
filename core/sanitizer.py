#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
共通入力サニタイザー
====================
プロンプトインジェクション対策の共通ユーティリティ。
player_validator.py / store_investigator.py / 新機能で共通使用。
"""

import re
from urllib.parse import urlparse


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


def sanitize_url(url: str) -> str:
    """
    URL専用サニタイザー

    【処理内容】
    1. 空白・改行の除去
    2. スキーム検証（http/https のみ許可）
    3. 危険な文字列の除去
    4. 長さ制限（2000文字）

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
        # スキームがない場合は https を付与
        if not parsed.scheme and parsed.netloc:
            sanitized = f"https://{sanitized}"
        elif not parsed.scheme and not parsed.netloc:
            # "example.com/path" のようなケース
            if "." in sanitized.split("/")[0]:
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
