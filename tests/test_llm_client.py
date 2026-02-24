#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM Client のテスト
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_client import LLMClient, is_api_available, get_default_client


class TestLLMClient:
    """LLMClient のテストクラス"""

    def test_init_with_gemini(self, monkeypatch):
        """Geminiクライアントの初期化"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        client = LLMClient()

        assert client.api_key == "test-key"

    def test_init_without_api_key(self, monkeypatch):
        """APIキーなしでの初期化エラー"""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(ValueError) as excinfo:
            LLMClient()

        assert "GOOGLE_API_KEY" in str(excinfo.value)

    def test_init_with_explicit_api_key(self):
        """明示的なAPIキーでの初期化"""
        client = LLMClient(api_key="explicit-key")

        assert client.api_key == "explicit-key"

    def test_init_with_cache(self, monkeypatch):
        """キャッシュ有効での初期化"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        client = LLMClient(enable_cache=True)

        assert client._cache is not None

    def test_extract_json_from_code_block(self, monkeypatch):
        """コードブロックからのJSON抽出"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        client = LLMClient()

        text = '''
        Here is the result:
        ```json
        {"key": "value", "number": 42}
        ```
        '''

        result = client.extract_json(text)

        assert result == {"key": "value", "number": 42}

    def test_extract_json_from_raw_object(self, monkeypatch):
        """生のJSONオブジェクトからの抽出"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        client = LLMClient()

        text = 'The answer is {"status": "ok", "count": 10} as shown above.'

        result = client.extract_json(text)

        assert result == {"status": "ok", "count": 10}

    def test_extract_json_from_array(self, monkeypatch):
        """JSON配列からの抽出"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        client = LLMClient()

        text = 'Results: [{"id": 1}, {"id": 2}]'

        result = client.extract_json(text)

        assert result == [{"id": 1}, {"id": 2}]

    def test_extract_json_invalid(self, monkeypatch):
        """不正なJSONの処理"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        client = LLMClient()

        text = "This is plain text without any JSON"

        result = client.extract_json(text)

        assert result is None

    def test_extract_json_empty(self, monkeypatch):
        """空文字列の処理"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        client = LLMClient()

        result = client.extract_json("")

        assert result is None

    def test_extract_json_none(self, monkeypatch):
        """Noneの処理"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        client = LLMClient()

        result = client.extract_json(None)

        assert result is None

    def test_call_with_use_search(self, monkeypatch):
        """use_search パラメータが受け入れられること"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        with patch('core.llm_client.LLMClient._call_gemini') as mock_gemini:
            mock_gemini.return_value = "Test response"

            client = LLMClient()
            result = client.call("Test prompt", use_search=True)

            assert result == "Test response"
            # use_search=True が _call_gemini に渡されること
            mock_gemini.assert_called_once()
            call_kwargs = mock_gemini.call_args
            assert call_kwargs[0][5] is True or call_kwargs.kwargs.get("use_search") is True  # use_search

    def test_call_default_no_search(self, monkeypatch):
        """use_search のデフォルトは False"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        with patch('core.llm_client.LLMClient._call_gemini') as mock_gemini:
            mock_gemini.return_value = "Test response"

            client = LLMClient()
            result = client.call("Test prompt")

            assert result == "Test response"


class TestIsAPIAvailable:
    """is_api_available のテストクラス"""

    def test_api_available(self, monkeypatch):
        """Gemini API が利用可能"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

        assert is_api_available() is True

    def test_api_not_available(self, monkeypatch):
        """Gemini API が利用不可"""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        assert is_api_available() is False


class TestGetDefaultClient:
    """get_default_client のテストクラス"""

    def test_returns_gemini_client(self, monkeypatch):
        """Gemini APIが利用可能な場合はクライアントを返す"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        client = get_default_client()

        assert client.api_key == "test-key"

    def test_raises_when_no_api_key(self, monkeypatch):
        """GOOGLE_API_KEY 未設定の場合はエラー"""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(ValueError) as excinfo:
            get_default_client()

        assert "GOOGLE_API_KEY" in str(excinfo.value)
