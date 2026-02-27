#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
調査モジュール基底クラス・データ型定義
======================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


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
    source_urls: list[str] = field(default_factory=list)
    news_summary: str = ""
    checked_at: datetime = field(default_factory=datetime.now)
    needs_manual_review: bool = False
    raw_response: str = ""  # LLMの生レスポンス（デバッグ用）

    # 手動確認判定の信頼度閾値（should_need_manual_review のデフォルト）
    CONFIDENCE_THRESHOLD = 0.6

    @staticmethod
    def should_need_manual_review(
        status: "ValidationStatus",
        confidence: float,
        threshold: float = 0.6,
    ) -> bool:
        """正誤チェック結果に手動確認が必要か判定

        Args:
            status: 検証ステータス
            confidence: LLMレスポンスの信頼度 (0.0〜1.0)
            threshold: 信頼度閾値（これ以下は要確認）

        Returns:
            True = 手動確認が必要
        """
        return status == ValidationStatus.UNCERTAIN or confidence < threshold

    @classmethod
    def create_unchanged(
        cls,
        player_name: str,
        url: str = "",
        company_name: str = "",
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


@dataclass
class StoreInvestigationResult:
    """
    店舗調査結果

    【フィールド説明】
    - company_name: 調査対象の企業名
    - total_stores: 店舗総数
    - direct_stores: 直営店数（判別可能な場合）
    - franchise_stores: FC店数（判別可能な場合）
    - prefecture_distribution: 都道府県別店舗分布 {"東京都": 10, ...}
    - source_urls: 情報源URL（必須 - 検証用）
    - investigation_date: 調査実行日時
    - investigation_mode: 調査モード ("ai" / "scraping" / "hybrid")
    - notes: 補足情報
    - needs_verification: 手動確認が必要かどうか
    - raw_response: LLMの生レスポンス（デバッグ用）
    """
    company_name: str
    total_stores: int
    source_urls: list[str]  # 必須（検証用）
    investigation_date: datetime
    investigation_mode: str  # "ai" / "scraping" / "hybrid"
    direct_stores: Optional[int] = None
    franchise_stores: Optional[int] = None
    prefecture_distribution: Optional[dict[str, int]] = None
    notes: str = ""
    needs_verification: bool = False
    raw_response: str = ""

    @staticmethod
    def should_need_verification(
        total_stores: int,
        confidence: float,
        threshold: float = 0.7,
    ) -> bool:
        """店舗調査結果に手動確認が必要か判定

        Args:
            total_stores: 調査された店舗総数
            confidence: LLMレスポンスの信頼度 (0.0〜1.0)
            threshold: 信頼度閾値（これ以下は要確認）

        Returns:
            True = 手動確認が必要
        """
        return confidence < threshold or total_stores == 0

    @property
    def is_confident(self) -> bool:
        """AI調査結果を採用してよいか（ハイブリッドモード用）

        needs_verification=False かつ total_stores>0 であれば信頼できる。
        """
        return not self.needs_verification and self.total_stores > 0

    @classmethod
    def create_success(
        cls,
        company_name: str,
        total_stores: int,
        source_urls: list[str],
        investigation_mode: str,
        direct_stores: Optional[int] = None,
        franchise_stores: Optional[int] = None,
        prefecture_distribution: Optional[dict[str, int]] = None,
        notes: str = "",
    ) -> "StoreInvestigationResult":
        """成功した調査結果を作成"""
        return cls(
            company_name=company_name,
            total_stores=total_stores,
            source_urls=source_urls,
            investigation_date=datetime.now(),
            investigation_mode=investigation_mode,
            direct_stores=direct_stores,
            franchise_stores=franchise_stores,
            prefecture_distribution=prefecture_distribution,
            notes=notes,
            needs_verification=False,
        )

    @classmethod
    def create_uncertain(
        cls,
        company_name: str,
        investigation_mode: str,
        reason: str = "",
        source_urls: Optional[list[str]] = None,
        raw_response: str = "",
    ) -> "StoreInvestigationResult":
        """要確認の調査結果を作成"""
        return cls(
            company_name=company_name,
            total_stores=0,
            source_urls=source_urls or [],
            investigation_date=datetime.now(),
            investigation_mode=investigation_mode,
            notes=f"要確認: {reason}" if reason else "要確認",
            needs_verification=True,
            raw_response=raw_response,
        )

    @classmethod
    def create_error(
        cls,
        company_name: str,
        investigation_mode: str,
        error_message: str = "",
    ) -> "StoreInvestigationResult":
        """エラー結果を作成"""
        return cls(
            company_name=company_name,
            total_stores=0,
            source_urls=[],
            investigation_date=datetime.now(),
            investigation_mode=investigation_mode,
            notes=f"エラー: {error_message}",
            needs_verification=True,
        )

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "company_name": self.company_name,
            "total_stores": self.total_stores,
            "direct_stores": self.direct_stores,
            "franchise_stores": self.franchise_stores,
            "prefecture_distribution": self.prefecture_distribution,
            "source_urls": self.source_urls,
            "investigation_date": self.investigation_date.isoformat() if self.investigation_date else "",
            "investigation_mode": self.investigation_mode,
            "notes": self.notes,
            "needs_verification": self.needs_verification,
        }


