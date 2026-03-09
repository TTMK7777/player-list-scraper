#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLMレスポンス pydantic スキーマ
================================
LLMの出力JSONを安全にパース・正規化するためのスキーマ定義。
既存の dataclass (base.py) はそのまま維持し、LLMレスポンス→dataclass の
変換パイプラインの中間層として使用する。

【パイプライン】
LLM JSON文字列 → llm.extract_json() → dict → pydantic.model_validate() → pydanticモデル → 既存dataclass
フォールバック: ValidationError → create_uncertain() / create_error()
"""

import logging
from typing import Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.safe_parse import safe_float

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ====================================
# PlayerValidator 用スキーマ
# ====================================
class PlayerValidationLLMResponse(BaseModel):
    """正誤チェック LLMレスポンススキーマ"""

    model_config = ConfigDict(extra="ignore")  # LLMの余分なフィールドを無視

    is_active: bool = True
    change_type: str = "none"
    current_service_name: Optional[str] = None
    current_company_name: Optional[str] = None
    current_url: Optional[str] = None
    changes: list[str] = Field(default_factory=list)
    news: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)

    @field_validator("news", mode="before")
    @classmethod
    def normalize_news(cls, v):
        """news がリストの場合は文字列に変換"""
        if isinstance(v, list):
            return " / ".join(str(item) for item in v)
        return v or ""

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        """信頼度を安全に float に変換"""
        return safe_float(v, default=0.5)

    @field_validator("changes", "sources", mode="before")
    @classmethod
    def coerce_to_list(cls, v):
        """文字列の場合はリストに変換"""
        if isinstance(v, str):
            return [v] if v else []
        return v or []


# ====================================
# StoreInvestigator 用スキーマ
# ====================================
class StoreInvestigationLLMResponse(BaseModel):
    """店舗調査 LLMレスポンススキーマ"""

    model_config = ConfigDict(extra="ignore")

    total_stores: int = 0
    direct_stores: Optional[int] = None
    franchise_stores: Optional[int] = None
    store_list_url: Optional[str] = None
    prefecture_presence: Optional[dict] = None
    prefecture_distribution: Optional[dict] = None  # 旧形式フォールバック
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("total_stores", mode="before")
    @classmethod
    def coerce_total_stores(cls, v):
        """'約100店舗' のような文字列を数値に変換"""
        if isinstance(v, str):
            import re
            match = re.search(r'\d+', v)
            return int(match.group()) if match else 0
        try:
            return int(v) if v is not None else 0
        except (ValueError, TypeError):
            return 0

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        return safe_float(v, default=0.5)

    @field_validator("sources", mode="before")
    @classmethod
    def coerce_sources(cls, v):
        if isinstance(v, str):
            return [v] if v else []
        return v or []


# ====================================
# AttributeInvestigator 用スキーマ
# ====================================
class AttributeItemLLMResponse(BaseModel):
    """属性調査 1プレイヤー分のLLMレスポンス"""

    model_config = ConfigDict(extra="ignore")

    player_name: str = ""
    # Any型を使用: LLMは "yes"/1 等の非正規値を返すことがある。
    # True/False/None への正規化は _parse_batch_response で行う。
    attributes: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    reasoning: dict[str, str] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        return safe_float(v, default=0.5)

    @field_validator("sources", mode="before")
    @classmethod
    def coerce_sources(cls, v):
        if isinstance(v, str):
            return [v] if v else []
        return v or []

    @field_validator("reasoning", mode="before")
    @classmethod
    def coerce_reasoning(cls, v):
        """reasoning を dict に強制変換。非dict(NoneやList) → 空dict"""
        if not isinstance(v, dict):
            return {}
        return v


class AttributeBatchLLMResponse(BaseModel):
    """属性調査バッチ LLMレスポンススキーマ"""

    model_config = ConfigDict(extra="ignore")

    results: list[AttributeItemLLMResponse] = Field(default_factory=list)


# ====================================
# NewcomerDetector 用スキーマ
# ====================================
class NewcomerCandidateLLMResponse(BaseModel):
    """新規参入候補 LLMレスポンススキーマ"""

    model_config = ConfigDict(extra="ignore")

    player_name: str = ""
    official_url: str = ""
    company_name: str = ""
    entry_date_approx: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_urls: list[str] = Field(default_factory=list)
    reason: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        return safe_float(v, default=0.5)

    @field_validator("source_urls", mode="before")
    @classmethod
    def coerce_source_urls(cls, v):
        if isinstance(v, str):
            return [v] if v else []
        return v or []


# ====================================
# ユーティリティ
# ====================================
def parse_llm_response(raw: dict, schema: type[T]) -> Optional[T]:
    """LLMレスポンス dict を pydantic モデルに安全に変換

    Args:
        raw: LLM から抽出した dict
        schema: 変換先の pydantic モデルクラス

    Returns:
        変換されたモデル、または ValidationError 時は None
    """
    try:
        return schema.model_validate(raw)
    except Exception as e:
        logger.warning(f"LLMレスポンスのパースに失敗: {type(e).__name__}: {e}")
        return None
