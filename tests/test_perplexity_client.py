#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Perplexity Client のテスト
==========================
補助検索エンジンの初期化・検索・フォールバック動作を検証。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.perplexity_client import (
    PerplexityClient,
    is_perplexity_available,
    get_perplexity_client,
    PERPLEXITY_BASE_URL,
    PERPLEXITY_DEFAULT_MODEL,
)


class TestPerplexityClient:
    """PerplexityClient のテストクラス"""

    def test_init_with_explicit_api_key(self):
        """明示的なAPIキーでの初期化"""
        client = PerplexityClient(api_key="test-perplexity-key")
        assert client.api_key == "test-perplexity-key"
        assert client.model == PERPLEXITY_DEFAULT_MODEL

    def test_init_with_env_var(self, monkeypatch):
        """環境変数からのAPIキー取得"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "env-perplexity-key")
        client = PerplexityClient()
        assert client.api_key == "env-perplexity-key"

    def test_init_without_api_key(self, monkeypatch):
        """APIキーなしでの初期化エラー"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        with pytest.raises(ValueError) as excinfo:
            PerplexityClient()
        assert "PERPLEXITY_API_KEY" in str(excinfo.value)

    def test_init_custom_model(self):
        """カスタムモデル指定"""
        client = PerplexityClient(api_key="test-key", model="sonar")
        assert client.model == "sonar"

    def test_search_success(self):
        """正常な検索"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "楽天カードは現在もサービスを継続しています。"

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            result = client.search("楽天カード 最新ニュース")

            assert "楽天カード" in result
            MockOpenAI.assert_called_once_with(
                api_key="test-key",
                base_url=PERPLEXITY_BASE_URL,
            )

    def test_search_with_system_prompt(self):
        """システムプロンプト付き検索"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "回答テスト"

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            result = client.search("テスト", system_prompt="事実のみ回答")

            assert result == "回答テスト"
            # messages にシステムプロンプトが含まれること
            call_kwargs = mock_openai.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages", []))
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"

    def test_search_api_error_returns_empty(self):
        """API エラー時は空文字列を返す（例外を投げない）"""
        client = PerplexityClient(api_key="test-key")

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.side_effect = RuntimeError("API error")
            MockOpenAI.return_value = mock_openai

            result = client.search("テスト")

            assert result == ""

    def test_search_import_error_returns_empty(self):
        """openai 未インストール時は空文字列を返す"""
        client = PerplexityClient(api_key="test-key")

        # openai モジュールを sys.modules から一時的に除去し、ImportError を発生させる
        import openai as _openai_mod
        with patch.dict("sys.modules", {"openai": None}):
            result = client.search("テスト")
            assert result == ""

    def test_search_keyboard_interrupt_propagates(self):
        """KeyboardInterrupt は捕捉されずに伝播する"""
        client = PerplexityClient(api_key="test-key")

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.side_effect = KeyboardInterrupt()
            MockOpenAI.return_value = mock_openai

            with pytest.raises(KeyboardInterrupt):
                client.search("テスト")

    def test_search_none_content_returns_empty(self):
        """API 応答の content が None の場合は空文字列"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            result = client.search("テスト")

            assert result == ""

    def test_verify_player_status(self):
        """プレイヤー検証メソッド"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "楽天カードは継続中です。"

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            result = client.verify_player_status(
                player_name="楽天カード",
                industry="クレジットカード",
                company_name="楽天カード株式会社",
            )

            assert "楽天カード" in result

    def test_verify_player_status_without_optional_args(self):
        """オプション引数なしでのプレイヤー検証"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "回答"

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            result = client.verify_player_status(player_name="テストサービス")

            assert result == "回答"

    def test_search_newcomers(self):
        """新規参入候補の補助検索"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "新規参入: TestService（2026年1月開始）"

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            result = client.search_newcomers(
                industry="動画配信",
                existing_players=["Netflix", "Hulu", "U-NEXT"],
            )

            assert "TestService" in result

    def test_search_newcomers_limits_existing_players(self):
        """既存プレイヤーリストは20件に制限される"""
        client = PerplexityClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "結果なし"

        with patch("openai.OpenAI") as MockOpenAI:
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai

            # 30件のプレイヤーを渡す
            players = [f"Player{i}" for i in range(30)]
            client.search_newcomers(industry="テスト", existing_players=players)

            # 呼び出されたクエリに含まれるプレイヤーが20件以内か検証
            call_kwargs = mock_openai.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages", []))
            query = messages[-1]["content"]
            # Player20以降は含まれないことを確認
            assert "Player20" not in query


