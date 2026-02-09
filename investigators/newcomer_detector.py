#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新規参入プレイヤー自動検出モジュール
====================================
LLMによる新規参入候補の提案 + URL自動検証 + 信頼度スコアリング。

【重要】
- 候補はAIの提案であり、必ず手動確認が必要
- 「自動追加」は行わない（候補一覧 → 手動確認 → エクスポートの3ステップ必須）
- ハルシネーション対策: URL存在確認 + 信頼度半減ルール

【使用方法】
```python
from investigators.newcomer_detector import NewcomerDetector

detector = NewcomerDetector(llm_client=client)
candidates = await detector.detect(
    industry="動画配信サービス",
    existing_players=["Netflix", "Hulu", "ABEMAプレミアム"],
)
```
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from investigators.base import NewcomerCandidate
from core.sanitizer import sanitize_input, sanitize_url


class NewcomerDetector:
    """
    新規参入プレイヤー自動検出

    【多段階検証パイプライン】
    1. LLM提案: 既存リストにない新規参入候補を取得
    2. URL存在確認: 候補のURLにHEADリクエスト
    3. 信頼度スコアリング: URL検証結果を反映
    """

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

    def _get_llm_client(self):
        """LLMクライアントを取得（遅延初期化）"""
        if self.llm is None:
            from core.llm_client import get_default_client
            self.llm = get_default_client()
        return self.llm

    async def detect(
        self,
        industry: str,
        existing_players: list[str],
        on_progress: Optional[Callable] = None,
    ) -> list[NewcomerCandidate]:
        """
        新規参入候補を検出

        Args:
            industry: 業界名
            existing_players: 既存プレイヤー名のリスト
            on_progress: 進捗コールバック

        Returns:
            NewcomerCandidate のリスト（URL検証済み）
        """
        if on_progress:
            on_progress(1, 3, "LLMに問い合わせ中...")

        # Step 1: LLMに問い合わせ
        candidates = await self._query_newcomers(industry, existing_players)

        if on_progress:
            on_progress(2, 3, f"URL検証中（{len(candidates)}件）...")

        # Step 2: URL自動検証（全候補）
        for candidate in candidates:
            if candidate.official_url:
                url_result = await self._verify_url(candidate.official_url)
                if url_result.get("status_code", 0) in (200, 301, 302, 303, 307, 308):
                    candidate.url_verified = True
                    candidate.verification_status = "verified"
                elif url_result.get("error"):
                    candidate.url_verified = False
                    candidate.verification_status = "url_error"
            else:
                candidate.verification_status = "unverified"

        # Step 3: 信頼度再計算（URL検証結果を反映）
        for candidate in candidates:
            if not candidate.url_verified and candidate.official_url:
                candidate.confidence *= 0.5  # URL不明は信頼度半減

        if on_progress:
            on_progress(3, 3, "検出完了")

        return candidates

    async def _query_newcomers(
        self,
        industry: str,
        existing_players: list[str],
    ) -> list[NewcomerCandidate]:
        """LLMに新規参入候補を問い合わせ"""

        llm = self._get_llm_client()

        safe_industry = sanitize_input(industry)
        safe_players = [sanitize_input(p) for p in existing_players]

        current_year = datetime.now().year
        existing_text = "\n".join(f"- {p}" for p in safe_players)

        prompt = f"""{safe_industry} 業界について、{current_year}年時点で日本国内でサービスを提供しているプレイヤーを調査。
以下の既存リストに含まれていない新規参入企業を特定してください。

【既存リスト】（{len(existing_players)}件）
{existing_text}

【重要な制約】
- 確実に存在するサービスのみ回答。推測や「ありそうな」サービスは含めない
- 公式サイトURLが確認できない場合はofficial_urlを空文字にする
- 各候補について、存在を確認した情報ソースURLを必ず記載
- 「新規参入がない場合」は空配列 [] を返すこと（無理に候補を作らない）

【出力形式】JSON
[
    {{
        "player_name": "サービス名",
        "official_url": "https://...",
        "company_name": "運営会社名",
        "entry_date_approx": "2025-06",
        "confidence": 0.8,
        "source_urls": ["https://..."],
        "reason": "新規参入と判断した理由"
    }}
]"""

        # LLM呼び出し（同期→非同期ラッパー）
        loop = asyncio.get_event_loop()
        raw_response = await loop.run_in_executor(
            None,
            lambda: llm.call(prompt, model=self.model, temperature=0.1)
        )

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> list[NewcomerCandidate]:
        """LLMレスポンスを解析"""

        llm = self._get_llm_client()

        try:
            data = llm.extract_json(raw_response)
        except Exception:
            data = None

        if data is None:
            return []

        # dict の場合、候補リストを探す
        if isinstance(data, dict):
            candidates_data = data.get("results", data.get("candidates", []))
        elif isinstance(data, list):
            candidates_data = data
        else:
            return []

        candidates = []
        for item in candidates_data:
            if not isinstance(item, dict):
                continue

            player_name = item.get("player_name", "").strip()
            if not player_name:
                continue

            # URLサニタイズ
            official_url = sanitize_url(item.get("official_url", ""))

            # source_urls の処理
            source_urls = item.get("source_urls", [])
            if isinstance(source_urls, str):
                source_urls = [source_urls]
            source_urls = [sanitize_url(u) for u in source_urls if u]

            candidate = NewcomerCandidate(
                player_name=player_name,
                official_url=official_url,
                company_name=item.get("company_name", ""),
                entry_date_approx=item.get("entry_date_approx", ""),
                confidence=float(item.get("confidence", 0.5)),
                source_urls=source_urls,
                reason=item.get("reason", ""),
                verification_status="unverified",
                url_verified=False,
            )
            candidates.append(candidate)

        return candidates

    async def _verify_url(self, url: str) -> dict:
        """
        URLの有効性をチェック（player_validator._check_url_status() と同パターン）

        Returns:
            dict: {"status_code": int, "final_url": str, "is_redirect": bool}
        """
        if not url:
            return {"status_code": 0, "error": "empty_url"}

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
                "final_url": str(response.url),
                "is_redirect": len(response.history) > 0,
            }
        except requests.exceptions.Timeout:
            return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "timeout"}
        except requests.exceptions.SSLError:
            return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "ssl_error"}
        except requests.exceptions.ConnectionError:
            return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "connection_error"}
        except requests.exceptions.RequestException:
            return {"status_code": 0, "final_url": url, "is_redirect": False, "error": "request_error"}
