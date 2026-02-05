#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PlayerValidator のテスト
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from investigators.player_validator import PlayerValidator
from investigators.base import AlertLevel, ChangeType, ValidationStatus


class TestPlayerValidator:
    """PlayerValidator のテストクラス"""

    @pytest.mark.asyncio
    async def test_validate_player_unchanged(self, mock_llm_client):
        """変更なしのプレイヤー検証"""
        validator = PlayerValidator(llm_client=mock_llm_client)

        result = await validator.validate_player(
            player_name="楽天カード",
            official_url="https://www.rakuten-card.co.jp/",
            company_name="楽天カード株式会社",
            industry="クレジットカード",
        )

        assert result.alert_level == AlertLevel.OK
        assert result.change_type == ChangeType.NO_CHANGE
        assert result.confidence >= 0.9
        assert not result.needs_manual_review

    @pytest.mark.asyncio
    async def test_validate_player_withdrawal(self, mock_llm_client_withdrawal):
        """撤退したプレイヤーの検証"""
        validator = PlayerValidator(llm_client=mock_llm_client_withdrawal)

        result = await validator.validate_player(
            player_name="終了したサービス",
            official_url="https://example.com/",
            company_name="株式会社〇〇",
            industry="テスト",
        )

        assert result.alert_level == AlertLevel.CRITICAL
        assert result.change_type == ChangeType.WITHDRAWAL
        assert not result.status == ValidationStatus.UNCHANGED

    @pytest.mark.asyncio
    async def test_validate_player_with_api_error(self):
        """APIエラー時の処理"""
        mock_llm = MagicMock()
        mock_llm.call.side_effect = RuntimeError("API connection failed")

        validator = PlayerValidator(llm_client=mock_llm)

        result = await validator.validate_player(
            player_name="テストサービス",
            official_url="https://example.com/",
        )

        assert result.status == ValidationStatus.ERROR
        assert result.needs_manual_review
        assert "API connection failed" in str(result.change_details)

    @pytest.mark.asyncio
    async def test_validate_player_low_confidence(self):
        """信頼度が低い場合の処理"""
        mock_llm = MagicMock()
        mock_llm.call.return_value = "test response"
        mock_llm.extract_json.return_value = {
            "is_active": True,
            "change_type": "none",
            "current_service_name": "テストサービス",
            "current_company_name": "テスト株式会社",
            "current_url": "https://example.com/",
            "changes": [],
            "news": "",
            "confidence": 0.3,  # 低い信頼度
            "sources": []
        }

        validator = PlayerValidator(llm_client=mock_llm)

        result = await validator.validate_player(
            player_name="テストサービス",
            official_url="https://example.com/",
        )

        assert result.needs_manual_review
        assert result.confidence < validator.CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_validate_batch(self, mock_llm_client, sample_player_data):
        """バッチ検証のテスト"""
        validator = PlayerValidator(llm_client=mock_llm_client)

        progress_calls = []

        def on_progress(current, total, name):
            progress_calls.append((current, total, name))

        results = await validator.validate_batch(
            sample_player_data,
            industry="クレジットカード",
            on_progress=on_progress,
            concurrency=2,
            delay_seconds=0.1,  # テスト用に短縮
        )

        assert len(results) == len(sample_player_data)
        assert len(progress_calls) == len(sample_player_data)

    @pytest.mark.asyncio
    async def test_check_url_status_success(self):
        """URL確認の成功ケース"""
        validator = PlayerValidator(llm_client=MagicMock())

        with patch('investigators.player_validator.requests.head') as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "https://example.com/"
            mock_response.history = []
            mock_head.return_value = mock_response

            result = await validator._check_url_status("https://example.com/")

            assert result["status_code"] == 200
            assert not result["is_redirect"]

    @pytest.mark.asyncio
    async def test_check_url_status_redirect(self):
        """リダイレクトの検出"""
        validator = PlayerValidator(llm_client=MagicMock())

        with patch('investigators.player_validator.requests.head') as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "https://new-example.com/"
            mock_response.history = [MagicMock()]  # リダイレクト履歴あり
            mock_head.return_value = mock_response

            result = await validator._check_url_status("https://old-example.com/")

            assert result["is_redirect"]
            assert result["final_url"] == "https://new-example.com/"

    @pytest.mark.asyncio
    async def test_check_url_status_timeout(self):
        """タイムアウト時の処理"""
        import requests

        validator = PlayerValidator(llm_client=MagicMock())

        with patch('investigators.player_validator.requests.head') as mock_head:
            mock_head.side_effect = requests.exceptions.Timeout()

            result = await validator._check_url_status("https://slow-example.com/")

            assert result["status_code"] == 0
            assert result.get("error") == "timeout"


class TestParseResponse:
    """_parse_response メソッドのテスト"""

    def test_parse_valid_response(self, mock_llm_client):
        """正常なレスポンスの解析"""
        validator = PlayerValidator(llm_client=mock_llm_client)

        result = validator._parse_response(
            response="test response",
            player_name="テストサービス",
            original_url="https://example.com/",
            original_company="テスト株式会社",
            url_status=None,
        )

        assert result.player_name_original == "テストサービス"
        assert result.alert_level == AlertLevel.OK

    def test_parse_invalid_json_response(self):
        """不正なJSONレスポンスの処理"""
        mock_llm = MagicMock()
        mock_llm.extract_json.return_value = None

        validator = PlayerValidator(llm_client=mock_llm)

        result = validator._parse_response(
            response="invalid response",
            player_name="テストサービス",
            original_url="https://example.com/",
            original_company="テスト株式会社",
            url_status=None,
        )

        assert result.status == ValidationStatus.UNCERTAIN
        assert result.needs_manual_review


class TestSanitizeInput:
    """_sanitize_input メソッドのテスト（プロンプトインジェクション対策）"""

    def test_sanitize_normal_input(self):
        """正常な入力はそのまま返す"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("楽天カード")

        assert result == "楽天カード"

    def test_sanitize_newline_characters(self):
        """改行文字を空白に置換"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("テスト\n改行\rキャリッジ\tタブ")

        assert "\n" not in result
        assert "\r" not in result
        assert "\t" not in result
        assert "テスト 改行 キャリッジ タブ" == result

    def test_sanitize_multiple_spaces(self):
        """連続する空白を1つに圧縮"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("テスト    複数    空白")

        assert "    " not in result
        assert "テスト 複数 空白" == result

    def test_sanitize_code_block(self):
        """コードブロック記法をエスケープ"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("```json{\"hack\": true}```")

        assert "```" not in result
        assert "`‵`" in result

    def test_sanitize_brackets(self):
        """プロンプト区切り文字をエスケープ"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("【攻撃】テスト")

        assert "【" not in result
        assert "】" not in result
        assert "[攻撃]テスト" == result

    def test_sanitize_length_limit(self):
        """500文字を超える入力を切り詰め"""
        validator = PlayerValidator(llm_client=MagicMock())

        long_input = "A" * 600
        result = validator._sanitize_input(long_input)

        assert len(result) == 500

    def test_sanitize_empty_string(self):
        """空文字列の処理"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("")

        assert result == ""

    def test_sanitize_whitespace_only(self):
        """空白のみの入力"""
        validator = PlayerValidator(llm_client=MagicMock())

        result = validator._sanitize_input("   \n\t   ")

        assert result == ""
