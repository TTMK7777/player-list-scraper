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

from core.llm_client import LLMClient, get_available_providers, get_default_client


class TestLLMClient:
    """LLMClient のテストクラス"""

    def test_init_with_perplexity(self, monkeypatch):
        """Perplexityクライアントの初期化"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

        client = LLMClient(provider="perplexity")

        assert client.provider == "perplexity"
        assert client.api_key == "test-key"

    def test_init_with_gemini(self, monkeypatch):
        """Geminiクライアントの初期化"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        client = LLMClient(provider="gemini")

        assert client.provider == "gemini"
        assert client.api_key == "test-key"

    def test_init_without_api_key(self, monkeypatch):
        """APIキーなしでの初期化エラー"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with pytest.raises(ValueError) as excinfo:
            LLMClient(provider="perplexity")

        assert "required" in str(excinfo.value).lower()

    def test_init_with_unknown_provider(self, monkeypatch):
        """不明なプロバイダーでの初期化エラー"""
        with pytest.raises(ValueError) as excinfo:
            LLMClient(provider="unknown_provider")

        assert "Unknown provider" in str(excinfo.value)

    def test_init_with_explicit_api_key(self):
        """明示的なAPIキーでの初期化"""
        client = LLMClient(api_key="explicit-key", provider="perplexity")

        assert client.api_key == "explicit-key"

    def test_extract_json_from_code_block(self, monkeypatch):
        """コードブロックからのJSON抽出"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = LLMClient(provider="perplexity")

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
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = LLMClient(provider="perplexity")

        text = 'The answer is {"status": "ok", "count": 10} as shown above.'

        result = client.extract_json(text)

        assert result == {"status": "ok", "count": 10}

    def test_extract_json_from_array(self, monkeypatch):
        """JSON配列からの抽出"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = LLMClient(provider="perplexity")

        text = 'Results: [{"id": 1}, {"id": 2}]'

        result = client.extract_json(text)

        assert result == [{"id": 1}, {"id": 2}]

    def test_extract_json_invalid(self, monkeypatch):
        """不正なJSONの処理"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = LLMClient(provider="perplexity")

        text = "This is plain text without any JSON"

        result = client.extract_json(text)

        assert result is None

    def test_extract_json_empty(self, monkeypatch):
        """空文字列の処理"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = LLMClient(provider="perplexity")

        result = client.extract_json("")

        assert result is None

    def test_extract_json_none(self, monkeypatch):
        """Noneの処理"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = LLMClient(provider="perplexity")

        result = client.extract_json(None)

        assert result is None


class TestGetAvailableProviders:
    """get_available_providers のテストクラス"""

    def test_both_providers_available(self, monkeypatch):
        """両方のプロバイダーが利用可能"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

        providers = get_available_providers()

        assert providers["perplexity"] is True
        assert providers["gemini"] is True

    def test_only_perplexity_available(self, monkeypatch):
        """Perplexityのみ利用可能"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        providers = get_available_providers()

        assert providers["perplexity"] is True
        assert providers["gemini"] is False

    def test_no_providers_available(self, monkeypatch):
        """どのプロバイダーも利用不可"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        providers = get_available_providers()

        assert providers["perplexity"] is False
        assert providers["gemini"] is False


class TestGetDefaultClient:
    """get_default_client のテストクラス"""

    def test_returns_perplexity_when_available(self, monkeypatch):
        """Perplexityが利用可能な場合はPerplexityを返す"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        client = get_default_client()

        assert client.provider == "perplexity"

    def test_returns_gemini_as_fallback(self, monkeypatch):
        """Perplexityが利用不可でGeminiが利用可能な場合はGeminiを返す"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        client = get_default_client()

        assert client.provider == "gemini"

    def test_raises_when_no_provider_available(self, monkeypatch):
        """どのプロバイダーも利用不可の場合はエラー"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(ValueError) as excinfo:
            get_default_client()

        assert "No LLM API key" in str(excinfo.value)


class TestPerplexityAPI:
    """Perplexity API呼び出しのテスト"""

    def test_call_perplexity_success(self, monkeypatch):
        """Perplexity API呼び出しの成功"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

        with patch('core.llm_client.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test response"}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            client = LLMClient(provider="perplexity")
            result = client.call("Test prompt")

            assert result == "Test response"

    def test_call_perplexity_timeout(self, monkeypatch):
        """Perplexity API タイムアウト"""
        import requests

        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

        with patch('core.llm_client.requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout()

            client = LLMClient(provider="perplexity")

            with pytest.raises(RuntimeError) as excinfo:
                client.call("Test prompt")

            assert "タイムアウト" in str(excinfo.value)

    def test_call_perplexity_auth_error(self, monkeypatch):
        """Perplexity API 認証エラー"""
        import requests

        monkeypatch.setenv("PERPLEXITY_API_KEY", "invalid-key")

        with patch('core.llm_client.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            error = requests.exceptions.HTTPError(response=mock_response)
            mock_post.side_effect = error

            client = LLMClient(provider="perplexity")

            with pytest.raises(RuntimeError) as excinfo:
                client.call("Test prompt")

            assert "認証エラー" in str(excinfo.value)
