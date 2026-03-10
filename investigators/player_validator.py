#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プレイヤー正誤チェッカー
========================
既存のプレイヤーリストを読み込み、各プレイヤーの最新状態を自動チェック

【機能】
- サービス継続確認（撤退・終了していないか）
- サービス名変更の検出
- 運営会社名変更の検出
- 公式URL変更の検出
- 統合・買収情報の検出

【使用方法】
```python
from investigators import PlayerValidator
from core import ExcelHandler

# Excelからプレイヤーデータを読み込み
handler = ExcelHandler()
players = handler.load("プレイヤーリスト.xlsx")

# 正誤チェック実行
validator = PlayerValidator()
results = await validator.validate_batch(players)
```
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from .base import (
    AlertLevel,
    ChangeType,
    ValidationResult,
    ValidationStatus,
    determine_alert_level,
)

# 親ディレクトリのモジュールをインポート
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.async_helpers import optimal_concurrency
from core.llm_client import LLMClient, get_default_client, DEFAULT_MODEL
from core.excel_handler import PlayerData
from core.sanitizer import sanitize_input, verify_url
from core.safe_parse import safe_float
from core.llm_schemas import PlayerValidationLLMResponse, parse_llm_response


class PlayerValidator:
    """
    プレイヤー正誤チェッカー

    【チェック内容】
    1. サービスは現在も継続しているか（撤退・終了していないか）
    2. サービス名の変更はあるか
    3. 運営会社名の変更はあるか
    4. 公式URLは正しいか（リダイレクト・変更の有無）
    5. 統合・買収などの重大ニュースはあるか
    """

    # コスト概算用の単価（USD/API呼び出し）
    COST_PER_CALL = 0.015  # Gemini 2.5 Pro + 検索グラウンディング（1プレイヤーあたり概算）

    @staticmethod
    def estimate_cost(player_count: int) -> dict:
        """コスト概算を計算

        1プレイヤー = 1回のAPI呼び出し。

        Args:
            player_count: プレイヤー数

        Returns:
            {"call_count": int, "cost_per_call": float, "estimated_cost": float}
        """
        cost_per_call = PlayerValidator.COST_PER_CALL
        return {
            "call_count": player_count,
            "cost_per_call": cost_per_call,
            "estimated_cost": player_count * cost_per_call,
        }

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: str = DEFAULT_MODEL,
    ):
        """
        Args:
            llm_client: LLMクライアント（未指定時はデフォルトを使用）
            model: 使用するモデル
        """
        self.llm = llm_client or get_default_client()
        self.model = model

    async def validate_player(
        self,
        player_name: str,
        official_url: str = "",
        company_name: str = "",
        industry: Optional[str] = None,
        definition: str = "",
    ) -> ValidationResult:
        """
        単一プレイヤーの正誤チェック

        Args:
            player_name: プレイヤー名（サービス名）
            official_url: 公式URL
            company_name: 運営会社名
            industry: 業界（クレジットカード、動画配信など）

        Returns:
            ValidationResult: チェック結果
        """
        try:
            # Step 1: URLの有効性チェック（オプション）
            url_status = await self._check_url_status(official_url) if official_url else None

            # Step 2: LLMで最新情報を調査
            llm_response = await self._query_latest_info(
                player_name, official_url, company_name, industry, definition
            )

            # Step 3: レスポンスを解析
            result = self._parse_response(
                llm_response,
                player_name,
                official_url,
                company_name,
                url_status,
            )

            return result

        except Exception as e:
            return ValidationResult.create_error(
                player_name=player_name,
                url=official_url,
                error_message=str(e),
            )

    async def validate_batch(
        self,
        players: list[PlayerData],
        industry: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        concurrency: Optional[int] = None,
        delay_seconds: float = 1.0,
        definition: str = "",
    ) -> list[ValidationResult]:
        """
        複数プレイヤーをバッチチェック

        Args:
            players: PlayerData のリスト
            industry: 業界（全プレイヤー共通）
            on_progress: 進捗コールバック (current, total, player_name)
            concurrency: 同時実行数（None時は自動決定）
            delay_seconds: リクエスト間の遅延（秒）

        Returns:
            list[ValidationResult]: チェック結果のリスト
        """
        results = []
        total = len(players)

        # 並列数を自動決定（未指定時）
        if concurrency is None:
            concurrency = optimal_concurrency(total)

        # セマフォで同時実行数を制限
        semaphore = asyncio.Semaphore(concurrency)

        async def validate_with_semaphore(idx: int, player: PlayerData):
            async with semaphore:
                if on_progress:
                    on_progress(idx + 1, total, player.player_name)

                result = await self.validate_player(
                    player_name=player.player_name,
                    official_url=player.official_url,
                    company_name=player.company_name,
                    industry=industry,
                    definition=definition,
                )

            # API制限対策の遅延（セマフォ外）
            await asyncio.sleep(delay_seconds)
            return result

        # 並行実行
        tasks = [
            validate_with_semaphore(idx, player)
            for idx, player in enumerate(players)
        ]
        results = await asyncio.gather(*tasks)

        return list(results)

    async def _check_url_status(self, url: str) -> Optional[dict]:
        """
        URLの有効性をチェック

        共通ユーティリティ core.sanitizer.verify_url() に委譲。
        後方互換性のためメソッドとして残す。

        Returns:
            dict: {"status_code": int, "final_url": str, "is_redirect": bool}
        """
        if not url:
            return None
        return await verify_url(url)

    async def _query_latest_info(
        self,
        player_name: str,
        official_url: str,
        company_name: str,
        industry: Optional[str],
        definition: str = "",
    ) -> str:
        """LLMに最新情報を問い合わせ"""

        # 入力をサニタイズ（プロンプトインジェクション対策）
        safe_player_name = sanitize_input(player_name)
        safe_company_name = sanitize_input(company_name)
        safe_industry = sanitize_input(industry) if industry else ""
        safe_url = sanitize_input(official_url)

        industry_context = f"（{safe_industry}業界）" if safe_industry else ""
        definition_context = f"\n【業界定義・範囲】\n{sanitize_input(definition)}\n" if definition else ""
        company_context = f"（運営会社: {safe_company_name}）" if safe_company_name else ""
        url_context = f"[公式URL] {safe_url}" if safe_url else ""

        current_year = datetime.now().year

        prompt = f"""
「{safe_player_name}」{industry_context}{company_context}の最新情報を調査してください。
{definition_context}
{url_context}

【確認事項】
1. サービスは現在も継続していますか？（撤退・終了していないか）
2. サービス名の変更はありますか？（リブランディング等）
3. 運営会社名の変更はありますか？
4. 公式URLは正しいですか？（リダイレクト・変更の有無）
5. 統合・買収などの重大ニュースはありますか？（{current_year - 1}年1月以降）

【重要】
- {current_year}年時点の最新情報を優先してください
- {current_year - 2}年以前の統合・買収・社名変更は背景情報であり、change_type は現在の状態で判定してください
- 公式サイト、プレスリリース、信頼できるニュースソースのみを参照
- 推測や古い情報は避けてください

【出力形式】JSON（必ずこの形式で）
```json
{{
    "is_active": true,
    "change_type": "none",
    "current_service_name": "現在のサービス名",
    "current_company_name": "現在の運営会社名",
    "current_url": "現在の公式URL",
    "changes": ["変更点1", "変更点2"],
    "news": "関連ニュース（撤退・統合等の重大情報があれば）",
    "confidence": 0.9,
    "sources": ["情報源URL1", "情報源URL2"]
}}
```

【change_type の値】
- "none": 変更なし
- "withdrawal": サービス終了・撤退
- "merger": 統合・買収
- "company_rename": 運営会社名の変更
- "service_rename": サービス名の変更（リブランディング）
- "url_change": URLのみ変更

【正しい判定の例】
例1: サービスが継続中で変更なし
{{"is_active": true, "change_type": "none", "confidence": 0.95, "changes": []}}

例2: サービスが終了している場合
{{"is_active": false, "change_type": "withdrawal", "confidence": 0.9, "changes": ["2025年3月にサービス終了"]}}

例3: 運営会社名が変更された場合
{{"is_active": true, "change_type": "company_rename", "confidence": 0.85, "changes": ["旧社名→新社名に変更"]}}
"""

        # LLM呼び出し（同期を非同期でラップ、事実確認系は temperature=0.1 統一）
        response = await asyncio.to_thread(
            lambda: self.llm.call(prompt, model=self.model, use_search=True, temperature=0.1)
        )
        return response

    def _parse_response(
        self,
        response: str,
        player_name: str,
        original_url: str,
        original_company: str,
        url_status: Optional[dict],
    ) -> ValidationResult:
        """LLMのレスポンスを解析してValidationResultを生成

        pydantic スキーマでバリデーション→正規化した後、ValidationResult に変換。
        """

        # JSONを抽出
        data = self.llm.extract_json(response)

        if not data or not isinstance(data, dict):
            logger.warning(
                "[%s] JSON抽出失敗 — extract_json returned %s\n"
                "--- raw_response start ---\n%s\n--- raw_response end ---",
                player_name,
                type(data).__name__ if data is not None else "None",
                response[:2000] if response else "(empty)",
            )
            return ValidationResult.create_uncertain(
                player_name=player_name,
                url=original_url,
                reason="LLMからの応答を解析できませんでした",
            )

        # pydantic でバリデーション + 正規化
        parsed = parse_llm_response(data, PlayerValidationLLMResponse)
        if parsed is None:
            logger.warning(
                "[%s] pydanticバリデーション失敗 — extracted data: %s",
                player_name,
                json.dumps(data, ensure_ascii=False, default=str)[:1000],
            )
            return ValidationResult.create_uncertain(
                player_name=player_name,
                url=original_url,
                reason="LLMレスポンスのバリデーションに失敗しました",
            )

        # 変更タイプを判定
        change_type_map = {
            "none": ChangeType.NO_CHANGE,
            "withdrawal": ChangeType.WITHDRAWAL,
            "merger": ChangeType.MERGER,
            "company_rename": ChangeType.COMPANY_RENAME,
            "service_rename": ChangeType.SERVICE_RENAME,
            "url_change": ChangeType.URL_CHANGE,
        }
        change_type = change_type_map.get(parsed.change_type, ChangeType.NO_CHANGE)

        # アラートレベルを決定
        alert_level = determine_alert_level(change_type)

        # ステータスを決定
        confidence = parsed.confidence

        if not parsed.is_active:
            status = ValidationStatus.CONFIRMED
            change_type = ChangeType.WITHDRAWAL
            alert_level = AlertLevel.CRITICAL
        elif confidence < ValidationResult.CONFIDENCE_THRESHOLD:
            status = ValidationStatus.UNCERTAIN
        elif change_type == ChangeType.NO_CHANGE:
            status = ValidationStatus.UNCHANGED
        else:
            status = ValidationStatus.CONFIRMED

        # 変更内容（pydantic で既にリスト化済み）
        changes = list(parsed.changes)

        # URLの状態をチェック
        current_url = parsed.current_url or original_url
        if url_status and url_status.get("is_redirect"):
            if url_status["final_url"] != original_url:
                if change_type != ChangeType.URL_CHANGE:
                    changes.append(f"URLリダイレクト検出: {original_url} → {url_status['final_url']}")

        return ValidationResult(
            player_name_original=player_name,
            player_name_current=parsed.current_service_name or player_name,
            status=status,
            alert_level=alert_level,
            change_type=change_type,
            change_details=changes,
            url_original=original_url,
            url_current=current_url,
            company_name_original=original_company,
            company_name_current=parsed.current_company_name or original_company,
            source_urls=parsed.sources,
            news_summary=parsed.news,
            checked_at=datetime.now(),
            needs_manual_review=ValidationResult.should_need_manual_review(status, confidence),
            raw_response=response,
        )


