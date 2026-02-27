#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLMスキーマのユニットテスト
============================
正常・異常・境界値テスト。
"""

import sys
from pathlib import Path

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.llm_schemas import (
    PlayerValidationLLMResponse,
    StoreInvestigationLLMResponse,
    AttributeItemLLMResponse,
    AttributeBatchLLMResponse,
    NewcomerCandidateLLMResponse,
    parse_llm_response,
)


# ====================================
# PlayerValidationLLMResponse
# ====================================
class TestPlayerValidationLLMResponse:
    """正誤チェック LLMレスポンススキーマ"""

    def test_normal_response(self):
        """正常なレスポンスをパース"""
        data = {
            "is_active": True,
            "change_type": "none",
            "current_service_name": "楽天カード",
            "current_company_name": "楽天カード株式会社",
            "current_url": "https://www.rakuten-card.co.jp/",
            "changes": [],
            "news": "",
            "confidence": 0.95,
            "sources": ["https://www.rakuten-card.co.jp/"],
        }
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.is_active is True
        assert result.confidence == 0.95
        assert result.change_type == "none"

    def test_news_as_list(self):
        """news がリストの場合は文字列に変換"""
        data = {
            "news": ["ニュース1", "ニュース2"],
            "confidence": 0.8,
        }
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.news == "ニュース1 / ニュース2"

    def test_news_as_none(self):
        """news が None の場合は空文字"""
        data = {"news": None, "confidence": 0.8}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.news == ""

    def test_confidence_as_string(self):
        """confidence が文字列の場合は float に変換"""
        data = {"confidence": "0.85"}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.confidence == 0.85

    def test_confidence_none_uses_default(self):
        """confidence が None の場合はデフォルト 0.5"""
        data = {"confidence": None}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.confidence == 0.5

    def test_confidence_invalid_string(self):
        """confidence が無効な文字列の場合はデフォルト"""
        data = {"confidence": "高い"}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.confidence == 0.5

    def test_changes_as_string(self):
        """changes が文字列の場合はリスト化"""
        data = {"changes": "サービス名変更", "confidence": 0.8}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.changes == ["サービス名変更"]

    def test_changes_as_none(self):
        """changes が None の場合は空リスト"""
        data = {"changes": None, "confidence": 0.8}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.changes == []

    def test_sources_as_string(self):
        """sources が文字列の場合はリスト化"""
        data = {"sources": "https://example.com", "confidence": 0.8}
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.sources == ["https://example.com"]

    def test_extra_fields_ignored(self):
        """余分なフィールドは無視"""
        data = {
            "confidence": 0.8,
            "unknown_field": "value",
            "another_field": 123,
        }
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.confidence == 0.8
        assert not hasattr(result, "unknown_field")

    def test_empty_dict(self):
        """空辞書でもデフォルト値で生成"""
        result = PlayerValidationLLMResponse.model_validate({})
        assert result.is_active is True
        assert result.confidence == 0.5
        assert result.changes == []

    def test_withdrawal_response(self):
        """撤退ケース"""
        data = {
            "is_active": False,
            "change_type": "withdrawal",
            "confidence": 0.9,
            "changes": ["2025年3月にサービス終了"],
            "news": "2025年3月31日をもってサービスを終了",
        }
        result = PlayerValidationLLMResponse.model_validate(data)
        assert result.is_active is False
        assert result.change_type == "withdrawal"


# ====================================
# StoreInvestigationLLMResponse
# ====================================
class TestStoreInvestigationLLMResponse:
    """店舗調査 LLMレスポンススキーマ"""

    def test_normal_response(self):
        """正常なレスポンス"""
        data = {
            "total_stores": 100,
            "direct_stores": 80,
            "franchise_stores": 20,
            "confidence": 0.85,
            "sources": ["https://example.com/stores/"],
        }
        result = StoreInvestigationLLMResponse.model_validate(data)
        assert result.total_stores == 100
        assert result.direct_stores == 80

    def test_total_stores_as_string(self):
        """total_stores が '約100店舗' のような文字列"""
        data = {"total_stores": "約100店舗", "confidence": 0.8}
        result = StoreInvestigationLLMResponse.model_validate(data)
        assert result.total_stores == 100

    def test_total_stores_as_none(self):
        """total_stores が None"""
        data = {"total_stores": None, "confidence": 0.8}
        result = StoreInvestigationLLMResponse.model_validate(data)
        assert result.total_stores == 0

    def test_prefecture_presence(self):
        """都道府県展開有無"""
        data = {
            "total_stores": 50,
            "prefecture_presence": {"東京都": True, "大阪府": False, "北海道": None},
            "confidence": 0.9,
        }
        result = StoreInvestigationLLMResponse.model_validate(data)
        assert result.prefecture_presence["東京都"] is True
        assert result.prefecture_presence["大阪府"] is False


# ====================================
# AttributeItemLLMResponse
# ====================================
class TestAttributeItemLLMResponse:
    """属性調査 LLMレスポンススキーマ"""

    def test_normal_response(self):
        """正常なレスポンス"""
        data = {
            "player_name": "Netflix",
            "attributes": {"アクション": True, "ホラー": False, "ドキュメンタリー": None},
            "confidence": 0.9,
            "sources": ["https://www.netflix.com/"],
        }
        result = AttributeItemLLMResponse.model_validate(data)
        assert result.player_name == "Netflix"
        assert result.attributes["アクション"] is True
        assert result.attributes["ホラー"] is False

    def test_sources_as_string(self):
        """sources が文字列"""
        data = {
            "player_name": "Test",
            "attributes": {},
            "sources": "https://example.com",
        }
        result = AttributeItemLLMResponse.model_validate(data)
        assert result.sources == ["https://example.com"]


# ====================================
# NewcomerCandidateLLMResponse
# ====================================
class TestNewcomerCandidateLLMResponse:
    """新規参入候補 LLMレスポンススキーマ"""

    def test_normal_response(self):
        """正常なレスポンス"""
        data = {
            "player_name": "新サービス",
            "official_url": "https://new-service.com",
            "company_name": "新会社",
            "entry_date_approx": "2025-06",
            "confidence": 0.8,
            "source_urls": ["https://news.example.com"],
            "reason": "2025年に新規参入",
        }
        result = NewcomerCandidateLLMResponse.model_validate(data)
        assert result.player_name == "新サービス"
        assert result.confidence == 0.8

    def test_source_urls_as_string(self):
        """source_urls が文字列"""
        data = {
            "player_name": "Test",
            "source_urls": "https://example.com",
        }
        result = NewcomerCandidateLLMResponse.model_validate(data)
        assert result.source_urls == ["https://example.com"]


# ====================================
# parse_llm_response ユーティリティ
# ====================================
class TestParseLlmResponse:
    """parse_llm_response 関数のテスト"""

    def test_valid_data(self):
        """正常データ → モデルを返す"""
        data = {"confidence": 0.9, "is_active": True}
        result = parse_llm_response(data, PlayerValidationLLMResponse)
        assert result is not None
        assert result.confidence == 0.9

    def test_empty_dict(self):
        """空辞書 → デフォルト値でモデルを返す"""
        result = parse_llm_response({}, PlayerValidationLLMResponse)
        assert result is not None
        assert result.is_active is True

    def test_none_input(self):
        """None → None を返す"""
        result = parse_llm_response(None, PlayerValidationLLMResponse)
        assert result is None

    def test_invalid_type(self):
        """不正な型 → None を返す"""
        result = parse_llm_response("not a dict", PlayerValidationLLMResponse)
        assert result is None
