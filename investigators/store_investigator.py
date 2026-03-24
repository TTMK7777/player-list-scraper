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
import logging
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
from core.llm_client import DEFAULT_MODEL
from core.llm_schemas import (
    BrandDiscoveryLLMResponse,
    StoreInvestigationLLMResponse,
    parse_llm_response,
)
from core.postal_prefecture import PREFECTURES


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

    # コスト概算用の単価（USD/API呼び出し）
    COST_PER_CALL = 0.02  # Gemini 2.5 Pro + 検索グラウンディング（1企業あたり概算）

    @staticmethod
    def estimate_cost(company_count: int, mode: str = "ai") -> dict:
        """コスト概算を計算

        1企業 = 1回のAPI呼び出し（AIモード）。
        スクレイピングモードはAPI呼び出しなし。

        Args:
            company_count: 企業数
            mode: 調査モード ("ai" / "scraping" / "hybrid")

        Returns:
            {"call_count": int, "cost_per_call": float, "estimated_cost": float, "mode": str}
        """
        if mode == "scraping":
            return {
                "call_count": 0,
                "cost_per_call": 0.0,
                "estimated_cost": 0.0,
                "mode": mode,
            }

        # hybrid はAI + 一部スクレイピング（最悪ケースはAIと同じ）
        cost_per_call = StoreInvestigator.COST_PER_CALL
        return {
            "call_count": company_count,
            "cost_per_call": cost_per_call,
            "estimated_cost": company_count * cost_per_call,
            "mode": mode,
        }

    def __init__(
        self,
        llm_client=None,
        model: str = DEFAULT_MODEL,
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

    async def investigate(
        self,
        company_name: str,
        official_url: str = "",
        industry: Optional[str] = None,
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
        company_name = sanitize_input(company_name)
        official_url = sanitize_input(official_url)
        industry = sanitize_input(industry) if industry else None

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
        industry: Optional[str],
        log: Callable[[str], None],
    ) -> StoreInvestigationResult:
        """AI（LLM）による店舗調査（2段階ブランド発見対応）"""
        log("AI調査を実行中...")

        llm = self._get_llm_client()
        current_year = datetime.now().year
        _already_retried_with_brands = False

        # プロンプト生成
        prompt = self._build_ai_prompt(company_name, official_url, industry, current_year)

        try:
            # LLM呼び出し（イベントループブロック防止）
            response = await asyncio.to_thread(
                lambda: llm.call(prompt, model=self.model, use_search=True, temperature=0.1)
            )
            log("LLMレスポンスを解析中...")

            # レスポンス解析
            result = self._parse_ai_response(company_name, response)
            log(f"調査完了: {result.total_stores}店舗")

            # 2段階ブランド発見: 0件 + 要確認の場合、ブランド特定→再調査
            if (
                result.total_stores == 0
                and result.needs_verification
                and not _already_retried_with_brands
            ):
                _already_retried_with_brands = True
                log("0件のためブランド発見フェーズを実行...")

                brand_list = await self._discover_brands(company_name, industry)

                if brand_list:
                    log(f"ブランド発見: {brand_list} → 再調査実行...")
                    prompt_retry = self._build_ai_prompt(
                        company_name, official_url, industry, current_year,
                        brands=brand_list,
                    )
                    response_retry = await asyncio.to_thread(
                        lambda: llm.call(
                            prompt_retry, model=self.model,
                            use_search=True, temperature=0.1,
                        )
                    )
                    log("再調査レスポンスを解析中...")
                    result = self._parse_ai_response(company_name, response_retry)
                    log(f"再調査完了: {result.total_stores}店舗")

            return result

        except Exception as e:
            log(f"AI調査エラー: {e}")
            return StoreInvestigationResult.create_error(
                company_name=company_name,
                investigation_mode="ai",
                error_message=str(e)
            )

    async def _discover_brands(
        self, company_name: str, industry: Optional[str] = None
    ) -> list[str]:
        """企業名から関連ブランド・サービス名を特定する専用LLMコール"""
        industry_hint = f"（業界: {industry}）" if industry else ""
        prompt = f"""
「{company_name}」{industry_hint}が運営する全てのブランド・サービス名・教室名・店舗ブランド名を列挙してください。

【重要】
- 企業名とブランド名が異なる場合がある（例: 企業「Z会」→「Z会教室」「Z会進学教室」）
- 複数のサービスブランドを展開している場合は全て列挙
- 既に終了したブランドは除外

【出力形式】JSON
```json
{{
    "brands": [
        {{"name": "ブランド名1", "type": "店舗/教室/サービス"}},
        {{"name": "ブランド名2", "type": "店舗/教室/サービス"}}
    ],
    "parent_company": "{company_name}",
    "notes": "補足（任意）"
}}
```
"""
        llm = self._get_llm_client()
        response = await asyncio.to_thread(
            lambda: llm.call(prompt, model=self.model, use_search=True, temperature=0.1)
        )

        try:
            data = llm.extract_json(response)
            if data and isinstance(data, dict):
                parsed = BrandDiscoveryLLMResponse(**data)
                return [b["name"] for b in parsed.brands if isinstance(b, dict) and "name" in b]
        except Exception as e:
            logging.getLogger(__name__).warning(
                "ブランド発見パース失敗 (%s): %s", company_name, e
            )

        return []

    def _build_ai_prompt(
        self,
        company_name: str,
        official_url: str,
        industry: Optional[str],
        current_year: int,
        brands: Optional[list[str]] = None,
    ) -> str:
        """AI調査用プロンプトを生成（v5.1 精度向上版）"""
        url_hint = f"\n【公式サイト】{official_url}" if official_url else ""
        industry_hint = f"\n【業界】{industry}" if industry else ""

        # ブランドリストが指定されている場合のヒント
        brands_hint = ""
        if brands:
            brand_lines = "\n".join(f"- {b}" for b in brands)
            brands_hint = f"""
【関連ブランド・サービス名】
以下のブランドそれぞれで「○○ 店舗一覧」「○○ 教室一覧」を検索してください:
{brand_lines}
"""

        # 都道府県リストをJSON形式で生成
        pref_template = ", ".join([f'"{p}": 数値/0/null' for p in PREFECTURES[:5]])

        return f"""
「{company_name}」の店舗・教室・拠点の展開状況を調査してください。
{url_hint}{industry_hint}

【最重要】以下の手順で調査してください:
1. まず「{company_name}」の関連ブランド・サービス名を特定
   （例: 企業名「Z会」→「Z会教室」「Z会進学教室」等）
2. 企業名+ブランド名それぞれで「○○ 店舗一覧」「○○ 教室一覧」を検索
3. 公式サイトの店舗/教室一覧ページを特定（URLを記録）
4. 各都道府県の概算店舗・教室数を確認
{brands_hint}
【ブランド展開の注意】
- 企業名とサービスブランド名が異なる場合がある
- 複数ブランド展開時は全ブランドの合計をカウント
- オンライン専業で物理拠点がない場合は total_stores: 0 が正しい

【都道府県の判定ルール】
- 店舗一覧から各都道府県の概算店舗・教室数を整数で回答（例: 25）
- 該当都道府県に店舗なしと確認 → 0
- 店舗一覧ページ自体が見つからない/アクセスできない場合のみ → null

【重要な注意】
- 「不明だから null」ではなく「店舗一覧を確認した結果」で判断すること
- 店舗一覧が存在するなら、全都道府県を数値/0 で判定可能
- 店舗一覧ページのURLは必ず store_list_url と sources に含める
- {current_year}年時点の最新店舗データを優先
- 閉店済み・統合済みの店舗は除外し、現在営業中のみカウント

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
- prefecture_presence は各都道府県の概算店舗・教室数を整数（0以上）または null で回答
- store_list_url は店舗一覧/店舗検索ページのURLを必ず記載（見つからない場合は null）
- 全47都道府県について回答: {', '.join(PREFECTURES)}
"""

    def _parse_ai_response(
        self,
        company_name: str,
        response: str,
    ) -> StoreInvestigationResult:
        """AIレスポンスを解析（pydantic スキーマでバリデーション）"""
        llm = self._get_llm_client()

        try:
            data = llm.extract_json(response)
        except Exception:
            data = None

        if data is None:
            return StoreInvestigationResult.create_uncertain(
                company_name=company_name,
                investigation_mode="ai",
                reason="JSONを抽出できませんでした",
                raw_response=response,
            )

        if not isinstance(data, dict):
            return StoreInvestigationResult.create_uncertain(
                company_name=company_name,
                investigation_mode="ai",
                reason="JSON解析結果がオブジェクトではありません",
                raw_response=response,
            )

        # pydantic でバリデーション + 正規化
        parsed = parse_llm_response(data, StoreInvestigationLLMResponse)
        if parsed is None:
            return StoreInvestigationResult.create_uncertain(
                company_name=company_name,
                investigation_mode="ai",
                reason="LLMレスポンスのバリデーションに失敗しました",
                raw_response=response,
            )

        # 都道府県データ（新形式: prefecture_presence / 旧形式: prefecture_distribution）
        prefecture_presence = parsed.prefecture_presence or parsed.prefecture_distribution

        # 都道府県別店舗数データを正規化（数値保持）
        # 注意: bool は int のサブクラスなので is True/False を先に判定
        prefecture_distribution = None
        if isinstance(prefecture_presence, dict):
            prefecture_distribution = {}
            for pref in PREFECTURES:
                value = prefecture_presence.get(pref)
                if value is True:
                    prefecture_distribution[pref] = 1  # 旧形式互換
                elif value is False:
                    prefecture_distribution[pref] = 0  # 旧形式互換
                elif isinstance(value, (int, float)) and value > 0:
                    prefecture_distribution[pref] = int(value)
                elif isinstance(value, (int, float)) and value == 0:
                    prefecture_distribution[pref] = 0
                else:
                    prefecture_distribution[pref] = None

        # ソースURLの妥当性チェック（pydantic で既にリスト化済み）
        sources = [s for s in parsed.sources if isinstance(s, str) and s.startswith("http")]

        # store_list_url をソースURLに追加（重複を避ける）
        store_list_url = parsed.store_list_url
        if store_list_url and isinstance(store_list_url, str) and store_list_url.startswith("http"):
            if store_list_url not in sources:
                sources.insert(0, store_list_url)

        # 要確認フラグ（判定ロジックは base.py に一元化）
        needs_verification = StoreInvestigationResult.should_need_verification(
            parsed.total_stores, parsed.confidence
        )

        return StoreInvestigationResult(
            company_name=company_name,
            total_stores=parsed.total_stores,
            source_urls=sources,
            investigation_date=datetime.now(),
            investigation_mode="ai",
            direct_stores=parsed.direct_stores if isinstance(parsed.direct_stores, int) else None,
            franchise_stores=parsed.franchise_stores if isinstance(parsed.franchise_stores, int) else None,
            prefecture_distribution=prefecture_distribution if isinstance(prefecture_distribution, dict) else None,
            notes=parsed.notes,
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

            notes = f"戦略: {result.strategy_used}, 処理時間: {result.elapsed_time:.1f}秒"

            log(f"スクレイピング完了: {total_stores}店舗")

            return StoreInvestigationResult(
                company_name=company_name,
                total_stores=total_stores,
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
        industry: Optional[str],
        log: Callable[[str], None],
    ) -> StoreInvestigationResult:
        """ハイブリッド調査（AI → スクレイピング補完）"""
        log("ハイブリッド調査を開始...")

        # Step 1: AI調査
        ai_result = await self._investigate_ai(
            company_name, official_url, industry, log
        )

        # Step 2: 信頼度チェック（is_confident: needs_verification=False かつ total_stores>0）
        if ai_result.is_confident:
            log("AI調査の結果が十分です")
            ai_result = StoreInvestigationResult(
                company_name=ai_result.company_name,
                total_stores=ai_result.total_stores,
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
            log("AI調査が要確認のためスクレイピングで補完...")

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

            # API制限対策の遅延（セマフォ外）
            await asyncio.sleep(delay_seconds)
            return result

        # 並行実行
        tasks = [investigate_one(i, c) for i, c in enumerate(companies)]
        results = await asyncio.gather(*tasks)

        return list(results)
