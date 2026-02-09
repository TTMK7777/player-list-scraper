#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新規参入プレイヤー検出 (NewcomerDetector) のテスト
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from investigators.newcomer_detector import NewcomerDetector
from investigators.base import NewcomerCandidate


# ====================================
# フィクスチャ
# ====================================
@pytest.fixture
def existing_players():
    """既存プレイヤーリスト"""
    return ["Netflix", "Hulu", "ABEMAプレミアム", "U-NEXT", "dアニメストア"]


@pytest.fixture
def mock_llm_newcomer_success():
    """新規参入候補あり用モック"""
    mock = MagicMock()
    mock.call.return_value = '''```json
[
    {
        "player_name": "新動画サービスA",
        "official_url": "https://new-service-a.example.com/",
        "company_name": "株式会社ニューサービスA",
        "entry_date_approx": "2025-10",
        "confidence": 0.8,
        "source_urls": ["https://news.example.com/article1"],
        "reason": "2025年10月にサービス開始"
    },
    {
        "player_name": "新動画サービスB",
        "official_url": "https://new-service-b.example.com/",
        "company_name": "株式会社ニューサービスB",
        "entry_date_approx": "2026-01",
        "confidence": 0.6,
        "source_urls": ["https://news.example.com/article2"],
        "reason": "2026年1月にベータ開始"
    }
]
```'''
    mock.extract_json.return_value = [
        {
            "player_name": "新動画サービスA",
            "official_url": "https://new-service-a.example.com/",
            "company_name": "株式会社ニューサービスA",
            "entry_date_approx": "2025-10",
            "confidence": 0.8,
            "source_urls": ["https://news.example.com/article1"],
            "reason": "2025年10月にサービス開始",
        },
        {
            "player_name": "新動画サービスB",
            "official_url": "https://new-service-b.example.com/",
            "company_name": "株式会社ニューサービスB",
            "entry_date_approx": "2026-01",
            "confidence": 0.6,
            "source_urls": ["https://news.example.com/article2"],
            "reason": "2026年1月にベータ開始",
        },
    ]
    return mock


@pytest.fixture
def mock_llm_newcomer_empty():
    """新規参入なし用モック"""
    mock = MagicMock()
    mock.call.return_value = '```json\n[]\n```'
    mock.extract_json.return_value = []
    return mock


# ====================================
# NewcomerCandidate テスト
# ====================================
class TestNewcomerCandidate:
    """NewcomerCandidate データクラスのテスト"""

    def test_default_values(self):
        """デフォルト値の確認"""
        candidate = NewcomerCandidate(player_name="テストサービス")
        assert candidate.player_name == "テストサービス"
        assert candidate.official_url == ""
        assert candidate.verification_status == "unverified"
        assert candidate.url_verified is False
        assert candidate.confidence == 0.0

    def test_to_dict(self):
        """辞書変換"""
        candidate = NewcomerCandidate(
            player_name="テストサービス",
            official_url="https://example.com",
            confidence=0.8,
            verification_status="verified",
            url_verified=True,
        )
        d = candidate.to_dict()
        assert d["player_name"] == "テストサービス"
        assert d["url_verified"] is True
        assert d["verification_status"] == "verified"


# ====================================
# レスポンス解析テスト
# ====================================
class TestResponseParsing:
    """LLMレスポンス解析のテスト"""

    def test_parse_valid_response(self, mock_llm_newcomer_success):
        """正常なJSONレスポンスの解析"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_success)
        candidates = detector._parse_response(mock_llm_newcomer_success.call.return_value)

        assert len(candidates) == 2
        assert candidates[0].player_name == "新動画サービスA"
        assert candidates[0].confidence == 0.8
        assert candidates[0].verification_status == "unverified"

    def test_parse_empty_array(self, mock_llm_newcomer_empty):
        """空配列レスポンスの正常処理"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_empty)
        candidates = detector._parse_response("[]")
        assert len(candidates) == 0

    def test_parse_invalid_json(self):
        """JSON解析失敗時は空リスト"""
        mock = MagicMock()
        mock.extract_json.return_value = None
        detector = NewcomerDetector(llm_client=mock)
        candidates = detector._parse_response("これはJSONではありません")
        assert len(candidates) == 0

    def test_parse_dict_response_with_results_key(self):
        """dict形式のレスポンス（results キー）"""
        mock = MagicMock()
        mock.extract_json.return_value = {
            "results": [
                {
                    "player_name": "テストサービス",
                    "official_url": "https://example.com",
                    "confidence": 0.7,
                }
            ]
        }
        detector = NewcomerDetector(llm_client=mock)
        candidates = detector._parse_response("...")
        assert len(candidates) == 1
        assert candidates[0].player_name == "テストサービス"

    def test_parse_skips_empty_player_name(self):
        """プレイヤー名が空の候補はスキップ"""
        mock = MagicMock()
        mock.extract_json.return_value = [
            {"player_name": "", "confidence": 0.5},
            {"player_name": "有効なサービス", "confidence": 0.7},
        ]
        detector = NewcomerDetector(llm_client=mock)
        candidates = detector._parse_response("...")
        assert len(candidates) == 1
        assert candidates[0].player_name == "有効なサービス"


