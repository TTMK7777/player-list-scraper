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
import re
from datetime import datetime
from typing import Callable, Optional

import requests

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

from core.llm_client import LLMClient, get_default_client
from core.excel_handler import PlayerData


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

    # 信頼度の閾値
    CONFIDENCE_THRESHOLD = 0.6  # これ以下は「要確認」

    def __init__(
        self,
        llm_client: LLMClient = None,
        model: str = "sonar-pro",
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
        industry: str = "",
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
                player_name, official_url, company_name, industry
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
        industry: str = "",
        on_progress: Callable[[int, int, str], None] = None,
        concurrency: int = 3,
        delay_seconds: float = 1.0,
    ) -> list[ValidationResult]:
        """
        複数プレイヤーをバッチチェック

        Args:
            players: PlayerData のリスト
            industry: 業界（全プレイヤー共通）
            on_progress: 進捗コールバック (current, total, player_name)
            concurrency: 同時実行数
            delay_seconds: リクエスト間の遅延（秒）

        Returns:
            list[ValidationResult]: チェック結果のリスト
        """
        results = []
        total = len(players)

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
                )

                # API制限対策の遅延
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

        Returns:
            dict: {"status_code": int, "final_url": str, "is_redirect": bool}
        """
        if not url:
            return None

        try:
            response = await asyncio.to_thread(
                requests.head,
                url,
                timeout=10,
                allow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
            return {
                "status_code": response.status_code,
                "final_url": response.url,
                "is_redirect": len(response.history) > 0,
            }
        except Exception:
            return {"status_code": 0, "final_url": url, "is_redirect": False}

    async def _query_latest_info(
        self,
        player_name: str,
        official_url: str,
        company_name: str,
        industry: str,
    ) -> str:
        """LLMに最新情報を問い合わせ"""

        industry_context = f"（{industry}業界）" if industry else ""
        company_context = f"（運営会社: {company_name}）" if company_name else ""
        url_context = f"【公式URL】{official_url}" if official_url else ""

        prompt = f"""
「{player_name}」{industry_context}{company_context}の最新情報を調査してください。

{url_context}

【確認事項】
1. サービスは現在も継続していますか？（撤退・終了していないか）
2. サービス名の変更はありますか？（リブランディング等）
3. 運営会社名の変更はありますか？
4. 公式URLは正しいですか？（リダイレクト・変更の有無）
5. 統合・買収などの重大ニュースはありますか？（直近1-2年）

【重要】
- 2024年以降の最新情報を優先してください
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
"""

        # LLM呼び出し（同期を非同期でラップ）
        response = await asyncio.to_thread(
            self.llm.call,
            prompt,
            self.model,
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
        """LLMのレスポンスを解析してValidationResultを生成"""

        # JSONを抽出
        data = self.llm.extract_json(response)

        if not data or not isinstance(data, dict):
            return ValidationResult.create_uncertain(
                player_name=player_name,
                url=original_url,
                reason="LLMからの応答を解析できませんでした",
            )

        # 変更タイプを判定
        change_type_str = data.get("change_type", "none")
        change_type_map = {
            "none": ChangeType.NO_CHANGE,
            "withdrawal": ChangeType.WITHDRAWAL,
            "merger": ChangeType.MERGER,
            "company_rename": ChangeType.COMPANY_RENAME,
            "service_rename": ChangeType.SERVICE_RENAME,
            "url_change": ChangeType.URL_CHANGE,
        }
        change_type = change_type_map.get(change_type_str, ChangeType.NO_CHANGE)

        # アラートレベルを決定
        alert_level = determine_alert_level(change_type)

        # ステータスを決定
        confidence = float(data.get("confidence", 0.5))
        is_active = data.get("is_active", True)

        if not is_active:
            status = ValidationStatus.CONFIRMED
            change_type = ChangeType.WITHDRAWAL
            alert_level = AlertLevel.CRITICAL
        elif confidence < self.CONFIDENCE_THRESHOLD:
            status = ValidationStatus.UNCERTAIN
        elif change_type == ChangeType.NO_CHANGE:
            status = ValidationStatus.UNCHANGED
        else:
            status = ValidationStatus.CONFIRMED

        # 変更内容を取得
        changes = data.get("changes", [])
        if isinstance(changes, str):
            changes = [changes] if changes else []

        # URLの状態をチェック
        current_url = data.get("current_url", original_url) or original_url
        if url_status and url_status.get("is_redirect"):
            if url_status["final_url"] != original_url:
                if ChangeType.URL_CHANGE not in [change_type]:
                    changes.append(f"URLリダイレクト検出: {original_url} → {url_status['final_url']}")

        # ニュースサマリー
        news = data.get("news", "")
        if isinstance(news, list):
            news = " / ".join(news)

        # ソースURL
        sources = data.get("sources", [])
        if isinstance(sources, str):
            sources = [sources] if sources else []

        return ValidationResult(
            player_name_original=player_name,
            player_name_current=data.get("current_service_name", player_name) or player_name,
            status=status,
            alert_level=alert_level,
            change_type=change_type,
            change_details=changes,
            url_original=original_url,
            url_current=current_url,
            company_name_original=original_company,
            company_name_current=data.get("current_company_name", original_company) or original_company,
            confidence=confidence,
            source_urls=sources,
            news_summary=news,
            checked_at=datetime.now(),
            needs_manual_review=(status == ValidationStatus.UNCERTAIN or confidence < self.CONFIDENCE_THRESHOLD),
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

    print(f"\n🔍 プレイヤー正誤チェッカー")
    print(f"入力: {args.excel_file}")
    print()

    # Excelを読み込み
    from core.excel_handler import ExcelHandler
    handler = ExcelHandler()
    players = handler.load(args.excel_file)

    if args.limit:
        players = players[:args.limit]

    print(f"📋 プレイヤー数: {len(players)}件")
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
    print("📊 チェック結果サマリー")
    print("=" * 50)

    alert_counts = {}
    for result in results:
        level = result.alert_level.value
        alert_counts[level] = alert_counts.get(level, 0) + 1

    for level, count in sorted(alert_counts.items()):
        print(f"  {level}: {count}件")

    # 問題のあるプレイヤーを表示
    print()
    print("⚠️ 変更・問題があるプレイヤー:")
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
        print(f"💾 結果を保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
