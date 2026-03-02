#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
0ベースプレイヤーリスト生成モジュール
======================================
既存リストなしで、業界+条件からプレイヤーリストを全量生成する。
newcomer_detector のパイプライン（LLM→候補→URL検証）を応用。

【重要】
- AI生成の候補は必ず手動確認が必要
- URL検証 + 手動確認の2段階ゲートでハルシネーション対策
- temperature=0.1 で事実確認に特化

【使用方法】
```python
from investigators.player_list_generator import PlayerListGenerator

generator = PlayerListGenerator(llm_client=client)
players = await generator.generate(
    industry="動画配信サービス",
    conditions="日本国内でサービスを提供しているもの",
)
```
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from investigators.base import GeneratedPlayer
from core.sanitizer import sanitize_input, sanitize_url, verify_url
from core.llm_client import DEFAULT_MODEL
from core.llm_schemas import parse_llm_response, NewcomerCandidateLLMResponse


class PlayerListGenerator:
    """
    0ベースプレイヤーリスト生成

    【多段階検証パイプライン】
    1. LLM生成: 業界+条件からプレイヤー候補を網羅的に取得
    2. URL存在確認: 候補のURLにHEADリクエスト
    3. 手動確認: ユーザーがチェックボックスで選択→エクスポート
    """

    # コスト概算用の単価（USD/API呼び出し）
    COST_PER_CALL = 0.05  # 検索グラウンディング付き

    @staticmethod
    def estimate_cost() -> dict:
        """コスト概算を計算

        1回の固定LLM呼び出し。

        Returns:
            {"call_count": int, "cost_per_call": float, "estimated_cost": float}
        """
        return {
            "call_count": 1,
            "cost_per_call": PlayerListGenerator.COST_PER_CALL,
            "estimated_cost": PlayerListGenerator.COST_PER_CALL,
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

    def _get_llm_client(self):
        """LLMクライアントを取得（遅延初期化）"""
        if self.llm is None:
            from core.llm_client import get_default_client
            self.llm = get_default_client()
        return self.llm

    async def generate(
        self,
        industry: str,
        conditions: str = "",
        max_count: int = 50,
        on_progress: Optional[Callable] = None,
    ) -> list[GeneratedPlayer]:
        """
        プレイヤーリストを0から生成

        Args:
            industry: 業界名
            conditions: 絞り込み条件（テキスト）
            max_count: 最大件数
            on_progress: 進捗コールバック (current, total, message)

        Returns:
            GeneratedPlayer のリスト（URL検証済み）
        """
        if on_progress:
            on_progress(1, 3, "LLMにプレイヤーリストを生成中...")

        # Step 1: LLMに問い合わせ
        candidates = await self._query_players(industry, conditions, max_count)

        if on_progress:
            on_progress(2, 3, f"URL検証中（{len(candidates)}件）...")

        # Step 2: URL自動検証（全候補）
        for candidate in candidates:
            if candidate.official_url:
                url_result = await self._verify_url(candidate.official_url)
                if url_result.get("status_code", 0) in (200, 301, 302, 303, 307, 308):
                    candidate.url_verified = True
                elif url_result.get("error"):
                    candidate.url_verified = False

        if on_progress:
            on_progress(3, 3, "生成完了")

        return candidates

    async def _query_players(
        self,
        industry: str,
        conditions: str,
        max_count: int,
    ) -> list[GeneratedPlayer]:
        """LLMにプレイヤーリストを問い合わせ"""

        llm = self._get_llm_client()

        safe_industry = sanitize_input(industry)
        safe_conditions = sanitize_input(conditions) if conditions else ""

        current_year = datetime.now().year

        # 条件セクション（attribute_investigatorのcontext注入パターンを採用）
        conditions_section = f"\n■絞り込み条件\n{safe_conditions}\n" if safe_conditions else ""

        prompt = f"""{safe_industry} 業界において{current_year}年時点でサービスを提供しているプレイヤーを
網羅的に列挙してください。
{conditions_section}
■重要な制約
- 確実に存在するサービスのみ。推測や「ありそうな」サービスは不可
- 公式サイトURLが不明ならofficial_urlを空文字に
- 情報ソースURLを必ず記載
- 最大{max_count}件まで
- 「プレイヤーがいない場合」は空配列 [] を返すこと

■出力形式: JSON配列
[
    {{
        "player_name": "サービス名",
        "official_url": "https://...",
        "company_name": "運営会社名",
        "source_urls": ["https://..."],
        "reason": "リストに含める理由"
    }}
]

■正しい出力の例
[{{"player_name": "Netflix", "official_url": "https://www.netflix.com/jp/", "company_name": "Netflix株式会社", "source_urls": ["https://www.netflix.com/jp/"], "reason": "国内主要動画配信サービス"}}]
"""

        # LLM呼び出し（同期→非同期ラッパー、temperature=0.1）
        loop = asyncio.get_running_loop()
        raw_response = await loop.run_in_executor(
            None,
            lambda: llm.call(prompt, model=self.model, temperature=0.1, use_search=True)
        )

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> list[GeneratedPlayer]:
        """LLMレスポンスを解析（pydantic バリデーション）"""

        llm = self._get_llm_client()

        try:
            data = llm.extract_json(raw_response)
        except Exception:
            data = None

        if data is None:
            return []

        # dict の場合、リストを探す
        if isinstance(data, dict):
            candidates_data = data.get("results", data.get("players", data.get("candidates", [])))
        elif isinstance(data, list):
            candidates_data = data
        else:
            return []

        players = []
        for item in candidates_data:
            if not isinstance(item, dict):
                continue

            # pydantic でバリデーション（NewcomerCandidateLLMResponse を再利用）
            parsed = parse_llm_response(item, NewcomerCandidateLLMResponse)
            if parsed is None or not parsed.player_name.strip():
                continue

            # URLサニタイズ
            official_url = sanitize_url(parsed.official_url)
            source_urls = [sanitize_url(u) for u in parsed.source_urls if u]

            player = GeneratedPlayer(
                player_name=parsed.player_name.strip(),
                official_url=official_url,
                company_name=parsed.company_name,
                source_urls=source_urls,
                reason=parsed.reason,
                url_verified=False,
            )
            players.append(player)

        return players

    async def _verify_url(self, url: str) -> dict:
        """URLの有効性をチェック"""
        return await verify_url(url)
