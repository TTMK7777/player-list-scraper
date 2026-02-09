#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
安全な数値変換ユーティリティ
============================
LLMレスポンスから取得した値を安全に数値に変換する。
不正な値（None、空文字列、非数値文字列）でもクラッシュしない。
"""

import logging

logger = logging.getLogger(__name__)


def safe_float(
    value,
    default: float = 0.5,
    min_val: float = 0.0,
    max_val: float = 1.0,
) -> float:
    """
    安全にfloatに変換する。

    LLMレスポンスから取得した confidence 等の値を安全に変換。
    None、空文字列、"高い"/"low" のような非数値文字列でも ValueError を投げない。

    Args:
        value: 変換対象の値（any type）
        default: 変換失敗時のデフォルト値
        min_val: 最小値（クランプ）
        max_val: 最大値（クランプ）

    Returns:
        変換後のfloat値（min_val〜max_val の範囲にクランプ）

    Examples:
        >>> safe_float(0.9)
        0.9
        >>> safe_float("0.85")
        0.85
        >>> safe_float(None)
        0.5
        >>> safe_float("高い")
        0.5
        >>> safe_float(1.5, max_val=1.0)
        1.0
        >>> safe_float(-0.1, min_val=0.0)
        0.0
    """
    if value is None:
        return default

    try:
        result = float(value)
    except (ValueError, TypeError):
        logger.debug(f"safe_float: 数値変換失敗 value={value!r}, default={default} を使用")
        return default

    # NaN/Inf チェック
    if result != result or result == float("inf") or result == float("-inf"):
        return default

    # クランプ
    return max(min_val, min(max_val, result))


def safe_int(
    value,
    default: int = 0,
    min_val: int = None,
    max_val: int = None,
) -> int:
    """
    安全にintに変換する。

    Args:
        value: 変換対象の値
        default: 変換失敗時のデフォルト値
        min_val: 最小値（Noneでクランプなし）
        max_val: 最大値（Noneでクランプなし）

    Returns:
        変換後のint値

    Examples:
        >>> safe_int(42)
        42
        >>> safe_int("100")
        100
        >>> safe_int(None)
        0
        >>> safe_int("abc")
        0
    """
    if value is None:
        return default

    try:
        result = int(float(value))  # "3.0" のような文字列にも対応
    except (ValueError, TypeError):
        logger.debug(f"safe_int: 数値変換失敗 value={value!r}, default={default} を使用")
        return default

    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)

    return result
