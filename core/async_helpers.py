#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Async安全ランナー
=================
Streamlit / Playwright 環境で既存のイベントループと競合しないように
安全にコルーチンを実行するユーティリティ。

【問題】
asyncio.run() は「既にイベントループが走っている環境」で RuntimeError を投げる。
Streamlit は内部で独自の非同期ループを使用しており、Playwright も同様。

【解決策】
1. まず asyncio.get_running_loop() で既存ループの有無を確認
2. 既存ループがあれば ThreadPoolExecutor 経由で新スレッドで実行
3. なければ通常の asyncio.run() を使用

nest_asyncio に依存せず、スレッド分離で安全性を担保する。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def optimal_concurrency(total: int) -> int:
    """プレイヤー数に応じた最適並列数を返す

    Args:
        total: 処理対象の総数

    Returns:
        推奨同時実行数
    """
    if total <= 0:
        return 1
    elif total <= 5:
        return total           # 少数: 全並列OK
    elif total <= 20:
        return 3               # 中規模: 標準
    elif total <= 100:
        return 2               # 大規模: レート制限考慮
    else:
        return 1               # 超大規模: 安全優先


# 共有のスレッドプールエグゼキュータ（デーモンスレッド）
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="async_runner")


def _run_in_new_loop(coro):
    """新しいイベントループを作成してコルーチンを実行（サブスレッド用）"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def run_async(coro) -> T:
    """
    安全にコルーチンを実行する。

    - 既存のイベントループが走っている場合: ThreadPoolExecutor で新スレッドに委譲
    - イベントループがない場合: asyncio.run() を直接使用

    Args:
        coro: 実行するコルーチン

    Returns:
        コルーチンの戻り値

    Examples:
        >>> async def fetch_data():
        ...     return {"status": "ok"}
        >>> result = run_async(fetch_data())
        >>> result
        {'status': 'ok'}
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # イベントループが走っていない → 通常の asyncio.run()
        return asyncio.run(coro)

    # 既にイベントループが走っている → サブスレッドで実行
    future = _executor.submit(_run_in_new_loop, coro)
    return future.result()
