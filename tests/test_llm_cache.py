#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
core/llm_cache.py のテスト
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_cache import LLMCache


class TestLLMCacheBasic:
    """LLMCache の基本操作テスト"""

    def test_set_and_get(self):
        """set した値が get で取得できる"""
        cache = LLMCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent(self):
        """存在しないキーは None を返す"""
        cache = LLMCache()
        assert cache.get("nonexistent") is None

    def test_overwrite(self):
        """同一キーに set すると上書きされる"""
        cache = LLMCache()
        cache.set("key1", "old_value")
        cache.set("key1", "new_value")
        assert cache.get("key1") == "new_value"

    def test_clear(self):
        """clear でキャッシュが空になる"""
        cache = LLMCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.size == 0

    def test_size(self):
        """size が正しいエントリ数を返す"""
        cache = LLMCache()
        assert cache.size == 0
        cache.set("key1", "value1")
        assert cache.size == 1
        cache.set("key2", "value2")
        assert cache.size == 2


class TestLLMCacheTTL:
    """TTL（有効期限）のテスト"""

    def test_ttl_not_expired(self):
        """TTL内の値は取得できる"""
        cache = LLMCache(ttl_seconds=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_ttl_expired(self):
        """TTLを超えた値は None を返す"""
        cache = LLMCache(ttl_seconds=1)
        cache.set("key1", "value1")

        # time.time() をモックして期限切れをシミュレート
        original_time = time.time
        with patch("core.llm_cache.time") as mock_time:
            mock_time.time.return_value = original_time() + 2  # 2秒後
            result = cache.get("key1")
        assert result is None

    def test_ttl_expired_entry_removed(self):
        """期限切れエントリは自動削除される"""
        cache = LLMCache(ttl_seconds=1)
        cache.set("key1", "value1")

        original_time = time.time
        with patch("core.llm_cache.time") as mock_time:
            mock_time.time.return_value = original_time() + 2
            cache.get("key1")  # 期限切れ → 削除
        assert cache.size == 0


class TestLLMCacheMaxSize:
    """max_size（最大エントリ数）のテスト"""

    def test_max_size_eviction(self):
        """max_size を超えると最も古いエントリが削除される"""
        cache = LLMCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # 4つ目を追加 → key1 が削除される
        cache.set("key4", "value4")

        assert cache.size == 3
        assert cache.get("key1") is None  # 削除された
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_max_size_overwrite_no_eviction(self):
        """同一キーの上書きでは max_size を超えない"""
        cache = LLMCache(max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key1", "new_value1")  # 上書き（新規追加ではない）

        assert cache.size == 2
        assert cache.get("key1") == "new_value1"
        assert cache.get("key2") == "value2"


class TestLLMCacheMakeKey:
    """make_key() のテスト"""

    def test_same_input_same_key(self):
        """同じ入力は同じキーを生成する"""
        cache = LLMCache()
        key1 = cache.make_key("hello", "model1", 0.1)
        key2 = cache.make_key("hello", "model1", 0.1)
        assert key1 == key2

    def test_different_prompt_different_key(self):
        """異なるプロンプトは異なるキーを生成する"""
        cache = LLMCache()
        key1 = cache.make_key("hello", "model1", 0.1)
        key2 = cache.make_key("world", "model1", 0.1)
        assert key1 != key2

    def test_different_model_different_key(self):
        """異なるモデルは異なるキーを生成する"""
        cache = LLMCache()
        key1 = cache.make_key("hello", "model1", 0.1)
        key2 = cache.make_key("hello", "model2", 0.1)
        assert key1 != key2

    def test_different_temperature_different_key(self):
        """異なるtemperatureは異なるキーを生成する"""
        cache = LLMCache()
        key1 = cache.make_key("hello", "model1", 0.1)
        key2 = cache.make_key("hello", "model1", 0.5)
        assert key1 != key2

    def test_key_is_hex_string(self):
        """キーはSHA256の16進文字列"""
        cache = LLMCache()
        key = cache.make_key("test", "model", 0.1)
        assert len(key) == 64  # SHA256は32バイト = 64文字の16進
        assert all(c in "0123456789abcdef" for c in key)


class TestLLMCacheStats:
    """stats プロパティのテスト"""

    def test_initial_stats(self):
        """初期状態の統計"""
        cache = LLMCache()
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate"] == 0.0

    def test_hit_miss_tracking(self):
        """ヒットとミスが正しくカウントされる"""
        cache = LLMCache()
        cache.set("key1", "value1")

        cache.get("key1")      # hit
        cache.get("key1")      # hit
        cache.get("missing")   # miss

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert abs(stats["hit_rate"] - 2/3) < 0.01

    def test_clear_resets_stats(self):
        """clear で統計もリセットされる"""
        cache = LLMCache()
        cache.set("key1", "value1")
        cache.get("key1")
        cache.clear()

        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
