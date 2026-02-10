#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗調査モジュール v5.0
======================
AI調査をメインに、スクレイピングをオプションとして併存

【調査モード】
- AI: LLMによるWeb検索ベースの調査（推奨）
- SCRAPING: 従来のスクレイピング
- HYBRID: AI調査 → 低信頼度時にスクレイピング補完
"""

import asyncio
import re
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from investigators.base import StoreInvestigationResult
from core.async_helpers import optimal_concurrency
from core.sanitizer import sanitize_input
from core.safe_parse import safe_float


class InvestigationMode(Enum):
    """調査モード"""
    AI = "ai"              # デフォルト・推奨
    SCRAPING = "scraping"  # スクレイピングのみ
    HYBRID = "hybrid"      # AI優先、低信頼度時にスクレイピング補完


class StoreInvestigator:
    """
    店舗調査クラス

    【使用例】
    ```python
    investigator = StoreInvestigator()
    result = await investigator.investigate(
        company_name="スターバックス",
        official_url="https://www.starbucks.co.jp/",
        mode=InvestigationMode.AI
    )
    print(f"店舗数: {result.total_stores}")
    ```
    """

    CONFIDENCE_THRESHOLD = 0.7  # これ以下でHYBRID時はスクレイピング試行

    # 入力サニタイズ用の危険パターン
    DANGEROUS_PATTERNS = [
        r"ignore.*instructions?",
        r"forget.*instructions?",
        r"system.*prompt",
        r"<\|.*\|>",
        r"\{\{.*\}\}",
        r"```.*system",
    ]

    def __init__(
        self,
        llm_client=None,
        model: str = "sonar-pro",
    ):
        """
        Args:
            llm_client: LLMクライアント（未指定時は自動作成）
            model: 使用するLLMモデル
        """
        self.llm = llm_client
        self.model = model
        self._scraper = None  # 遅延初期化

    def _get_llm_client(self):
        """LLMクライアントを取得（遅延初期化、キャッシュ有効）"""
        if self.llm is None:
            from core.llm_client import LLMClient
            # 店舗調査は短時間で変わらないのでキャッシュ有効
            self.llm = LLMClient(enable_cache=True)
        return self.llm

    def _get_scraper(self):
        """スクレイパーを取得（遅延初期化）"""
        if self._scraper is None:
            try:
                from store_scraper_v3 import MultiStrategyScraper
                self._scraper = MultiStrategyScraper()
            except Exception as e:
                raise RuntimeError(f"スクレイパーの初期化に失敗: {e}")
        return self._scraper

    def _sanitize_input(self, text: str) -> str:
        """
        入力をサニタイズ（プロンプトインジェクション対策）
        ※ 共通サニタイザー core.sanitizer.sanitize_input() に委譲
        """
        return sanitize_input(text)

    async def investigate(
        self,
        company_name: str,
        official_url: str = "",
        industry: str = "",
        mode: InvestigationMode = InvestigationMode.AI,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> StoreInvestigationResult:
        """
        店舗調査を実行

        Args:
            company_name: 調査対象の企業名
            official_url: 公式サイトURL（オプション）
            industry: 業界（オプション、調査精度向上用）
            mode: 調査モード（AI / SCRAPING / HYBRID）
            on_progress: 進捗コールバック

        Returns:
            StoreInvestigationResult: 調査結果
        """
        def log(msg: str):
            if on_progress:
                on_progress(msg)

        # 入力サニタイズ
        company_name = self._sanitize_input(company_name)
        official_url = self._sanitize_input(official_url)
        industry = self._sanitize_input(industry)

        if not company_name:
            return StoreInvestigationResult.create_error(
                company_name="",
                investigation_mode=mode.value,
                error_message="企業名が指定されていません"
            )

        log(f"[{mode.value.upper()}] {company_name} の店舗調査を開始...")

        try:
            if mode == InvestigationMode.AI:
                return await self._investigate_ai(
                    company_name, official_url, industry, log
                )

            elif mode == InvestigationMode.SCRAPING:
                return await self._investigate_scraping(
                    company_name, official_url, log
                )

            elif mode == InvestigationMode.HYBRID:
                return await self._investigate_hybrid(
                    company_name, official_url, industry, log
                )

            else:
                return StoreInvestigationResult.create_error(
                    company_name=company_name,
                    investigation_mode=mode.value,
                    error_message=f"不明な調査モード: {mode}"
                )

        except Exception as e:
            log(f"エラー: {str(e)}")
            return StoreInvestigationResult.create_error(
                company_name=company_name,
                investigation_mode=mode.value,
                error_message=str(e)
            )

    async def _investigate_ai(
        self,
        company_name: str,
        official_url: str,
        industry: str,
        log: Callable[[str], None],
    ) -> StoreInvestigationResult:
        """AI（LLM）による店舗調査"""
        log("AI調査を実行中...")

        llm = self._get_llm_client()
        current_year = datetime.now().year

        # プロンプト生成
        prompt = self._build_ai_prompt(company_name, official_url, industry, current_year)

        try:
            # LLM呼び出し
            response = llm.call(prompt, model=self.model)
            log("LLMレスポンスを解析中...")

            # レスポンス解析
            result = self._parse_ai_response(company_name, response)
            log(f"調査完了: {result.total_stores}店舗, 信頼度{result.confidence*100:.0f}%")

            return result

        except Exception as e:
            log(f"AI調査エラー: {e}")
            return StoreInvestigationResult.create_error(
                company_name=company_name,
                investigation_mode="ai",
                error_message=str(e)
            )

    # 47都道府県リスト（プロンプト用）
    PREFECTURES = [
        "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
        "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
        "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
        "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
        "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
        "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
        "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
    ]

    def _build_ai_prompt(
        self,
        company_name: str,
        official_url: str,
        industry: str,
        current_year: int,
    ) -> str:
        """AI調査用プロンプトを生成（v5.1 精度向上版）"""
        url_hint = f"\n【公式サイト】{official_url}" if official_url else ""
        industry_hint = f"\n【業界】{industry}" if industry else ""

        # 都道府県リストをJSON形式で生成
        pref_template = ", ".join([f'"{p}": true/false/null' for p in self.PREFECTURES[:5]])

        return f"""
