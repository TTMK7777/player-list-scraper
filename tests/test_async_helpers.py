#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
core/async_helpers.py のテスト
"""

import asyncio
import pytest
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.async_helpers import run_async, _run_in_new_loop, optimal_concurrency


class TestRunAsync:
    """run_async() のテスト"""

    def test_run_async_no_existing_loop(self):
        """イベントループがない環境で正常動作"""
        async def simple_coro():
            return 42

        result = run_async(simple_coro())
        assert result == 42

    def test_run_async_with_existing_loop(self):
        """既存のイベントループが走っている環境で正常動作"""
        async def inner():
            return "from_inner"

        async def outer():
            # outer は既にループ上で走っている
            # → run_async(inner()) は ThreadPoolExecutor 経由になる
            result = run_async(inner())
            return result

        result = asyncio.run(outer())
        assert result == "from_inner"

    def test_run_async_with_async_sleep(self):
        """非同期 sleep を含むコルーチンが正常動作"""
        async def slow_coro():
            await asyncio.sleep(0.01)
            return "done"

        result = run_async(slow_coro())
        assert result == "done"

    def test_run_async_propagates_exception(self):
        """コルーチン内の例外が正しく伝播する"""
        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing_coro())


class TestOptimalConcurrency:
    """optimal_concurrency() のテスト"""

    def test_zero_total(self):
        """total=0 のとき1を返す"""
        assert optimal_concurrency(0) == 1

    def test_negative_total(self):
        """negative total のとき1を返す"""
        assert optimal_concurrency(-5) == 1

    def test_single_item(self):
        """total=1 のとき1を返す"""
        assert optimal_concurrency(1) == 1

    def test_small_total(self):
        """total<=5 のとき min(total, 5) を返す"""
        assert optimal_concurrency(3) == 3
        assert optimal_concurrency(5) == 5

    def test_medium_total(self):
        """total 6-20 のとき3を返す"""
        assert optimal_concurrency(6) == 3
        assert optimal_concurrency(10) == 3
        assert optimal_concurrency(20) == 3

    def test_large_total(self):
        """total 21-100 のとき2を返す"""
        assert optimal_concurrency(21) == 2
        assert optimal_concurrency(50) == 2
        assert optimal_concurrency(100) == 2

    def test_very_large_total(self):
        """total>100 のとき1を返す"""
        assert optimal_concurrency(101) == 1
        assert optimal_concurrency(500) == 1


class TestRunInNewLoop:
    """_run_in_new_loop() のテスト"""

    def test_run_in_new_loop_basic(self):
        """新規ループでの基本実行"""
        async def coro():
            return "hello"

        result = _run_in_new_loop(coro())
        assert result == "hello"
