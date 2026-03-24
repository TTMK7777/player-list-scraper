#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
robots_checker のテスト
======================
8件のテストケースで RobotsChecker の動作を検証する。
"""

import time
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from core.robots_checker import RobotsChecker, RobotsDisallowedError, _CACHE_TTL


@pytest.fixture
def checker():
    """テスト用 RobotsChecker インスタンス。"""
    return RobotsChecker()


def _make_robots_response(content: str) -> MagicMock:
    """robots.txt のレスポンスをモック生成する。"""
    mock_response = MagicMock()
    mock_response.read.return_value = content.encode("utf-8")
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


class TestRobotsChecker:
    """RobotsChecker のテストスイート。"""

    async def test_allowed_url_returns_true(self, checker):
        """robots.txt で Allow されたURLは True を返す。"""
        robots_txt = "User-agent: *\nAllow: /\n"
        mock_resp = _make_robots_response(robots_txt)

        with patch("core.robots_checker.urllib.request.urlopen", return_value=mock_resp):
            result = await checker.is_allowed(
                "https://example.com/page", "TestBot/1.0"
            )
        assert result is True

    async def test_disallowed_url_returns_false(self, checker):
        """Disallow されたURLは False を返す。"""
        robots_txt = "User-agent: *\nDisallow: /private/\n"
        mock_resp = _make_robots_response(robots_txt)

        with patch("core.robots_checker.urllib.request.urlopen", return_value=mock_resp):
            result = await checker.is_allowed(
                "https://example.com/private/secret", "TestBot/1.0"
            )
        assert result is False

    async def test_cache_hit(self, checker):
        """同一ドメイン2回目はキャッシュから取得（HTTP呼び出し1回のみ）。"""
        robots_txt = "User-agent: *\nAllow: /\n"
        mock_resp = _make_robots_response(robots_txt)

        with patch("core.robots_checker.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            await checker.is_allowed("https://example.com/page1", "TestBot/1.0")
            await checker.is_allowed("https://example.com/page2", "TestBot/1.0")

            # urlopen は1回のみ呼ばれるべき
            assert mock_urlopen.call_count == 1

    async def test_cache_expired(self, checker):
        """TTL 超過後は robots.txt を再取得する。"""
        robots_txt = "User-agent: *\nAllow: /\n"
        mock_resp1 = _make_robots_response(robots_txt)
        mock_resp2 = _make_robots_response(robots_txt)

        with patch("core.robots_checker.urllib.request.urlopen", side_effect=[mock_resp1, mock_resp2]) as mock_urlopen:
            # 1回目
            await checker.is_allowed("https://example.com/page1", "TestBot/1.0")
            assert mock_urlopen.call_count == 1

            # キャッシュの取得時刻を TTL 超過に設定
            domain = "example.com"
            parser, _ = checker._cache[domain]
            checker._cache[domain] = (parser, time.time() - _CACHE_TTL - 1)

            # 2回目（キャッシュ期限切れ → 再取得）
            await checker.is_allowed("https://example.com/page2", "TestBot/1.0")
            assert mock_urlopen.call_count == 2

    async def test_timeout_returns_true(self, checker):
        """タイムアウト時は全許可（True）を返す。"""
        with patch(
            "core.robots_checker.urllib.request.urlopen",
            side_effect=TimeoutError("Connection timed out"),
        ):
            result = await checker.is_allowed(
                "https://slow-site.example.com/page", "TestBot/1.0"
            )
        assert result is True

    async def test_404_returns_true(self, checker):
        """HTTP 404 エラー時は全許可（True）を返す。"""
        http_error = urllib.error.HTTPError(
            url="https://example.com/robots.txt",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=None,
        )
        with patch(
            "core.robots_checker.urllib.request.urlopen",
            side_effect=http_error,
        ):
            result = await checker.is_allowed(
                "https://example.com/page", "TestBot/1.0"
            )
        assert result is True

    async def test_connection_error_returns_true(self, checker):
        """接続エラー時は全許可（True）を返す。"""
        with patch(
            "core.robots_checker.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            result = await checker.is_allowed(
                "https://down-site.example.com/page", "TestBot/1.0"
            )
        assert result is True

    def test_robots_disallowed_error_attributes(self):
        """RobotsDisallowedError が url と domain 属性を持つことを確認。"""
        error = RobotsDisallowedError(
            url="https://example.com/private/page",
            domain="example.com",
        )
        assert error.url == "https://example.com/private/page"
        assert error.domain == "example.com"
        assert "example.com" in str(error)
        assert "/private/page" in str(error)
