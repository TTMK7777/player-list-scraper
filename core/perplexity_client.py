#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Perplexity API クライアント（補助検索エンジン）
================================================
Gemini をメインとし、Perplexity を補助的な検索・クロスバリデーション用に使用。

【設計方針】
- Perplexity は OpenAI 互換 API を使用（公式推奨）
- Gemini の結果を補完する目的のみ（単独使用は想定しない）
- PERPLEXITY_API_KEY 未設定時は全機能が graceful に無効化
- エラー時は空文字列を返し、呼び出し元の Gemini フローを妨げない

【使用方法】
```python
from core.perplexity_client import PerplexityClient, is_perplexity_available

if is_perplexity_available():
    client = PerplexityClient()
    result = client.search("楽天カード 最新ニュース 2026年")
```
"""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 環境変数読み込み（override=True で .env.local を優先）
load_dotenv(Path.home() / ".env.local", override=True)

logger = logging.getLogger(__name__)

# Perplexity API 設定
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
PERPLEXITY_DEFAULT_MODEL = "sonar-pro"


class PerplexityClient:
    """
    Perplexity API クライアント（補助検索エンジン）

    OpenAI 互換 API を使用。Gemini のクロスバリデーション・補完用。

    【使用例】
    ```python
    client = PerplexityClient()
    # 基本検索（テキスト回答を返す）
    result = client.search("楽天カード サービス終了 2026年")

    # プレイヤー検証用（構造化された質問）
    result = client.verify_player_status("楽天カード", industry="クレジットカード")
    ```
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = PERPLEXITY_DEFAULT_MODEL,
    ):
        """
        Args:
            api_key: Perplexity API キー（未指定時は環境変数 PERPLEXITY_API_KEY から取得）
            model: 使用モデル（デフォルト: sonar-pro）
        """
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError(
                "PERPLEXITY_API_KEY is required. "
                "Set it in ~/.env.local or pass it explicitly."
            )

    def search(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> str:
        """
        Perplexity にテキスト検索クエリを送信

        Args:
            query: 検索クエリ
            system_prompt: システムプロンプト（オプション）
            temperature: 生成温度（デフォルト: 0.1、事実確認向け）
            max_tokens: 最大トークン数

        Returns:
            検索結果テキスト（エラー時は空文字列）
        """
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=PERPLEXITY_BASE_URL,
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": query})

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content or ""

        except ImportError:
            logger.warning(
                "openai パッケージが未インストールです。"
                "Perplexity 補助検索は無効化されます: pip install openai"
            )
            return ""
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            logger.warning("Perplexity API エラー（補助検索は無視して続行）: %s", e)
            return ""

    def verify_player_status(
        self,
        player_name: str,
        industry: str = "",
        company_name: str = "",
    ) -> str:
        """
        プレイヤーの最新状態を Perplexity で補助検証

        Gemini の正誤チェック結果が「要確認」の場合に呼ばれる。
        構造化 JSON は求めず、テキスト回答で事実情報を取得。

        Args:
            player_name: プレイヤー名
            industry: 業界名（オプション）
            company_name: 運営会社名（オプション）

        Returns:
            検証結果テキスト（エラー時は空文字列）
        """
        industry_ctx = f"（{industry}業界）" if industry else ""
        company_ctx = f"（運営: {company_name}）" if company_name else ""

        query = (
            f"「{player_name}」{industry_ctx}{company_ctx}について、"
            f"以下を簡潔に教えてください:\n"
            f"1. 現在もサービスは継続していますか？\n"
            f"2. 最近のサービス名変更や運営会社の変更はありますか？\n"
            f"3. 撤退・統合・買収などの重大ニュースはありますか？\n"
            f"日本語で、事実のみ回答してください。"
        )

        system_prompt = (
            "あなたは正確な事実確認アシスタントです。"
            "確認できない情報は「確認できません」と回答してください。"
            "推測は一切行わないでください。"
        )

        return self.search(
            query=query,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1500,
        )

    def search_newcomers(
        self,
        industry: str,
        existing_players: list[str],
    ) -> str:
        """
        新規参入候補を Perplexity で補助検索

        Gemini の新規参入検出結果のクロスバリデーション用。

        Args:
            industry: 業界名
            existing_players: 既存プレイヤー名リスト（除外用）

        Returns:
            検索結果テキスト（エラー時は空文字列）
        """
        existing_text = "、".join(existing_players[:20])  # 上位20件で制限

        query = (
            f"{industry} 業界で、最近（直近1-2年以内）に新規参入した"
            f"日本国内のサービスやプレイヤーを教えてください。\n"
            f"以下の既存プレイヤーは除外してください: {existing_text}\n"
            f"各候補について、サービス名・運営会社・参入時期・公式サイトURL（分かれば）"
            f"を簡潔に列挙してください。"
        )

        system_prompt = (
            "あなたは市場調査アシスタントです。"
            "確実に存在するサービスのみ回答してください。"
            "推測や「ありそうな」サービスは含めないでください。"
        )

        return self.search(
            query=query,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=2000,
        )


def is_perplexity_available() -> bool:
    """
    Perplexity API が利用可能かを確認

    Returns:
        bool: PERPLEXITY_API_KEY が設定されていれば True
    """
    return bool(os.getenv("PERPLEXITY_API_KEY"))


def get_perplexity_client() -> Optional[PerplexityClient]:
    """
    Perplexity クライアントを安全に取得

    APIキー未設定時は None を返す（エラーではない）。

    Returns:
        PerplexityClient or None
    """
    if not is_perplexity_available():
        return None

    try:
        return PerplexityClient()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        logger.warning("Perplexity クライアントの初期化に失敗: %s", e)
        return None
