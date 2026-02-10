#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLMレスポンスキャッシュ
=======================
TTL付きインメモリキャッシュ。
属性調査・店舗調査（AIモード）など、静的情報を扱う機能で有効化。
正誤チェック・新規参入検出ではキャッシュ無効（opt-in方式）。

【使用例】
```python
cache = LLMCache(ttl_seconds=3600, max_size=500)
key = cache.make_key(prompt, model, temperature)
cached = cache.get(key)
if cached is None:
    response = llm.call(prompt)
    cache.set(key, response)
```
"""

import hashlib
import threading
import time
from typing import Optional


class LLMCache:
    """TTL付きインメモリLLMレスポンスキャッシュ（スレッドセーフ）"""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 500):
        """
        Args:
            ttl_seconds: キャッシュの有効期限（秒）。デフォルト1時間
            max_size: キャッシュの最大エントリ数
        """
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: dict[str, tuple[str, float]] = {}  # key -> (value, timestamp)
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def make_key(self, prompt: str, model: str = "", temperature: float = 0.1) -> str:
        """キャッシュキーを生成

        Args:
            prompt: プロンプト文字列
            model: モデル名
            temperature: 生成温度

        Returns:
            SHA256ハッシュのキー文字列
        """
        raw = f"{prompt}|{model}|{temperature}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        """キャッシュから取得

        Args:
            key: キャッシュキー

        Returns:
            キャッシュされたレスポンス文字列。未ヒット/期限切れはNone
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            value, timestamp = entry
            if time.time() - timestamp > self._ttl:
                # 期限切れ → 削除
                del self._store[key]
                self._misses += 1
                return None

            self._hits += 1
            return value

    def set(self, key: str, value: str) -> None:
        """キャッシュに保存

        Args:
            key: キャッシュキー
            value: レスポンス文字列
        """
        with self._lock:
            # max_size を超えたら最も古いエントリを削除
            if len(self._store) >= self._max_size and key not in self._store:
                self._evict_oldest()

            self._store[key] = (value, time.time())

    def clear(self) -> None:
        """キャッシュを全クリア"""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict:
        """キャッシュ統計を返す

        Returns:
            {"hits": int, "misses": int, "size": int, "hit_rate": float}
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "hit_rate": hit_rate,
        }

    @property
    def size(self) -> int:
        """現在のキャッシュエントリ数"""
        return len(self._store)

    def _evict_oldest(self) -> None:
        """最も古いエントリを削除"""
        if not self._store:
            return

        oldest_key = min(self._store, key=lambda k: self._store[k][1])
        del self._store[oldest_key]
