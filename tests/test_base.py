#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
base.py のユニットテスト
========================
should_need_verification / should_need_manual_review / is_confident の境界値テスト。
"""

import sys
from pathlib import Path

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime
from investigators.base import (
    StoreInvestigationResult,
    ValidationResult,
    ValidationStatus,
    AlertLevel,
    ChangeType,
)


# ====================================
# StoreInvestigationResult.should_need_verification
# ====================================
class TestShouldNeedVerification:
    """should_need_verification 静的メソッドの境界値テスト"""

    def test_high_confidence_with_stores(self):
        """信頼度が高く店舗あり → 確認不要"""
        assert StoreInvestigationResult.should_need_verification(100, 0.85) is False

    def test_exact_threshold(self):
        """信頼度がちょうど閾値 → 確認不要"""
        assert StoreInvestigationResult.should_need_verification(100, 0.7) is False

    def test_below_threshold(self):
        """信頼度が閾値以下 → 確認必要"""
        assert StoreInvestigationResult.should_need_verification(100, 0.69) is True

    def test_zero_stores(self):
        """店舗数0 → 信頼度に関係なく確認必要"""
        assert StoreInvestigationResult.should_need_verification(0, 0.95) is True

    def test_zero_stores_and_low_confidence(self):
        """店舗数0かつ低信頼度 → 確認必要"""
        assert StoreInvestigationResult.should_need_verification(0, 0.3) is True

    def test_custom_threshold(self):
        """カスタム閾値"""
        assert StoreInvestigationResult.should_need_verification(100, 0.5, threshold=0.5) is False
        assert StoreInvestigationResult.should_need_verification(100, 0.49, threshold=0.5) is True


# ====================================
# StoreInvestigationResult.is_confident
# ====================================
class TestIsConfident:
    """is_confident プロパティのテスト"""

    def test_confident_result(self):
        """needs_verification=False, total_stores>0 → 信頼できる"""
        result = StoreInvestigationResult(
            company_name="テスト",
            total_stores=100,
            source_urls=[],
            investigation_date=datetime.now(),
            investigation_mode="ai",
            needs_verification=False,
        )
        assert result.is_confident is True

    def test_needs_verification(self):
        """needs_verification=True → 信頼できない"""
        result = StoreInvestigationResult(
            company_name="テスト",
            total_stores=100,
            source_urls=[],
            investigation_date=datetime.now(),
            investigation_mode="ai",
            needs_verification=True,
        )
        assert result.is_confident is False

    def test_zero_stores(self):
        """total_stores=0 → 信頼できない"""
        result = StoreInvestigationResult(
            company_name="テスト",
            total_stores=0,
            source_urls=[],
            investigation_date=datetime.now(),
            investigation_mode="ai",
            needs_verification=False,
        )
        assert result.is_confident is False


# ====================================
# ValidationResult.should_need_manual_review
# ====================================
class TestShouldNeedManualReview:
    """should_need_manual_review 静的メソッドの境界値テスト"""

    def test_uncertain_status(self):
        """UNCERTAIN ステータス → 手動確認必要"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.UNCERTAIN, 0.9
        ) is True

    def test_low_confidence(self):
        """信頼度が低い → 手動確認必要"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.CONFIRMED, 0.5
        ) is True

    def test_exact_threshold(self):
        """信頼度がちょうど閾値 → 確認不要"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.CONFIRMED, 0.6
        ) is False

    def test_below_threshold(self):
        """信頼度が閾値未満 → 手動確認必要"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.CONFIRMED, 0.59
        ) is True

    def test_high_confidence_confirmed(self):
        """信頼度が高い CONFIRMED → 確認不要"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.CONFIRMED, 0.95
        ) is False

    def test_unchanged_high_confidence(self):
        """UNCHANGED + 高信頼度 → 確認不要"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.UNCHANGED, 0.9
        ) is False

    def test_custom_threshold(self):
        """カスタム閾値"""
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.CONFIRMED, 0.5, threshold=0.5
        ) is False
        assert ValidationResult.should_need_manual_review(
            ValidationStatus.CONFIRMED, 0.49, threshold=0.5
        ) is True


# ====================================
# industry=None のテスト
# ====================================
class TestIndustryNone:
    """industry=None での動作確認"""

    def test_validation_result_create_unchanged_no_industry(self):
        """ValidationResult.create_unchanged は industry フィールドを持たないので影響なし"""
        result = ValidationResult.create_unchanged(
            player_name="テスト",
            url="https://example.com",
        )
        assert result.status == ValidationStatus.UNCHANGED

    def test_store_result_with_none_industry(self):
        """StoreInvestigationResult は industry フィールドを持たないので影響なし"""
        result = StoreInvestigationResult.create_success(
            company_name="テスト",
            total_stores=100,
            source_urls=["https://example.com"],
            investigation_mode="ai",
        )
        assert result.total_stores == 100