# ====================================
# URL検証テスト
# ====================================
class TestUrlVerification:
    """URL自動検証のテスト"""

    @pytest.mark.asyncio
    async def test_verify_url_success(self):
        """URL検証成功"""
        detector = NewcomerDetector()

        with patch("core.sanitizer.requests.head") as mock_head:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "https://example.com/"
            mock_response.history = []
            mock_head.return_value = mock_response

            result = await detector._verify_url("https://example.com")
            assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_verify_url_timeout(self):
        """URL検証タイムアウト"""
        import requests

        detector = NewcomerDetector()

        with patch("core.sanitizer.requests.head") as mock_head:
            mock_head.side_effect = requests.exceptions.Timeout()

            result = await detector._verify_url("https://example.com")
            assert result["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_verify_url_empty(self):
        """空URLの検証"""
        detector = NewcomerDetector()
        result = await detector._verify_url("")
        assert result["error"] == "empty_url"


# ====================================
# 信頼度再計算テスト
# ====================================
class TestConfidenceRecalculation:
    """信頼度再計算のテスト"""

    @pytest.mark.asyncio
    async def test_url_verified_keeps_confidence(
        self, mock_llm_newcomer_success, existing_players
    ):
        """URL検証済みの場合、信頼度は変更なし"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_success)

        with patch.object(detector, "_verify_url") as mock_verify:
            mock_verify.return_value = {"status_code": 200}

            candidates = await detector.detect("動画配信サービス", existing_players)

            # URL検証OKなので信頼度変更なし
            assert candidates[0].confidence == 0.8
            assert candidates[0].url_verified is True
            assert candidates[0].verification_status == "verified"

    @pytest.mark.asyncio
    async def test_url_error_halves_confidence(
        self, mock_llm_newcomer_success, existing_players
    ):
        """URL検証失敗の場合、信頼度が半減"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_success)

        with patch.object(detector, "_verify_url") as mock_verify:
            mock_verify.return_value = {"status_code": 0, "error": "connection_error"}

            candidates = await detector.detect("動画配信サービス", existing_players)

            # URL検証NGで信頼度半減
            assert candidates[0].confidence == 0.4  # 0.8 * 0.5
            assert candidates[0].url_verified is False
            assert candidates[0].verification_status == "url_error"


# ====================================
# verification_status 状態遷移テスト
# ====================================
class TestVerificationStatus:
    """verification_status の状態遷移テスト"""

    @pytest.mark.asyncio
    async def test_status_verified(self, mock_llm_newcomer_success, existing_players):
        """URL検証OK → verified"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_success)

        with patch.object(detector, "_verify_url") as mock_verify:
            mock_verify.return_value = {"status_code": 200}
            candidates = await detector.detect("動画配信サービス", existing_players)
            assert candidates[0].verification_status == "verified"

    @pytest.mark.asyncio
    async def test_status_url_error(self, mock_llm_newcomer_success, existing_players):
        """URL検証エラー → url_error"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_success)

        with patch.object(detector, "_verify_url") as mock_verify:
            mock_verify.return_value = {"status_code": 0, "error": "timeout"}
            candidates = await detector.detect("動画配信サービス", existing_players)
            assert candidates[0].verification_status == "url_error"

    @pytest.mark.asyncio
    async def test_status_unverified_no_url(self, existing_players):
        """URLなし → unverified"""
        mock = MagicMock()
        mock.extract_json.return_value = [
            {
                "player_name": "URLなしサービス",
                "official_url": "",
                "confidence": 0.5,
            }
        ]
        detector = NewcomerDetector(llm_client=mock)

        with patch.object(detector, "_verify_url"):
            candidates = await detector.detect("動画配信サービス", existing_players)
            assert candidates[0].verification_status == "unverified"


# ====================================
# 統合テスト
# ====================================
class TestDetectIntegration:
    """detect() メソッドの統合テスト"""

    @pytest.mark.asyncio
    async def test_detect_with_empty_result(
        self, mock_llm_newcomer_empty, existing_players
    ):
        """新規参入なしの正常処理"""
        detector = NewcomerDetector(llm_client=mock_llm_newcomer_empty)
        candidates = await detector.detect("動画配信サービス", existing_players)
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_detect_with_progress(
        self, mock_llm_newcomer_success, existing_players
    ):
        """進捗コールバック呼び出し確認"""
        progress_calls = []

        def on_progress(current, total, name):
            progress_calls.append((current, total, name))

        detector = NewcomerDetector(llm_client=mock_llm_newcomer_success)

        with patch.object(detector, "_verify_url") as mock_verify:
            mock_verify.return_value = {"status_code": 200}
            await detector.detect(
                "動画配信サービス",
                existing_players,
                on_progress=on_progress,
            )

        assert len(progress_calls) == 3  # 3ステップ