@dataclass
class AttributeInvestigationResult:
    """
    属性調査結果（カテゴリ/ブランド共通）

    【フィールド説明】
    - player_name: 調査対象のプレイヤー名
    - attribute_matrix: 属性名 → True/False/None (○/×/?) のマッピング
    - source_urls: 情報源URL
    - investigation_date: 調査実行日時
    - needs_verification: 手動確認が必要かどうか
    - raw_response: LLMの生レスポンス（デバッグ用）
    """
    player_name: str
    attribute_matrix: dict[str, Optional[bool]]  # 属性名 → ○(True)/×(False)/?(None)
    source_urls: list[str] = field(default_factory=list)
    investigation_date: datetime = field(default_factory=datetime.now)
    needs_verification: bool = False
    raw_response: str = ""

    @classmethod
    def create_success(
        cls,
        player_name: str,
        attribute_matrix: dict[str, Optional[bool]],
        source_urls: Optional[list[str]] = None,
    ) -> "AttributeInvestigationResult":
        """成功した調査結果を作成"""
        return cls(
            player_name=player_name,
            attribute_matrix=attribute_matrix,
            source_urls=source_urls or [],
            investigation_date=datetime.now(),
            needs_verification=False,
        )

    @classmethod
    def create_uncertain(
        cls,
        player_name: str,
        attribute_matrix: Optional[dict[str, Optional[bool]]] = None,
        reason: str = "",
        raw_response: str = "",
    ) -> "AttributeInvestigationResult":
        """要確認の調査結果を作成"""
        return cls(
            player_name=player_name,
            attribute_matrix=attribute_matrix or {},
            source_urls=[],
            investigation_date=datetime.now(),
            needs_verification=True,
            raw_response=raw_response,
        )

    @classmethod
    def create_error(
        cls,
        player_name: str,
        error_message: str = "",
    ) -> "AttributeInvestigationResult":
        """エラー結果を作成"""
        return cls(
            player_name=player_name,
            attribute_matrix={},
            source_urls=[],
            investigation_date=datetime.now(),
            needs_verification=True,
            raw_response=f"エラー: {error_message}",
        )

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "player_name": self.player_name,
            "attribute_matrix": self.attribute_matrix,
            "source_urls": self.source_urls,
            "investigation_date": self.investigation_date.isoformat() if self.investigation_date else "",
            "needs_verification": self.needs_verification,
        }


@dataclass
class GeneratedPlayer:
    """
    0ベース生成プレイヤー候補

    【フィールド説明】
    - player_name: プレイヤー名
    - official_url: 公式サイトURL
    - company_name: 運営会社名
    - source_urls: 情報源URL
    - reason: リストに含める理由
    - url_verified: URL存在確認済みか
    - category: 業界内カテゴリ（任意）
    """
    player_name: str
    official_url: str = ""
    company_name: str = ""
    source_urls: list[str] = field(default_factory=list)
    reason: str = ""
    url_verified: bool = False
    category: str = ""

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "player_name": self.player_name,
            "official_url": self.official_url,
            "company_name": self.company_name,
            "source_urls": self.source_urls,
            "reason": self.reason,
            "url_verified": self.url_verified,
            "category": self.category,
        }


@dataclass
class NewcomerCandidate:
    """
    新規参入プレイヤー候補

    【フィールド説明】
    - player_name: 候補プレイヤー名
    - official_url: 公式サイトURL
    - company_name: 運営会社名
    - entry_date_approx: 推定参入時期（"2025-06" 等）
    - source_urls: 情報源URL
    - reason: 新規参入と判断した理由
    - verification_status: 検証ステータス ("verified"/"unverified"/"url_error")
    - url_verified: URL存在確認済みか
    """
    player_name: str
    official_url: str = ""
    company_name: str = ""
    entry_date_approx: str = ""
    source_urls: list[str] = field(default_factory=list)
    reason: str = ""
    verification_status: str = "unverified"  # "verified" / "unverified" / "url_error"
    url_verified: bool = False

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "player_name": self.player_name,
            "official_url": self.official_url,
            "company_name": self.company_name,
            "entry_date_approx": self.entry_date_approx,
            "source_urls": self.source_urls,
            "reason": self.reason,
            "verification_status": self.verification_status,
            "url_verified": self.url_verified,
        }
