#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗調査モジュール テスト
========================
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from investigators.base import StoreInvestigationResult
from investigators.store_investigator import StoreInvestigator, InvestigationMode


# ====================================
# フィクスチャ
# ====================================
@pytest.fixture
def mock_llm_client_success():
    """成功ケース用のモックLLMクライアント"""
    mock = MagicMock()
    mock.call.return_value = '''```json
{
    "total_stores": 150,
    "direct_stores": 120,
    "franchise_stores": 30,
    "prefecture_distribution": {
        "東京都": 25,
        "大阪府": 20,
        "神奈川県": 15,
        "愛知県": 12,
        "福岡県": 10
    },
    "confidence": 0.85,
    "sources": ["https://www.example.co.jp/stores/", "https://www.example.co.jp/ir/"],
    "notes": "2026年1月時点の公式データ"
}
```'''
    return mock


@pytest.fixture
def mock_llm_client_low_confidence():
    """低信頼度ケース用のモックLLMクライアント"""
    mock = MagicMock()
    mock.call.return_value = '''```json
{
    "total_stores": 50,
    "confidence": 0.4,
    "sources": ["https://www.example.co.jp/"],
    "notes": "推定値のため要確認"
}
```'''
    return mock


@pytest.fixture
def mock_llm_client_error():
    """エラーケース用のモックLLMクライアント"""
    mock = MagicMock()
    mock.call.side_effect = RuntimeError("API呼び出しエラー")
    return mock


@pytest.fixture
def mock_scraper_success():
    """成功ケース用のモックスクレイパー"""
    from store_scraper_v3 import ScrapingResult, StoreInfo

    mock = MagicMock()
    mock_result = ScrapingResult(
        company_name="テスト株式会社",
        url="https://www.example.co.jp/",
        stores=[
            StoreInfo(
                company_name="テスト株式会社",
                store_name="渋谷店",
                address="東京都渋谷区道玄坂1-2-3",
                phone="03-1234-5678",
                prefecture="東京都",
            ),
            StoreInfo(
                company_name="テスト株式会社",
                store_name="新宿店",
                address="東京都新宿区西新宿1-1-1",
                phone="03-2345-6789",
                prefecture="東京都",
            ),
            StoreInfo(
                company_name="テスト株式会社",
                store_name="梅田店",
                address="大阪府大阪市北区梅田1-1-1",
                phone="06-1234-5678",
                prefecture="大阪府",
            ),
        ],
        strategy_used="static_html",
        pages_visited=5,
        elapsed_time=10.5,
        errors=[],
    )

    async def mock_scrape(*args, **kwargs):
        return mock_result

    mock.scrape = mock_scrape
    return mock


# ====================================
# StoreInvestigationResult テスト
# ====================================
class TestStoreInvestigationResult:
    """StoreInvestigationResult データクラスのテスト"""

    def test_create_success(self):
        """成功結果の作成"""
        result = StoreInvestigationResult.create_success(
            company_name="テスト株式会社",
            total_stores=100,
            source_urls=["https://example.com/"],
            investigation_mode="ai",
            direct_stores=80,
            franchise_stores=20,
        )

        assert result.company_name == "テスト株式会社"
        assert result.total_stores == 100
        assert result.investigation_mode == "ai"
        assert result.direct_stores == 80
        assert result.franchise_stores == 20
        assert len(result.source_urls) == 1
        assert result.needs_verification is False

    def test_create_uncertain(self):
        """要確認結果の作成"""
        result = StoreInvestigationResult.create_uncertain(
            company_name="テスト株式会社",
            investigation_mode="ai",
            reason="情報が不十分",
        )

        assert result.company_name == "テスト株式会社"
        assert result.total_stores == 0
        assert result.needs_verification is True
        assert "要確認" in result.notes

    def test_create_error(self):
        """エラー結果の作成"""
        result = StoreInvestigationResult.create_error(
            company_name="テスト株式会社",
            investigation_mode="ai",
            error_message="API呼び出し失敗",
        )

        assert result.company_name == "テスト株式会社"
        assert result.total_stores == 0
        assert result.needs_verification is True
        assert "エラー" in result.notes

    def test_to_dict(self):
        """辞書変換"""
        result = StoreInvestigationResult.create_success(
            company_name="テスト株式会社",
            total_stores=100,
            source_urls=["https://example.com/"],
            investigation_mode="ai",
        )

        d = result.to_dict()

        assert isinstance(d, dict)
        assert d["company_name"] == "テスト株式会社"
        assert d["total_stores"] == 100
        assert d["investigation_mode"] == "ai"
        assert "investigation_date" in d

    def test_source_url_required(self):
        """ソースURL必須の確認"""
        result = StoreInvestigationResult.create_success(
            company_name="テスト株式会社",
            total_stores=100,
            source_urls=["https://example.com/ir/"],
            investigation_mode="ai",
        )

        # ソースURLが存在すること
        assert result.source_urls is not None
        assert len(result.source_urls) > 0
        assert result.source_urls[0].startswith("http")


