#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ドメイン別レートリミッター
==========================
同一ドメインへのリクエスト間隔を制御し、過度なクロールを防止する。

- ドメイン単位で asyncio.Lock + 最終リクエスト時刻を管理
- デフォルト最小間隔: 0.5秒（約2リクエスト/秒）
"""

import asyncio
import time
import urllib.parse


class DomainRateLimiter:
    """ドメイン別にリクエスト間隔を制御するレートリミッター。"""

    def __init__(self, min_interval: float = 0.5) -> None:
        """
        Args:
            min_interval: 同一ドメインへの最小リクエスト間隔（秒）
        """
        self.min_interval = min_interval
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    @staticmethod
    def _extract_domain(url: str) -> str:
        """URLからドメイン（netloc）を抽出する。

        Args:
            url: 対象URL

        Returns:
            ドメイン文字列（ポート含む場合はポートも含む）
        """
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc

    def _get_lock(self, domain: str) -> asyncio.Lock:
        """ドメイン用のロックを取得（なければ作成）。"""
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    async def wait(self, url: str) -> None:
        """リクエスト前にドメイン別レート制限を適用する。

        前回リクエストから min_interval 未経過の場合、残り時間だけ待機する。
        異なるドメインへのリクエストは互いにブロックしない。

        Args:
            url: リクエスト先URL
        """
        domain = self._extract_domain(url)
        lock = self._get_lock(domain)

        async with lock:
            now = time.monotonic()
            if domain in self._last_request:
                elapsed = now - self._last_request[domain]
                if elapsed < self.min_interval:
                    await asyncio.sleep(self.min_interval - elapsed)
            self._last_request[domain] = time.monotonic()
