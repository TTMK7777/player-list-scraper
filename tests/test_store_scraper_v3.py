#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
store_scraper_v3 セキュリティ・エラー処理テスト
================================================
SSRF防止 (_validate_url) と HTTPエラー処理 (_fetch_page) を検証する。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from store_scraper_v3 import (
    AIInferenceStrategy,
    StaticHTMLStrategy,
)


# ====================================
# フィクスチャ
# ====================================
@pytest.fixture
def ai_strategy():
    """AIInferenceStrategy インスタンス"""
    return AIInferenceStrategy()


@pytest.fixture
def static_strategy():
    """StaticHTMLStrategy インスタンス"""
    return StaticHTMLStrategy()


# ====================================
# SSRF防止テスト (_validate_url)
# ====================================
class TestValidateUrl:
    """AIInferenceStrategy._validate_url の SSRF防止テスト"""

    def test_http_url_is_allowed(self, ai_strategy: AIInferenceStrategy):
        """http:// スキームは許可される"""
        # 例外が発生しなければ OK
        ai_strategy._validate_url("http://example.com/api/stores")

    def test_https_url_is_allowed(self, ai_strategy: AIInferenceStrategy):
        """https:// スキームは許可される"""
        ai_strategy._validate_url("https://example.com/api/stores")

    def test_file_scheme_is_rejected(self, ai_strategy: AIInferenceStrategy):
        """file:// スキームは拒否される"""
        with pytest.raises(ValueError, match="許可されていないURLスキーム"):
            ai_strategy._validate_url("file:///etc/passwd")

    def test_ftp_scheme_is_rejected(self, ai_strategy: AIInferenceStrategy):
        """ftp:// スキームは拒否される"""
        with pytest.raises(ValueError, match="許可されていないURLスキーム"):
            ai_strategy._validate_url("ftp://example.com/data")

    def test_loopback_ipv4_is_rejected(self, ai_strategy: AIInferenceStrategy):
        """http://127.0.0.1 はローカルループバックとして拒否される"""
        with pytest.raises(ValueError, match="プライベート/ローカルIPへのアクセスは禁止"):
            ai_strategy._validate_url("http://127.0.0.1/admin")

    def test_private_ip_class_a_is_rejected(self, ai_strategy: AIInferenceStrategy):
        """http://10.0.0.1 はプライベートIPとして拒否される"""
        with pytest.raises(ValueError, match="プライベート/ローカルIPへのアクセスは禁止"):
            ai_strategy._validate_url("http://10.0.0.1/internal")

    def test_private_ip_class_c_is_rejected(self, ai_strategy: AIInferenceStrategy):
        """http://192.168.1.1 はプライベートIPとして拒否される"""
        with pytest.raises(ValueError, match="プライベート/ローカルIPへのアクセスは禁止"):
            ai_strategy._validate_url("http://192.168.1.1/router")

    def test_public_domain_is_allowed(self, ai_strategy: AIInferenceStrategy):
        """http://example.com は通常のドメインとして許可される"""
        # 例外が発生しなければ OK
        ai_strategy._validate_url("http://example.com/stores")


# ====================================
# HTTPエラー処理テスト (_fetch_page)
# ====================================
class TestFetchPageHttpError:
    """StaticHTMLStrategy._fetch_page の HTTPエラー処理テスト"""

    @pytest.mark.asyncio
    async def test_http_404_raises_http_error(self, static_strategy: StaticHTMLStrategy):
        """404 レスポンスで requests.HTTPError が送出される"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=404)
        )

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                await static_strategy._fetch_page("https://example.com/not-found")

    @pytest.mark.asyncio
    async def test_http_500_raises_http_error(self, static_strategy: StaticHTMLStrategy):
        """500 レスポンスで requests.HTTPError が送出される"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=500)
        )

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                await static_strategy._fetch_page("https://example.com/server-error")

    @pytest.mark.asyncio
    async def test_http_error_does_not_increment_page_count(
        self, static_strategy: StaticHTMLStrategy
    ):
        """HTTPエラー時はページカウントがインクリメントされない"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=404)
        )

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                await static_strategy._fetch_page("https://example.com/not-found")

        # raise_for_status() が先に例外を送出するため、_count_page_visit() は呼ばれない
        assert static_strategy.pages_visited == 0

    @pytest.mark.asyncio
    async def test_successful_fetch_increments_page_count(
        self, static_strategy: StaticHTMLStrategy
    ):
        """正常なレスポンスでページカウントがインクリメントされる（対照テスト）"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.apparent_encoding = "utf-8"
        mock_response.text = "<html><body>OK</body></html>"

        with patch("store_scraper_v3.requests.get", return_value=mock_response):
            await static_strategy._fetch_page("https://example.com/")

        assert static_strategy.pages_visited == 1