class TestIsPerplexityAvailable:
    """is_perplexity_available のテストクラス"""

    def test_available(self, monkeypatch):
        """PERPLEXITY_API_KEY 設定済み"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        assert is_perplexity_available() is True

    def test_not_available(self, monkeypatch):
        """PERPLEXITY_API_KEY 未設定"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        assert is_perplexity_available() is False


class TestGetPerplexityClient:
    """get_perplexity_client のテストクラス"""

    def test_returns_client_when_available(self, monkeypatch):
        """APIキー設定時はクライアントを返す"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
        client = get_perplexity_client()
        assert client is not None
        assert isinstance(client, PerplexityClient)

    def test_returns_none_when_not_available(self, monkeypatch):
        """APIキー未設定時は None を返す（エラーではない）"""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        client = get_perplexity_client()
        assert client is None

    def test_returns_none_on_init_error(self, monkeypatch):
        """初期化エラー時も None を返す"""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

        with patch("core.perplexity_client.PerplexityClient", side_effect=RuntimeError("init error")):
            client = get_perplexity_client()
            assert client is None


class TestPerplexityIntegrationWithValidator:
    """PlayerValidator との統合テスト（モック使用）"""

    @pytest.mark.asyncio
    async def test_validator_uses_perplexity_on_uncertain(self, monkeypatch):
        """要確認結果の場合に Perplexity 補助検証が呼ばれる"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        from investigators.player_validator import PlayerValidator

        # Gemini が「要確認」を返すモック
        mock_llm = MagicMock()
        mock_llm.call.return_value = '```json\n{"is_active": true, "change_type": "none", "confidence": 0.3, "sources": []}\n```'
        mock_llm.extract_json.return_value = {
            "is_active": True,
            "change_type": "none",
            "confidence": 0.3,  # 低信頼度 → UNCERTAIN
            "sources": [],
        }

        # Perplexity モック
        mock_perplexity = MagicMock()
        mock_perplexity.verify_player_status.return_value = "サービスは継続中と確認できます。"

        validator = PlayerValidator(
            llm_client=mock_llm,
            perplexity_client=mock_perplexity,
        )

        result = await validator.validate_player(
            player_name="テストサービス",
            industry="テスト業界",
        )

        # Perplexity が呼ばれたことを確認
        mock_perplexity.verify_player_status.assert_called_once()
        # change_details に Perplexity の結果が含まれる
        perplexity_details = [d for d in result.change_details if "Perplexity" in d]
        assert len(perplexity_details) == 1

    @pytest.mark.asyncio
    async def test_validator_skips_perplexity_on_confirmed(self, monkeypatch):
        """確定済み結果の場合は Perplexity を呼ばない"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        from investigators.player_validator import PlayerValidator

        # Gemini が高信頼度の確認済みを返すモック
        mock_llm = MagicMock()
        mock_llm.call.return_value = "dummy"
        mock_llm.extract_json.return_value = {
            "is_active": True,
            "change_type": "none",
            "confidence": 0.95,
            "sources": ["https://example.com"],
        }

        mock_perplexity = MagicMock()

        validator = PlayerValidator(
            llm_client=mock_llm,
            perplexity_client=mock_perplexity,
        )

        await validator.validate_player(player_name="テストサービス")

        # Perplexity は呼ばれないこと
        mock_perplexity.verify_player_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_validator_works_without_perplexity(self, monkeypatch):
        """Perplexity なしでも正常動作"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from investigators.player_validator import PlayerValidator

        mock_llm = MagicMock()
        mock_llm.call.return_value = "dummy"
        mock_llm.extract_json.return_value = {
            "is_active": True,
            "change_type": "none",
            "confidence": 0.95,
            "sources": ["https://example.com"],
        }

        # perplexity_client=None を明示的に渡す
        validator = PlayerValidator(
            llm_client=mock_llm,
            perplexity_client=None,
        )

        result = await validator.validate_player(player_name="テストサービス")

        assert result.player_name_original == "テストサービス"

    @pytest.mark.asyncio
    async def test_validator_handles_perplexity_error(self, monkeypatch):
        """Perplexity エラー時もバリデーション結果は返る"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        from investigators.player_validator import PlayerValidator

        mock_llm = MagicMock()
        mock_llm.call.return_value = "dummy"
        mock_llm.extract_json.return_value = {
            "is_active": True,
            "change_type": "none",
            "confidence": 0.3,
            "sources": [],
        }

        mock_perplexity = MagicMock()
        mock_perplexity.verify_player_status.side_effect = RuntimeError("Perplexity down")

        validator = PlayerValidator(
            llm_client=mock_llm,
            perplexity_client=mock_perplexity,
        )

        result = await validator.validate_player(player_name="テストサービス")

        # エラーにならず結果が返ること
        assert result.player_name_original == "テストサービス"
        # Perplexity の結果は含まれない（エラーのため）
        perplexity_details = [d for d in result.change_details if "Perplexity" in d]
        assert len(perplexity_details) == 0


class TestPerplexityIntegrationWithNewcomerDetector:
    """NewcomerDetector との統合テスト（モック使用）"""

    @pytest.mark.asyncio
    async def test_detector_cross_validates_with_perplexity(self, monkeypatch):
        """Perplexity クロスバリデーションで確認済みフラグが付く"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        from investigators.newcomer_detector import NewcomerDetector

        # Gemini が2件の候補を返すモック
        mock_llm = MagicMock()
        mock_llm.call.return_value = '''```json
[
    {"player_name": "NewServiceA", "official_url": "", "company_name": "A社", "entry_date_approx": "2026-01", "confidence": 0.8, "source_urls": [], "reason": "新規参入"},
    {"player_name": "NewServiceB", "official_url": "", "company_name": "B社", "entry_date_approx": "2026-02", "confidence": 0.7, "source_urls": [], "reason": "新規参入"}
]
```'''
        mock_llm.extract_json.return_value = [
            {"player_name": "NewServiceA", "official_url": "", "company_name": "A社", "entry_date_approx": "2026-01", "confidence": 0.8, "source_urls": [], "reason": "新規参入"},
            {"player_name": "NewServiceB", "official_url": "", "company_name": "B社", "entry_date_approx": "2026-02", "confidence": 0.7, "source_urls": [], "reason": "新規参入"},
        ]

        # Perplexity は NewServiceA のみ言及
        mock_perplexity = MagicMock()
        mock_perplexity.search_newcomers.return_value = (
            "最近の新規参入として NewServiceA が確認されています。"
        )

        detector = NewcomerDetector(
            llm_client=mock_llm,
            perplexity_client=mock_perplexity,
        )

        candidates = await detector.detect(
            industry="テスト業界",
            existing_players=["ExistingPlayer"],
        )

        # NewServiceA は Perplexity で確認済み
        service_a = next(c for c in candidates if c.player_name == "NewServiceA")
        assert "Perplexity でも確認済み" in service_a.reason

        # NewServiceB は Perplexity で言及なし
        service_b = next(c for c in candidates if c.player_name == "NewServiceB")
        assert "Perplexity" not in service_b.reason

    @pytest.mark.asyncio
    async def test_detector_works_without_perplexity(self, monkeypatch):
        """Perplexity なしでも正常動作"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from investigators.newcomer_detector import NewcomerDetector

        mock_llm = MagicMock()
        mock_llm.call.return_value = "[]"
        mock_llm.extract_json.return_value = []

        detector = NewcomerDetector(
            llm_client=mock_llm,
            perplexity_client=None,
        )

        candidates = await detector.detect(
            industry="テスト業界",
            existing_players=["ExistingPlayer"],
        )

        assert isinstance(candidates, list)
