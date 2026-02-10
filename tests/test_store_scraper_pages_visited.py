#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
store_scraper_v3 pages_visited トラッキング テスト
===================================================
各戦略がページアクセス数を正しくカウントすることを検証する。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from store_scraper_v3 import (
    ScrapingStrategy,
    StaticHTMLStrategy,
    BrowserAutomationStrategy,
    AIInferenceStrategy,
    MultiStrategyScraper,
    ScrapingResult,
    StoreInfo,
    LLMClient,
)


# ====================================
# フィクスチャ
# ====================================
@pytest.fixture
def mock_llm():
    """モックLLMクライアント"""
    mock = MagicMock(spec=LLMClient)
    mock.call.return_value = '```json\n[]\n```'
    return mock


@pytest.fixture
def static_strategy():
    """StaticHTMLStrategy インスタンス"""
    return StaticHTMLStrategy()


@pytest.fixture
def browser_strategy():
    """BrowserAutomationStrategy インスタンス"""
    return BrowserAutomationStrategy()


@pytest.fixture
def ai_strategy():
    """AIInferenceStrategy インスタンス"""
    return AIInferenceStrategy()


# ====================================
# 基底クラステスト
# ====================================
class TestScrapingStrategyPageCount:
    """ScrapingStrategy のページカウンター基本テスト"""

    def test_initial_pages_visited_is_zero(self, static_strategy: StaticHTMLStrategy):
        """初期状態でページカウントが0"""
        assert static_strategy.pages_visited == 0

    def test_count_page_visit_increments(self, static_strategy: StaticHTMLStrategy):
        """_count_page_visit でカウントが増加"""
        static_strategy._count_page_visit()
        assert static_strategy.pages_visited == 1
        static_strategy._count_page_visit()
        assert static_strategy.pages_visited == 2

    def test_reset_page_count(self, static_strategy: StaticHTMLStrategy):
        """reset_page_count でカウントがリセットされる"""
        static_strategy._count_page_visit()
        static_strategy._count_page_visit()
        assert static_strategy.pages_visited == 2
        static_strategy.reset_page_count()
        assert static_strategy.pages_visited == 0

    def test_pages_visited_property_readonly(self, static_strategy: StaticHTMLStrategy):
        """pages_visited プロパティは読み取り専用"""
        with pytest.raises(AttributeError):
            static_strategy.pages_visited = 10


# ====================================
# StaticHTMLStrategy テスト
# ====================================
class TestStaticHTMLStrategyPageCount:
    """StaticHTMLStrategy のページカウントテスト"""

    @pytest.mark.asyncio
    async def test_fetch_page_increments_count(self, static_strategy: StaticHTMLStrategy):
        """_fetch_page がページカウントをインクリメント"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>test</body></html>"
        mock_response.apparent_encoding = "utf-8"

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await static_strategy._fetch_page("https://example.com")

        assert static_strategy.pages_visited == 1

    @pytest.mark.asyncio
    async def test_multiple_fetch_pages_count(self, static_strategy: StaticHTMLStrategy):
        """複数ページ取得でカウントが正しく増加"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>test</body></html>"
        mock_response.apparent_encoding = "utf-8"

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await static_strategy._fetch_page("https://example.com/page1")
            await static_strategy._fetch_page("https://example.com/page2")
            await static_strategy._fetch_page("https://example.com/page3")

        assert static_strategy.pages_visited == 3

    @pytest.mark.asyncio
    async def test_scrape_counts_top_page(self, static_strategy: StaticHTMLStrategy, mock_llm: MagicMock):
        """scrape メソッドがトップページアクセスをカウント"""
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Test</h1></body></html>"
        mock_response.apparent_encoding = "utf-8"

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await static_strategy.scrape("TestCo", "https://example.com", mock_llm)

        # 少なくとも1ページ（トップページ）はアクセスしている
        assert static_strategy.pages_visited >= 1