「{company_name}」の店舗展開状況を調査してください。
{url_hint}{industry_hint}

【最重要】以下の手順で調査してください:
1. まず「{company_name} 店舗一覧」「{company_name} 店舗検索」で検索
2. 公式サイトの店舗一覧/店舗検索ページを特定（URLを記録）
3. 店舗一覧から各都道府県への展開有無を確認

【都道府県の判定ルール】（厳格に適用）
- 店舗一覧に該当都道府県の店舗が**1件でも**あれば → true
- 店舗一覧で確認し、該当都道府県に**店舗がなければ** → false
- 店舗一覧ページ自体が**見つからない/アクセスできない場合のみ** → null

【重要な注意】
- 「不明だから null」ではなく「店舗一覧を確認した結果」で判断すること
- 店舗一覧が存在するなら、全都道府県を true/false で判定可能
- 店舗一覧ページのURLは必ず store_list_url と sources に含める
- {current_year}年以降の最新情報を優先

【出力形式】JSON
```json
{{
    "total_stores": 123,
    "direct_stores": 100,
    "franchise_stores": 23,
    "store_list_url": "https://example.com/stores/",
    "prefecture_presence": {{
        {pref_template}, ...（全47都道府県）
    }},
    "confidence": 0.85,
    "sources": ["https://..."],
    "notes": "補足情報（任意）"
}}
```

