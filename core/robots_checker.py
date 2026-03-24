#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
robots.txt チェッカー
=====================
urllib.robotparser ベースで robots.txt を取得・キャッシュし、
指定URLへのアクセス可否を判定する。

- ドメイン単位キャッシュ（TTL 1時間）
- asyncio.to_thread() で非同期ラップ
- タイムアウト5秒
- HTTP 404 / 接続エラー → 全許可（True）
"""

import asyncio
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Optional


# キャッシュTTL（秒）
_CACHE_TTL = 3600  # 1時間

# robots.txt 取得タイムアウト（秒）
_FETCH_TIMEOUT = 5


class RobotsDisallowedError(Exception):
    """robots.txt により拒否されたURLへのアクセスを示す例外。"""

    def __init__(self, url: str, domain: str, message: Optional[str] = None):
        self.url = url
        self.domain = domain
        if message is None:
            message = f"Access disallowed by robots.txt: {url} (domain: {domain})"
        super().__init__(message)


class RobotsChecker:
    """robots.txt を取得・キャッシュし、URLごとのアクセス可否を判定する。"""

    def __init__(self) -> None:
        # ドメイン → (RobotFileParser, 取得時刻) のキャッシュ
        self._cache: dict[str, tuple[urllib.robotparser.RobotFileParser, float]] = {}

    def _extract_domain(self, url: str) -> str:
        """URLからドメイン（netloc）を抽出する。"""
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc

    def _get_robots_url(self, url: str) -> str:
        """URLから robots.txt の完全URLを構築する。"""
        parsed = urllib.parse.urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _get_parser(self, domain: str, robots_url: str) -> urllib.robotparser.RobotFileParser:
        """キャッシュからパーサーを取得、期限切れ or 未取得なら新規取得する。

        同期メソッド（asyncio.to_thread 内から呼ばれる想定）。
        """
        now = time.time()

        # キャッシュヒット & TTL内
        if domain in self._cache:
            parser, fetched_at = self._cache[domain]
            if now - fetched_at < _CACHE_TTL:
                return parser

        # 新規取得
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)

        try:
            # タイムアウト付きで robots.txt を取得
            with urllib.request.urlopen(robots_url, timeout=_FETCH_TIMEOUT) as response:
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                parser.parse(text.splitlines())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # robots.txt が存在しない → 全許可パーサーを返す
                parser.parse([])
            else:
                # その他のHTTPエラー → 全許可
                parser.parse([])
        except (urllib.error.URLError, OSError, TimeoutError):
            # 接続エラー / タイムアウト → 全許可
            parser.parse([])

        self._cache[domain] = (parser, now)
        return parser

    def _check_sync(self, url: str, user_agent: str) -> bool:
        """同期版のアクセス可否チェック。"""
        domain = self._extract_domain(url)
        robots_url = self._get_robots_url(url)

        try:
            parser = self._get_parser(domain, robots_url)
            return parser.can_fetch(user_agent, url)
        except Exception:
            # 予期しない例外 → 安全側（全許可）
            return True

    async def is_allowed(self, url: str, user_agent: str) -> bool:
        """指定URLへのアクセスが robots.txt で許可されているか判定する。

        Args:
            url: チェック対象のURL
            user_agent: リクエストに使用するUser-Agent文字列

        Returns:
            True: アクセス許可（またはエラー時の全許可）
            False: robots.txt により拒否
        """
        return await asyncio.to_thread(self._check_sync, url, user_agent)