# ====================================
# BrowserAutomationStrategy テスト
# ====================================
class TestBrowserAutomationStrategyPageCount:
    """BrowserAutomationStrategy のページカウントテスト"""

    @pytest.mark.asyncio
    async def test_browser_scrape_counts_pages(
        self, browser_strategy: BrowserAutomationStrategy, mock_llm: MagicMock
    ):
        """ブラウザ戦略がページアクセスをカウント"""
        # Playwright のモック設定
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(
            return_value="<html><body>test</body></html>"
        )
        mock_page.evaluate = AsyncMock(return_value=[])
        mock_page.query_selector_all = AsyncMock(return_value=[])

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright = AsyncMock()
        mock_playwright.chromium = mock_chromium

        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_playwright_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "store_scraper_v3.async_playwright",
            return_value=mock_playwright_cm,
            create=True,
        ):
            # playwright のインポートをモック
            with patch.dict("sys.modules", {"playwright.async_api": MagicMock()}):
                await browser_strategy.scrape(
                    "TestCo", "https://example.com", mock_llm
                )

        # トップページは必ずアクセスされる
        assert browser_strategy.pages_visited >= 1


# ====================================
# AIInferenceStrategy テスト
# ====================================
class TestAIInferenceStrategyPageCount:
    """AIInferenceStrategy のページカウントテスト"""

    @pytest.mark.asyncio
    async def test_analyze_site_counts_page(
        self, ai_strategy: AIInferenceStrategy, mock_llm: MagicMock
    ):
        """_analyze_site_structure がページアクセスをカウント"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>test</body></html>"
        mock_response.apparent_encoding = "utf-8"

        mock_llm.call.return_value = '{"api_endpoint": null, "prefecture_urls": [], "recommended_approach": "crawl"}'

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await ai_strategy._analyze_site_structure(
                "https://example.com", "TestCo", mock_llm
            )

        assert ai_strategy.pages_visited == 1

    @pytest.mark.asyncio
    async def test_fetch_from_api_counts_page(
        self, ai_strategy: AIInferenceStrategy, mock_llm: MagicMock
    ):
        """_fetch_from_api がAPIアクセスをカウント"""
        mock_response = MagicMock()
        mock_response.json.return_value = []

        mock_llm.call.return_value = "[]"

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await ai_strategy._fetch_from_api(
                "https://api.example.com/stores", "TestCo", mock_llm
            )

        assert ai_strategy.pages_visited == 1

    @pytest.mark.asyncio
    async def test_scrape_page_counts_page(
        self, ai_strategy: AIInferenceStrategy, mock_llm: MagicMock
    ):
        """_scrape_page がページアクセスをカウント"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>test</body></html>"
        mock_response.apparent_encoding = "utf-8"

        mock_llm.call.return_value = "[]"

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await ai_strategy._scrape_page(
                "https://example.com/stores", "TestCo", mock_llm
            )

        assert ai_strategy.pages_visited == 1


# ====================================
# MultiStrategyScraper 統合テスト
# ====================================
class TestMultiStrategyScraperPageCount:
    """MultiStrategyScraper のページカウント統合テスト"""

    @pytest.mark.asyncio
    async def test_scrape_result_has_pages_visited(self):
        """ScrapingResult の pages_visited が 0 でないことを検証"""
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Test Store</h1></body></html>"
        mock_response.apparent_encoding = "utf-8"

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            scraper = MultiStrategyScraper(api_key="test-key")

        # LLMのモック
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.call.return_value = "[]"
        scraper.llm = mock_llm

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            with patch("store_scraper_v3.requests.post", return_value=MagicMock()):
                result = await scraper.scrape("TestCo", "https://example.com")

        assert isinstance(result, ScrapingResult)
        assert result.pages_visited > 0

    @pytest.mark.asyncio
    async def test_pages_visited_accumulates_across_strategies(self):
        """複数戦略の訪問ページ数が合算される"""
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            scraper = MultiStrategyScraper(api_key="test-key")

        # 各戦略のカウンターを手動設定
        for strategy in scraper.strategies:
            strategy._pages_visited = 5

        total = sum(s.pages_visited for s in scraper.strategies)
        assert total == 15  # 3戦略 x 5ページ

    def test_scraping_result_dataclass_pages_visited(self):
        """ScrapingResult の pages_visited フィールドが正しく動作"""
        result = ScrapingResult(
            company_name="TestCo",
            url="https://example.com",
            stores=[],
            strategy_used="static_html",
            pages_visited=42,
            elapsed_time=1.5,
        )
        assert result.pages_visited == 42

    @pytest.mark.asyncio
    async def test_fresh_strategies_start_at_zero(self):
        """新しいスクレイパーの全戦略がカウント0で開始"""
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            scraper = MultiStrategyScraper(api_key="test-key")

        for strategy in scraper.strategies:
            assert strategy.pages_visited == 0