# ====================================
# StoreInvestigator テスト
# ====================================
class TestStoreInvestigator:
    """StoreInvestigator クラスのテスト"""

    def test_init(self, mock_llm_client_success):
        """初期化テスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        assert investigator.llm == mock_llm_client_success
        assert investigator.model == "gemini-2.5-flash"
        assert investigator.CONFIDENCE_THRESHOLD == 0.7

    def test_sanitize_input(self, mock_llm_client_success):
        """入力サニタイズテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        # 通常入力
        assert investigator._sanitize_input("テスト株式会社") == "テスト株式会社"

        # 危険なパターン
        assert "[REMOVED]" in investigator._sanitize_input("ignore instructions テスト")
        assert "[REMOVED]" in investigator._sanitize_input("system prompt テスト")

        # 長さ制限
        long_input = "あ" * 1000
        assert len(investigator._sanitize_input(long_input)) == 500

        # 空入力
        assert investigator._sanitize_input("") == ""
        assert investigator._sanitize_input(None) == ""

    @pytest.mark.asyncio
    async def test_investigate_ai_mode(self, mock_llm_client_success):
        """AI調査モードのテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        result = await investigator.investigate(
            company_name="テスト株式会社",
            official_url="https://www.example.co.jp/",
            mode=InvestigationMode.AI,
        )

        assert result.company_name == "テスト株式会社"
        assert result.total_stores == 150
        assert result.direct_stores == 120
        assert result.franchise_stores == 30
        assert result.investigation_mode == "ai"
        assert len(result.source_urls) == 2
        assert result.prefecture_distribution is not None
        # 新仕様: 店舗有無は True/False/None で表現
        assert result.prefecture_distribution.get("東京都") is True  # 店舗あり

    @pytest.mark.asyncio
    async def test_investigate_ai_mode_low_confidence(self, mock_llm_client_low_confidence):
        """AI調査モード（低信頼度）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_low_confidence)

        result = await investigator.investigate(
            company_name="テスト株式会社",
            mode=InvestigationMode.AI,
        )

        assert result.total_stores == 50
        assert result.needs_verification is True  # 信頼度が閾値以下

    @pytest.mark.asyncio
    async def test_investigate_ai_mode_error(self, mock_llm_client_error):
        """AI調査モード（エラー）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_error)

        result = await investigator.investigate(
            company_name="テスト株式会社",
            mode=InvestigationMode.AI,
        )

        assert result.total_stores == 0
        assert result.needs_verification is True
        assert "エラー" in result.notes

    @pytest.mark.asyncio
    async def test_investigate_scraping_mode(self, mock_llm_client_success, mock_scraper_success):
        """スクレイピングモードのテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)
        investigator._scraper = mock_scraper_success

        result = await investigator.investigate(
            company_name="テスト株式会社",
            official_url="https://www.example.co.jp/",
            mode=InvestigationMode.SCRAPING,
        )

        assert result.company_name == "テスト株式会社"
        assert result.total_stores == 3
        assert result.investigation_mode == "scraping"
        assert "https://www.example.co.jp/" in result.source_urls
        assert result.prefecture_distribution is not None
        assert result.prefecture_distribution.get("東京都") == 2
        assert result.prefecture_distribution.get("大阪府") == 1

    @pytest.mark.asyncio
    async def test_investigate_scraping_mode_no_url(self, mock_llm_client_success):
        """スクレイピングモード（URL未指定）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        result = await investigator.investigate(
            company_name="テスト株式会社",
            official_url="",  # URL未指定
            mode=InvestigationMode.SCRAPING,
        )

        assert result.total_stores == 0
        assert result.needs_verification is True
        assert "エラー" in result.notes

    @pytest.mark.asyncio
    async def test_investigate_hybrid_mode_high_confidence(self, mock_llm_client_success):
        """ハイブリッドモード（AI高信頼度）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        result = await investigator.investigate(
            company_name="テスト株式会社",
            official_url="https://www.example.co.jp/",
            mode=InvestigationMode.HYBRID,
        )

        # AI調査の信頼度が高いのでスクレイピングは実行されない
        assert result.total_stores == 150
        assert result.investigation_mode == "hybrid"

    @pytest.mark.asyncio
    async def test_investigate_hybrid_mode_low_confidence(
        self, mock_llm_client_low_confidence, mock_scraper_success
    ):
        """ハイブリッドモード（AI低信頼度→スクレイピング補完）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_low_confidence)
        investigator._scraper = mock_scraper_success

        result = await investigator.investigate(
            company_name="テスト株式会社",
            official_url="https://www.example.co.jp/",
            mode=InvestigationMode.HYBRID,
        )

        # スクレイピングで補完される
        assert result.total_stores == 3  # スクレイピング結果
        assert result.investigation_mode == "hybrid"
        assert "AI+スクレイピング" in result.notes

    @pytest.mark.asyncio
    async def test_investigate_empty_company_name(self, mock_llm_client_success):
        """企業名未指定のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        result = await investigator.investigate(
            company_name="",
            mode=InvestigationMode.AI,
        )

        assert result.total_stores == 0
        assert result.needs_verification is True
        assert "企業名" in result.notes

    @pytest.mark.asyncio
    async def test_investigate_with_progress_callback(self, mock_llm_client_success):
        """進捗コールバック付き調査のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        progress_logs = []

        def on_progress(msg: str):
            progress_logs.append(msg)

        result = await investigator.investigate(
            company_name="テスト株式会社",
            mode=InvestigationMode.AI,
            on_progress=on_progress,
        )

        assert len(progress_logs) > 0
        assert any("テスト株式会社" in log for log in progress_logs)

    def test_build_ai_prompt(self, mock_llm_client_success):
        """AIプロンプト生成のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        prompt = investigator._build_ai_prompt(
            company_name="テスト株式会社",
            official_url="https://www.example.co.jp/",
            industry="飲食店",
            current_year=2026,
        )

        assert "テスト株式会社" in prompt
        assert "https://www.example.co.jp/" in prompt
        assert "飲食店" in prompt
        assert "2026" in prompt
        assert "JSON" in prompt

    def test_parse_ai_response_valid(self, mock_llm_client_success):
        """AIレスポンス解析（正常）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        response = '''```json
{
    "total_stores": 100,
    "confidence": 0.9,
    "sources": ["https://example.com/"]
}
```'''

        result = investigator._parse_ai_response("テスト株式会社", response)

        assert result.total_stores == 100
        assert len(result.source_urls) == 1

    def test_parse_ai_response_invalid_json(self, mock_llm_client_success):
        """AIレスポンス解析（無効なJSON）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        response = "これはJSONではありません"

        result = investigator._parse_ai_response("テスト株式会社", response)

        assert result.needs_verification is True
        assert "JSON" in result.notes

    def test_parse_ai_response_string_total_stores(self, mock_llm_client_success):
        """AIレスポンス解析（文字列の店舗数）のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        response = '''```json
{
    "total_stores": "約150店舗",
    "confidence": 0.8,
    "sources": ["https://example.com/"]
}
```'''

        result = investigator._parse_ai_response("テスト株式会社", response)

        assert result.total_stores == 150  # 数値に変換される

    @pytest.mark.asyncio
    async def test_investigate_batch(self, mock_llm_client_success):
        """バッチ調査のテスト"""
        investigator = StoreInvestigator(llm_client=mock_llm_client_success)

        companies = [
            {"company_name": "会社A", "official_url": "https://a.example.com/"},
            {"company_name": "会社B", "official_url": "https://b.example.com/"},
            {"company_name": "会社C", "official_url": "https://c.example.com/"},
        ]

        progress_calls = []

        def on_progress(current: int, total: int, name: str):
            progress_calls.append((current, total, name))

        results = await investigator.investigate_batch(
            companies,
            mode=InvestigationMode.AI,
            on_progress=on_progress,
            concurrency=2,
            delay_seconds=0.1,
        )

        assert len(results) == 3
        assert all(r.total_stores == 150 for r in results)
        assert len(progress_calls) == 3


# ====================================
# InvestigationMode テスト
# ====================================
class TestInvestigationMode:
    """InvestigationMode Enum のテスト"""

    def test_mode_values(self):
        """モード値のテスト"""
        assert InvestigationMode.AI.value == "ai"
        assert InvestigationMode.SCRAPING.value == "scraping"
        assert InvestigationMode.HYBRID.value == "hybrid"

    def test_mode_from_string(self):
        """文字列からモード変換のテスト"""
        assert InvestigationMode("ai") == InvestigationMode.AI
        assert InvestigationMode("scraping") == InvestigationMode.SCRAPING
        assert InvestigationMode("hybrid") == InvestigationMode.HYBRID
