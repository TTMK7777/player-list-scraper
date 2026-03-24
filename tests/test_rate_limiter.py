#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rate_limiter のテスト
====================
8件のテストケースで DomainRateLimiter の動作を検証する。
"""

import asyncio
import time

import pytest

from core.rate_limiter import DomainRateLimiter


@pytest.fixture
def limiter():
    """テスト用 DomainRateLimiter インスタンス（デフォルト0.5秒）。"""
    return DomainRateLimiter()


class TestDomainRateLimiter:
    """DomainRateLimiter のテストスイート。"""

    async def test_first_request_no_wait(self, limiter):
        """初回リクエストは待機なしで即時実行される。"""
        start = time.monotonic()
        await limiter.wait("https://example.com/page1")
        elapsed = time.monotonic() - start

        # 初回は待機なし（0.1秒未満で完了するはず）
        assert elapsed < 0.1

    async def test_same_domain_waits(self, limiter):
        """同一ドメインへの連続リクエストは min_interval 待機する。"""
        await limiter.wait("https://example.com/page1")

        start = time.monotonic()
        await limiter.wait("https://example.com/page2")
        elapsed = time.monotonic() - start

        # min_interval（0.5秒）以上待機しているはず
        assert elapsed >= 0.4  # タイマー精度のマージンを考慮

    async def test_different_domain_no_wait(self, limiter):
        """異なるドメインへのリクエストは待機不要。"""
        await limiter.wait("https://example.com/page1")

        start = time.monotonic()
        await limiter.wait("https://other-site.com/page1")
        elapsed = time.monotonic() - start

        # 異ドメインなので即時（0.1秒未満）
        assert elapsed < 0.1

    async def test_extract_domain(self):
        """URL からドメインが正しく抽出される。"""
        assert DomainRateLimiter._extract_domain("https://example.com/path") == "example.com"
        assert DomainRateLimiter._extract_domain("http://sub.example.com/path?q=1") == "sub.example.com"
        assert DomainRateLimiter._extract_domain("https://example.com") == "example.com"

    async def test_extract_domain_with_port(self):
        """ポート付きURLもドメインとして正しく処理される。"""
        assert DomainRateLimiter._extract_domain("https://example.com:8080/path") == "example.com:8080"
        assert DomainRateLimiter._extract_domain("http://localhost:3000/api") == "localhost:3000"

    async def test_custom_interval(self):
        """min_interval=1.0 でカスタム間隔が適用される。"""
        limiter = DomainRateLimiter(min_interval=1.0)

        await limiter.wait("https://example.com/page1")

        start = time.monotonic()
        await limiter.wait("https://example.com/page2")
        elapsed = time.monotonic() - start

        # 1.0秒以上待機
        assert elapsed >= 0.9  # タイマー精度のマージンを考慮

    async def test_concurrent_same_domain(self, limiter):
        """同一ドメインへの並行アクセスが直列化される。"""
        timestamps: list[float] = []

        async def make_request(url: str):
            await limiter.wait(url)
            timestamps.append(time.monotonic())

        # 同一ドメインに3つの並行リクエスト
        await asyncio.gather(
            make_request("https://example.com/a"),
            make_request("https://example.com/b"),
            make_request("https://example.com/c"),
        )

        # 3つのリクエストが直列化されているか確認
        assert len(timestamps) == 3
        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i - 1]
            # 各リクエスト間が min_interval 以上離れている
            assert interval >= 0.4  # マージン考慮

    async def test_concurrent_different_domains(self, limiter):
        """異なるドメインへのリクエストは並行処理される。"""
        timestamps: dict[str, float] = {}

        async def make_request(url: str, label: str):
            await limiter.wait(url)
            timestamps[label] = time.monotonic()

        start = time.monotonic()
        await asyncio.gather(
            make_request("https://site-a.com/page", "a"),
            make_request("https://site-b.com/page", "b"),
            make_request("https://site-c.com/page", "c"),
        )
        total_elapsed = time.monotonic() - start

        # 3つとも異ドメインなので、全体が並行処理される
        # 直列なら最低1.0秒かかるが、並行なら0.1秒未満
        assert total_elapsed < 0.3
        assert len(timestamps) == 3
