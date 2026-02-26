#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
属性調査エンジン（カテゴリ/ブランド統合）
==========================================
プレイヤー × 属性リスト → ○/×/? のマトリクスを生成。
バッチプロンプト方式でコスト最適化。

【使用方法】
```python
from investigators.attribute_investigator import AttributeInvestigator
from core.attribute_presets import get_preset

preset = get_preset("動画配信_ジャンル")
investigator = AttributeInvestigator(llm_client=client)
results = await investigator.investigate_batch(
    players=[{"player_name": "Netflix", "official_url": "https://www.netflix.com/jp/"}],
    attributes=preset["attributes"],
    industry="動画配信サービス",
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

from investigators.base import AttributeInvestigationResult
from core.sanitizer import sanitize_input
from core.attribute_presets import ATTRIBUTE_PRESETS


class AttributeInvestigator:
    """
    属性調査エンジン

    プレイヤー × 属性リスト → ○/×/? マトリクスを生成。
    バッチプロンプト方式で複数社まとめてLLM呼び出し（コスト最適化）。
    """

    # コスト概算用の単価（USD/バッチ呼び出し）
    COST_PER_BATCH_CALL = 0.03

    def __init__(
        self,
        llm_client=None,
        model: str = "gemini-2.5-flash",
    ):
        """
        Args:
            llm_client: LLMクライアント（未指定時は自動作成）
            model: 使用するLLMモデル
        """
        self.llm = llm_client
        self.model = model

    def _get_llm_client(self):
        """LLMクライアントを取得（遅延初期化、キャッシュ有効）"""
        if self.llm is None:
            from core.llm_client import LLMClient
            # 属性調査は静的情報なのでキャッシュ有効
            self.llm = LLMClient(enable_cache=True)
        return self.llm

    def _optimal_batch_size(self, attribute_count: int) -> int:
        """属性数に応じたバッチサイズを自動決定

        Args:
            attribute_count: 属性数

        Returns:
            推奨バッチサイズ（プレイヤー数/バッチ）
        """
        if attribute_count <= 7:    # クレカブランド(7属性)
            return 10  # 10社まとめ
        elif attribute_count <= 15:  # 動画配信(15属性)
            return 5   # 5社まとめ
        else:                        # カスタム(多属性)
            return 3   # 3社まとめ

    def estimate_cost(
        self,
        player_count: int,
        attribute_count: int,
        batch_size: Optional[int] = None,
    ) -> dict:
        """コスト概算を計算

        Args:
            player_count: プレイヤー数
            attribute_count: 属性数
            batch_size: バッチサイズ（未指定時は自動決定）

        Returns:
            {"batch_size": int, "batch_count": int, "estimated_cost": float}
        """
        if batch_size is None:
            batch_size = self._optimal_batch_size(attribute_count)

        batch_count = (player_count + batch_size - 1) // batch_size
        estimated_cost = batch_count * self.COST_PER_BATCH_CALL

        return {
            "batch_size": batch_size,
            "batch_count": batch_count,
            "estimated_cost": estimated_cost,
            "player_count": player_count,
            "attribute_count": attribute_count,
        }

    async def investigate_batch(
        self,
        players: list[dict],
        attributes: list[str],
        industry: str = "",
        batch_size: Optional[int] = None,
        on_progress: Optional[Callable] = None,
        concurrency: int = 2,
        delay_seconds: float = 1.5,
        context: str = "",
    ) -> list[AttributeInvestigationResult]:
        """バッチ単位で属性調査を実行

        Args:
            players: プレイヤーリスト [{"player_name": ..., "official_url": ...}, ...]
            attributes: 調査対象の属性リスト
            industry: 業界名
            batch_size: バッチサイズ（未指定時は自動決定）
            on_progress: 進捗コールバック(current, total, name)
            concurrency: 同時実行数
            delay_seconds: バッチ間遅延（秒）
            context: 判定基準の補足コンテキスト（空文字の場合は省略）

        Returns:
            AttributeInvestigationResult のリスト
        """
        if batch_size is None:
            batch_size = self._optimal_batch_size(len(attributes))

        results = []
        total = len(players)
        semaphore = asyncio.Semaphore(concurrency)

        # バッチ分割
        batches = []
        for i in range(0, total, batch_size):
            batches.append(players[i:i + batch_size])

        processed = 0

        for batch_idx, batch in enumerate(batches):
            async with semaphore:
                try:
                    batch_results = await self._investigate_single_batch(
                        batch, attributes, industry, context=context
                    )
                    results.extend(batch_results)
                except Exception as e:
                    # バッチ全体がエラーの場合、個別にエラー結果を生成
                    batch_names = [p.get("player_name", "?") for p in batch]
                    error_context = f"バッチ{batch_idx + 1} ({', '.join(batch_names)}): {e}"
                    for player in batch:
                        results.append(
                            AttributeInvestigationResult.create_error(
                                player_name=player.get("player_name", "不明"),
                                error_message=error_context,
                            )
                        )

                processed += len(batch)

                if on_progress:
                    names = ", ".join(p.get("player_name", "?") for p in batch)
                    on_progress(processed, total, names)

                # レート制限対策
                if batch_idx < len(batches) - 1:
                    await asyncio.sleep(delay_seconds)

        return results

    async def _investigate_single_batch(
        self,
        players: list[dict],
        attributes: list[str],
        industry: str = "",
        context: str = "",
    ) -> list[AttributeInvestigationResult]:
        """1バッチ分の属性調査を実行（複数社まとめて1回のLLM呼び出し）

        Args:
            players: バッチ内のプレイヤーリスト
            attributes: 調査対象属性リスト
            industry: 業界名
            context: 判定基準の補足コンテキスト（空文字の場合は省略）

        Returns:
            AttributeInvestigationResult のリスト
        """

        llm = self._get_llm_client()

        # プロンプト生成
        prompt = self._build_batch_prompt(players, attributes, industry, context=context)

        # LLM呼び出し（同期→非同期ラッパー）
        loop = asyncio.get_running_loop()
        raw_response = await loop.run_in_executor(
            None,
            lambda: llm.call(prompt, model=self.model, temperature=0.1)
        )

        # レスポンス解析
        return self._parse_batch_response(raw_response, players, attributes)

    def _build_batch_prompt(
        self,
        players: list[dict],
        attributes: list[str],
        industry: str = "",
        context: str = "",
    ) -> str:
        """バッチプロンプトを生成

        Args:
            players: バッチ内のプレイヤーリスト
            attributes: 調査対象属性リスト
            industry: 業界名
            context: 判定基準の補足コンテキスト（空文字の場合は省略）

        Returns:
            LLM用プロンプト文字列
        """
        safe_industry = sanitize_input(industry) if industry else ""

        # プレイヤー一覧
        player_lines = []
        for i, player in enumerate(players, 1):
            name = sanitize_input(player.get("player_name", ""))
            url = player.get("official_url", "")
            if url:
                player_lines.append(f"{i}. {name}（{url}）")
            else:
                player_lines.append(f"{i}. {name}")

        players_text = "\n".join(player_lines)

        # 属性一覧
        attributes_text = ", ".join(attributes)

        industry_text = f"（{safe_industry}業界）" if safe_industry else ""

        # コンテキストセクション（指定時のみ挿入）
        context_section = f"\n■判定基準\n{context}\n" if context else ""

        prompt = f"""以下の{len(players)}つのサービス{industry_text}について、各属性の取り扱い有無を調査してください。

■調査対象
{players_text}
{context_section}
■調査属性: {attributes_text}

【出力形式】JSON（必ずこの形式で出力してください）
{{
    "results": [
        {{
            "player_name": "サービス名",
            "attributes": {{"属性名1": true, "属性名2": false, "属性名3": null}},
            "confidence": 0.9,
            "sources": ["https://..."]
        }}
    ]
}}

【判定ルール】
- 公式サイト・プレスリリースで確認 → true
- 明確に取り扱いなしと確認 → false
- 確認できない場合 → null
- 推測禁止。事実のみ回答すること
- 各プレイヤーに対して、全属性の判定を必ず含めること"""

        return prompt

    def _parse_batch_response(
        self,
        raw_response: str,
        players: list[dict],
        attributes: list[str],
    ) -> list[AttributeInvestigationResult]:
        """バッチレスポンスを解析して結果リストに変換"""

        llm = self._get_llm_client()

        try:
            data = llm.extract_json(raw_response)
        except Exception:
            data = None

        if data is None:
            # JSON解析失敗 → 全プレイヤーを要確認に
            return [
                AttributeInvestigationResult.create_uncertain(
                    player_name=p.get("player_name", "不明"),
                    reason="JSONレスポンス解析失敗",
                    raw_response=raw_response,
                )
                for p in players
            ]

        # results キーから取得（dict の場合）
        if isinstance(data, dict):
            result_list = data.get("results", [])
        elif isinstance(data, list):
            result_list = data
        else:
            result_list = []

        # 結果をプレイヤー名でマッピング
        results = []
        result_map = {}
        for item in result_list:
            if isinstance(item, dict):
                name = item.get("player_name", "")
                result_map[name] = item

        for player in players:
            player_name = player.get("player_name", "不明")

            # 名前で結果を探す
            item = result_map.get(player_name)

            if item is None:
                # 部分一致で探す
                for key, val in result_map.items():
                    if player_name in key or key in player_name:
                        item = val
                        break

            if item is None:
                results.append(
                    AttributeInvestigationResult.create_uncertain(
                        player_name=player_name,
                        reason="LLMレスポンスに該当結果なし",
                        raw_response=raw_response,
                    )
                )
                continue

            # 属性マトリクスを正規化
            raw_attrs = item.get("attributes", {})
            attribute_matrix = {}
            for attr in attributes:
                value = raw_attrs.get(attr)
                if value is True:
                    attribute_matrix[attr] = True
                elif value is False:
                    attribute_matrix[attr] = False
                else:
                    attribute_matrix[attr] = None  # null/不明

            sources = item.get("sources", [])
            if isinstance(sources, str):
                sources = [sources]

            results.append(
                AttributeInvestigationResult.create_success(
                    player_name=player_name,
                    attribute_matrix=attribute_matrix,
                    source_urls=sources,
                )
            )

        return results

    async def investigate_single(
        self,
        player_name: str,
        official_url: str,
        attributes: list[str],
        industry: str = "",
        context: str = "",
    ) -> AttributeInvestigationResult:
        """個別プレイヤーの属性調査（精密調査用）

        Args:
            player_name: プレイヤー名
            official_url: 公式URL
            attributes: 調査対象属性リスト
            industry: 業界名
            context: 判定基準の補足コンテキスト（空文字の場合は省略）

        Returns:
            AttributeInvestigationResult
        """
        player = {"player_name": player_name, "official_url": official_url}
        results = await self._investigate_single_batch(
            [player], attributes, industry, context=context
        )
        return results[0] if results else AttributeInvestigationResult.create_error(
            player_name=player_name,
            error_message="調査結果なし",
        )