**重要**:
- prefecture_presence は「店舗数」ではなく「店舗があるかどうか」を true/false/null で回答
- store_list_url は店舗一覧/店舗検索ページのURLを必ず記載（見つからない場合は null）
- 全47都道府県について回答: {', '.join(self.PREFECTURES)}
"""

    def _parse_ai_response(
        self,
        company_name: str,
        response: str,
    ) -> StoreInvestigationResult:
        """AIレスポンスを解析"""
        import json

        # JSONを抽出
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group()
            else:
                return StoreInvestigationResult.create_uncertain(
                    company_name=company_name,
                    investigation_mode="ai",
                    reason="JSONを抽出できませんでした",
                    raw_response=response,
                )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return StoreInvestigationResult.create_uncertain(
                company_name=company_name,
                investigation_mode="ai",
                reason=f"JSON解析エラー: {e}",
                raw_response=response,
            )

        # データ抽出
        total_stores = data.get("total_stores", 0)
        if isinstance(total_stores, str):
            # "約100店舗" のような文字列を数値に変換
            match = re.search(r'\d+', total_stores)
            total_stores = int(match.group()) if match else 0

        direct_stores = data.get("direct_stores")
        franchise_stores = data.get("franchise_stores")

        # 店舗一覧ページURL（v5.1で追加）
        store_list_url = data.get("store_list_url")

        # 都道府県データ（新形式: prefecture_presence / 旧形式: prefecture_distribution）
        prefecture_presence = data.get("prefecture_presence") or data.get("prefecture_distribution")

        # 都道府県別有無データを正規化
        prefecture_distribution = None
        if isinstance(prefecture_presence, dict):
            prefecture_distribution = {}
            for pref in self.PREFECTURES:
                value = prefecture_presence.get(pref)
                if value is True:
                    prefecture_distribution[pref] = True
                elif value is False:
                    prefecture_distribution[pref] = False
                elif isinstance(value, int) and value > 0:
                    # 旧形式（数値）の場合は true に変換
                    prefecture_distribution[pref] = True
                elif isinstance(value, int) and value == 0:
                    prefecture_distribution[pref] = False
                else:
                    prefecture_distribution[pref] = None  # 不明

        confidence = safe_float(data.get("confidence"), default=0.5)
        sources = data.get("sources", [])
        notes = data.get("notes", "")

        # ソースURLの妥当性チェック
        if not isinstance(sources, list):
            sources = [sources] if sources else []
        sources = [s for s in sources if isinstance(s, str) and s.startswith("http")]

        # store_list_url をソースURLに追加（重複を避ける）
        if store_list_url and isinstance(store_list_url, str) and store_list_url.startswith("http"):
            if store_list_url not in sources:
                sources.insert(0, store_list_url)  # 先頭に追加

        # 要確認フラグ
        needs_verification = confidence < self.CONFIDENCE_THRESHOLD or total_stores == 0

        return StoreInvestigationResult(
            company_name=company_name,
            total_stores=total_stores,
            confidence=confidence,
            source_urls=sources,
            investigation_date=datetime.now(),
            investigation_mode="ai",
            direct_stores=direct_stores if isinstance(direct_stores, int) else None,
            franchise_stores=franchise_stores if isinstance(franchise_stores, int) else None,
            prefecture_distribution=prefecture_distribution if isinstance(prefecture_distribution, dict) else None,
            notes=notes,
            needs_verification=needs_verification,
            raw_response=response,
        )

    async def _investigate_scraping(
        self,
        company_name: str,
        official_url: str,
        log: Callable[[str], None],
    ) -> StoreInvestigationResult:
        """スクレイピングによる店舗調査"""
        log("スクレイピング調査を実行中...")

        if not official_url:
            return StoreInvestigationResult.create_error(
                company_name=company_name,
                investigation_mode="scraping",
                error_message="スクレイピングには公式URLが必要です"
            )

        try:
            scraper = self._get_scraper()

            # スクレイピング実行
            result = await scraper.scrape(
                company_name,
                official_url,
                on_progress=log
            )

            # 店舗数集計
            total_stores = len(result.stores)

            # 都道府県別集計
            pref_dist = {}
            for store in result.stores:
                pref = store.prefecture
                if pref:
                    pref_dist[pref] = pref_dist.get(pref, 0) + 1

            # ソースURL（スクレイピング元）
            source_urls = [official_url]
            if result.stores:
                # 最初の店舗URLを追加
                for store in result.stores[:3]:
                    if store.url and store.url not in source_urls:
                        source_urls.append(store.url)

            confidence = 0.9 if total_stores > 10 else 0.7 if total_stores > 0 else 0.3
            notes = f"戦略: {result.strategy_used}, 処理時間: {result.elapsed_time:.1f}秒"

            log(f"スクレイピング完了: {total_stores}店舗")

            return StoreInvestigationResult(
                company_name=company_name,
                total_stores=total_stores,
                confidence=confidence,
                source_urls=source_urls,
                investigation_date=datetime.now(),
                investigation_mode="scraping",
                prefecture_distribution=pref_dist if pref_dist else None,
                notes=notes,
                needs_verification=total_stores == 0,
            )

        except Exception as e:
            log(f"スクレイピングエラー: {e}")
            return StoreInvestigationResult.create_error(
                company_name=company_name,
                investigation_mode="scraping",
                error_message=str(e)
            )

    async def _investigate_hybrid(
        self,
        company_name: str,
        official_url: str,
        industry: str,
        log: Callable[[str], None],
    ) -> StoreInvestigationResult:
        """ハイブリッド調査（AI → スクレイピング補完）"""
        log("ハイブリッド調査を開始...")

        # Step 1: AI調査
        ai_result = await self._investigate_ai(
            company_name, official_url, industry, log
        )

        # Step 2: 信頼度チェック
        if ai_result.confidence >= self.CONFIDENCE_THRESHOLD:
            log(f"AI調査の信頼度が十分です（{ai_result.confidence*100:.0f}%）")
            ai_result = StoreInvestigationResult(
                company_name=ai_result.company_name,
                total_stores=ai_result.total_stores,
                confidence=ai_result.confidence,
                source_urls=ai_result.source_urls,
                investigation_date=ai_result.investigation_date,
                investigation_mode="hybrid",  # モードを更新
                direct_stores=ai_result.direct_stores,
                franchise_stores=ai_result.franchise_stores,
                prefecture_distribution=ai_result.prefecture_distribution,
                notes=ai_result.notes,
                needs_verification=ai_result.needs_verification,
                raw_response=ai_result.raw_response,
            )
            return ai_result

        # Step 3: スクレイピング補完
        if official_url:
            log(f"AI調査の信頼度が低いためスクレイピングで補完（{ai_result.confidence*100:.0f}%）...")

            scraping_result = await self._investigate_scraping(
                company_name, official_url, log
            )

            # スクレイピング成功
            if scraping_result.total_stores > 0:
                log(f"スクレイピングで {scraping_result.total_stores} 店舗を取得")

                # 結果をマージ
                merged_sources = list(set(ai_result.source_urls + scraping_result.source_urls))

                return StoreInvestigationResult(
                    company_name=company_name,
                    total_stores=scraping_result.total_stores,
                    confidence=max(ai_result.confidence, scraping_result.confidence),
                    source_urls=merged_sources,
                    investigation_date=datetime.now(),
                    investigation_mode="hybrid",
                    direct_stores=ai_result.direct_stores,
                    franchise_stores=ai_result.franchise_stores,
                    prefecture_distribution=scraping_result.prefecture_distribution or ai_result.prefecture_distribution,
                    notes=f"AI+スクレイピング併用. AI店舗数: {ai_result.total_stores}, スクレイピング店舗数: {scraping_result.total_stores}",
                    needs_verification=False,
                )

        # スクレイピング失敗またはURL未指定 → AI結果に要確認フラグ
        log("スクレイピング補完に失敗。AI結果に要確認フラグを設定")

        return StoreInvestigationResult(
            company_name=company_name,
            total_stores=ai_result.total_stores,
            confidence=ai_result.confidence,
            source_urls=ai_result.source_urls,
            investigation_date=datetime.now(),
            investigation_mode="hybrid",
            direct_stores=ai_result.direct_stores,
            franchise_stores=ai_result.franchise_stores,
            prefecture_distribution=ai_result.prefecture_distribution,
            notes=f"AI調査のみ（スクレイピング補完失敗）: {ai_result.notes}",
            needs_verification=True,
            raw_response=ai_result.raw_response,
        )

    async def investigate_batch(
        self,
        companies: list[dict],
        mode: InvestigationMode = InvestigationMode.AI,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        concurrency: Optional[int] = None,
        delay_seconds: float = 1.0,
    ) -> list[StoreInvestigationResult]:
        """
        複数企業の店舗調査をバッチ実行

        Args:
            companies: 調査対象リスト [{"company_name": "...", "official_url": "...", "industry": "..."}, ...]
            mode: 調査モード
            on_progress: 進捗コールバック (current, total, company_name)
            concurrency: 同時実行数（None時は自動決定）
            delay_seconds: リクエスト間隔（秒）

        Returns:
            list[StoreInvestigationResult]: 調査結果リスト
        """
        results = []
        total = len(companies)

        # 並列数を自動決定（未指定時）
        if concurrency is None:
            concurrency = optimal_concurrency(total)

        # セマフォで同時実行数を制限
        semaphore = asyncio.Semaphore(concurrency)

        async def investigate_one(idx: int, company: dict) -> StoreInvestigationResult:
            async with semaphore:
                company_name = company.get("company_name", "")

                if on_progress:
                    on_progress(idx + 1, total, company_name)

                result = await self.investigate(
                    company_name=company_name,
                    official_url=company.get("official_url", ""),
                    industry=company.get("industry", ""),
                    mode=mode,
                )

                await asyncio.sleep(delay_seconds)
                return result

        # 並行実行
        tasks = [investigate_one(i, c) for i, c in enumerate(companies)]
        results = await asyncio.gather(*tasks)

        return list(results)
