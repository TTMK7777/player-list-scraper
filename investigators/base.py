#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
調査モジュール基底クラス・データ型定義
======================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AlertLevel(Enum):
    """アラートレベル"""
    CRITICAL = "🔴 緊急"   # 撤退・統合
    WARNING = "🟡 警告"    # 名称変更
    INFO = "🟢 情報"       # URL変更・新規参入
    OK = "✅ 正常"         # 変更なし


class ChangeType(Enum):
    """変更タイプ"""
    WITHDRAWAL = "撤退"
    MERGER = "統合・買収"
    COMPANY_RENAME = "会社名変更"
    SERVICE_RENAME = "サービス名変更"
    URL_CHANGE = "URL変更"
    NEW_ENTRY = "新規参入"
    NO_CHANGE = "変更なし"


class ValidationStatus(Enum):
    """検証ステータス"""
    CONFIRMED = "確認済み"    # 高信頼度で変更を確認
    UNCHANGED = "変更なし"    # 高信頼度で変更なし
    UNCERTAIN = "要確認"      # 判断不能・情報不足 → 手動確認が必要
    ERROR = "エラー"          # API失敗・取得エラー


@dataclass
class ValidationResult:
    """
    正誤チェック結果

    【フィールド説明】
    - player_name_original: 入力Excelの元のプレイヤー名
    - player_name_current: 現在のプレイヤー名（変更があれば）
    - status: 検証ステータス
    - alert_level: アラートレベル
    - change_type: 変更タイプ
    - change_details: 具体的な変更点のリスト
    - url_original: 入力Excelの元のURL
    - url_current: 現在のURL（変更があれば）
    - company_name_original: 元の運営会社名
    - company_name_current: 現在の運営会社名
    - confidence: 信頼度 (0.0-1.0)
    - source_urls: 情報源URL
    - news_summary: 関連ニュース（撤退・統合等の重大情報）
    - checked_at: チェック実行日時
    - needs_manual_review: 手動確認が必要かどうか
    """
    player_name_original: str
    player_name_current: str
    status: ValidationStatus
    alert_level: AlertLevel
    change_type: ChangeType
    change_details: list[str] = field(default_factory=list)
    url_original: str = ""
    url_current: str = ""
    company_name_original: str = ""
    company_name_current: str = ""
    confidence: float = 0.0
    source_urls: list[str] = field(default_factory=list)
    news_summary: str = ""
    checked_at: datetime = field(default_factory=datetime.now)
    needs_manual_review: bool = False
    raw_response: str = ""  # LLMの生レスポンス（デバッグ用）

    @classmethod
    def create_unchanged(
        cls,
        player_name: str,
        url: str = "",
        company_name: str = "",
        confidence: float = 0.9,
        source_urls: list[str] = None,
    ) -> "ValidationResult":
        """変更なしの結果を作成"""
        return cls(
            player_name_original=player_name,
            player_name_current=player_name,
            status=ValidationStatus.UNCHANGED,
            alert_level=AlertLevel.OK,
            change_type=ChangeType.NO_CHANGE,
            url_original=url,
            url_current=url,
            company_name_original=company_name,
            company_name_current=company_name,
            confidence=confidence,
            source_urls=source_urls or [],
            needs_manual_review=False,
        )

    @classmethod
    def create_error(
        cls,
        player_name: str,
        url: str = "",
        error_message: str = "",
    ) -> "ValidationResult":
        """エラー結果を作成"""
        return cls(
            player_name_original=player_name,
            player_name_current=player_name,
            status=ValidationStatus.ERROR,
            alert_level=AlertLevel.INFO,
            change_type=ChangeType.NO_CHANGE,
            change_details=[f"エラー: {error_message}"],
            url_original=url,
            url_current=url,
            confidence=0.0,
            needs_manual_review=True,
        )

    @classmethod
    def create_uncertain(
        cls,
        player_name: str,
        url: str = "",
        reason: str = "",
    ) -> "ValidationResult":
        """要確認の結果を作成"""
        return cls(
            player_name_original=player_name,
            player_name_current=player_name,
            status=ValidationStatus.UNCERTAIN,
            alert_level=AlertLevel.WARNING,
            change_type=ChangeType.NO_CHANGE,
            change_details=[f"要確認: {reason}"] if reason else [],
            url_original=url,
            url_current=url,
            confidence=0.4,
            needs_manual_review=True,
        )

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "player_name_original": self.player_name_original,
            "player_name_current": self.player_name_current,
            "status": self.status.value,
            "alert_level": self.alert_level.value,
            "change_type": self.change_type.value,
            "change_details": self.change_details,
            "url_original": self.url_original,
            "url_current": self.url_current,
            "company_name_original": self.company_name_original,
            "company_name_current": self.company_name_current,
            "confidence": self.confidence,
            "source_urls": self.source_urls,
            "news_summary": self.news_summary,
            "checked_at": self.checked_at.isoformat() if self.checked_at else "",
            "needs_manual_review": self.needs_manual_review,
        }


def determine_alert_level(change_type: ChangeType) -> AlertLevel:
    """変更タイプからアラートレベルを決定"""
    mapping = {
        ChangeType.WITHDRAWAL: AlertLevel.CRITICAL,
        ChangeType.MERGER: AlertLevel.CRITICAL,
        ChangeType.COMPANY_RENAME: AlertLevel.WARNING,
        ChangeType.SERVICE_RENAME: AlertLevel.WARNING,
        ChangeType.URL_CHANGE: AlertLevel.INFO,
        ChangeType.NEW_ENTRY: AlertLevel.INFO,
        ChangeType.NO_CHANGE: AlertLevel.OK,
    }
    return mapping.get(change_type, AlertLevel.INFO)
