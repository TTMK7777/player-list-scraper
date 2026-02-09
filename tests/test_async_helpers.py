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

from core.async_helpers import run_async, _run_in_new_loop


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


class TestRunInNewLoop:
    """_run_in_new_loop() のテスト"""

    def test_run_in_new_loop_basic(self):
        """新規ループでの基本実行"""
        async def coro():
            return "hello"

        result = _run_in_new_loop(coro())
        assert result == "hello"