# =============================================================================
# CLI
# =============================================================================
async def main():
    """CLI エントリーポイント"""
    import argparse

    parser = argparse.ArgumentParser(description="プレイヤー正誤チェッカー")
    parser.add_argument("excel_file", help="チェック対象のExcelファイル")
    parser.add_argument("--industry", "-i", default="", help="業界名（例: クレジットカード）")
    parser.add_argument("--output", "-o", help="出力Excelファイル")
    parser.add_argument("--limit", "-l", type=int, help="チェック件数の上限")

    args = parser.parse_args()

    print(f"\n[SEARCH] プレイヤー正誤チェッカー")
    print(f"入力: {args.excel_file}")
    print()

    # Excelを読み込み
    from core.excel_handler import ExcelHandler
    handler = ExcelHandler()
    players = handler.load(args.excel_file)

    if args.limit:
        players = players[:args.limit]

    print(f"[INFO] プレイヤー数: {len(players)}件")
    print()

    # バリデーション実行
    validator = PlayerValidator()

    def on_progress(current: int, total: int, name: str):
        print(f"[{current}/{total}] チェック中: {name}")

    results = await validator.validate_batch(
        players,
        industry=args.industry,
        on_progress=on_progress,
    )

    # 結果サマリー
    print()
    print("=" * 50)
    print("[RESULT] チェック結果サマリー")
    print("=" * 50)

    alert_counts = {}
    for result in results:
        level = result.alert_level.value
        alert_counts[level] = alert_counts.get(level, 0) + 1

    for level, count in sorted(alert_counts.items()):
        print(f"  {level}: {count}件")

    # 問題のあるプレイヤーを表示
    print()
    print("[WARN] 変更・問題があるプレイヤー:")
    for result in results:
        if result.alert_level != AlertLevel.OK:
            print(f"  {result.alert_level.value} {result.player_name_original}")
            if result.change_details:
                for detail in result.change_details:
                    print(f"      → {detail}")

    # Excel出力
    if args.output:
        from core.excel_handler import ValidationReportExporter
        exporter = ValidationReportExporter()
        output_path = exporter.export(results, args.output)
        print()
        print(f"[SAVE] 結果を保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
