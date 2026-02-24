#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM APIクライアント
==================
Gemini API 専用クライアント（Google検索グラウンディング対応）

【対応モデル】
- gemini-2.5-flash（高速、デフォルト）
- gemini-2.5-pro（精密）
- gemini-3-flash / gemini-3-pro
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 環境変数読み込み（override=True で .env.local を優先）
load_dotenv(Path.home() / ".env.local", override=True)


class LLMClient:
    """
    Gemini API クライアント

    【使用例】
    ```python
    client = LLMClient()
    response = client.call("質問内容", model="gemini-2.5-flash")

    # Google検索グラウンディング付き（最新情報が必要な場合）
    response = client.call("質問内容", use_search=True)
    ```
    """

    # Gemini モデル（2026年2月時点の最新）
    # 参考: https://ai.google.dev/gemini-api/docs/models
    GEMINI_MODELS = {
        "gemini-flash": "gemini-2.5-flash",
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.0-flash": "gemini-2.0-flash",  # 2026年3月廃止予定
        "gemini-2.5-pro": "gemini-2.5-pro",
        "gemini-3-flash": "gemini-3-flash",
        "gemini-3-pro": "gemini-3-pro",
    }

    def __init__(
        self,
        api_key: str = None,
        enable_cache: bool = False,
    ):
        """
        Args:
            api_key: Google API キー（未指定時は環境変数 GOOGLE_API_KEY から取得）
            enable_cache: レスポンスキャッシュを有効化（デフォルト無効）
        """
        self._cache = None

        if enable_cache:
            from core.llm_cache import LLMCache
            self._cache = LLMCache(ttl_seconds=3600, max_size=500)

        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")

        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is required")

    def call(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        system_prompt: str = None,
        use_search: bool = False,
    ) -> str:
        """
        Gemini API を同期呼び出し

        Args:
            prompt: ユーザープロンプト
            model: モデル名（未指定時は gemini-2.5-flash）
            temperature: 生成温度
            max_tokens: 最大トークン数
            system_prompt: システムプロンプト（オプション）
            use_search: Google検索グラウンディングを有効化（最新情報が必要な場合）

        Returns:
            生成されたテキスト
        """
        # キャッシュチェック（有効時のみ）
        cache_key = None
        if self._cache is not None:
            full_prompt = f"{system_prompt or ''}|{prompt}"
            cache_key = self._cache.make_key(full_prompt, model or "", temperature)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # API呼び出し
        result = self._call_gemini(prompt, model, temperature, max_tokens, system_prompt, use_search)

        # キャッシュに保存（有効時のみ）
        if self._cache is not None and cache_key is not None:
            self._cache.set(cache_key, result)

        return result

    def _call_gemini(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        system_prompt: str = None,
        use_search: bool = False,
    ) -> str:
        """Gemini API 呼び出し（google.genai パッケージ使用）"""

        model = model or "gemini-2.5-flash"

        # モデル名を正規化
        if model in self.GEMINI_MODELS:
            model = self.GEMINI_MODELS[model]

        # 新しい google.genai パッケージを試す
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            # システムプロンプトを含める
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # Google検索グラウンディングの設定
            tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None

            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    tools=tools,
                ),
            )
            return response.text

        except ImportError:
            # フォールバック: 旧パッケージを試す
            try:
                import google.generativeai as genai_old

                genai_old.configure(api_key=self.api_key)

                full_prompt = prompt
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\n{prompt}"

                model_obj = genai_old.GenerativeModel(model)
                response = model_obj.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                )
                return response.text
            except ImportError:
                raise RuntimeError("google-genai package is required: pip install google-genai")

        except AttributeError as e:
            raise RuntimeError(f"Gemini API レスポンス解析エラー: {e}")
        except Exception as e:
            error_msg = str(e)
            if "quota" in error_msg.lower():
                raise RuntimeError("Gemini API クォータ超過: 利用制限に達しました")
            elif "invalid" in error_msg.lower() and "key" in error_msg.lower():
                raise RuntimeError("Gemini API 認証エラー: APIキーを確認してください")
            raise RuntimeError(f"Gemini API エラー: {e}")

    def extract_json(self, text: str) -> Optional[dict | list]:
        """
        テキストからJSONを抽出

        Args:
            text: LLMの出力テキスト

        Returns:
            抽出されたJSON（dict or list）、見つからない場合はNone
        """
        if not text:
            return None

        # ```json ... ``` 形式を探す
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # テキスト内の最初の `[` と `{` を比較し、先に出現する方から試す
        # これにより "[{...}, {...}]" のような配列が "{...}" として誤解析されない
        first_bracket = text.find('[')
        first_brace = text.find('{')

        # 試行順序を決定
        if first_bracket >= 0 and (first_brace < 0 or first_bracket < first_brace):
            # [ が先に出現 → 配列パターンを先に試す
            patterns = [
                (r'\[[\s\S]*\]', "array_greedy"),
                (r'\{[\s\S]*\}', "object_greedy"),
            ]
        else:
            # { が先に出現（または両方ない） → オブジェクトパターンを先に試す
            patterns = [
                (r'\{[\s\S]*\}', "object_greedy"),
                (r'\[[\s\S]*\]', "array_greedy"),
            ]

        for pattern, _label in patterns:
            json_match = re.search(pattern, text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        return None


def is_api_available() -> bool:
    """
    Gemini API が利用可能かを確認

    Returns:
        bool: GOOGLE_API_KEY が設定されていれば True
    """
    return bool(os.getenv("GOOGLE_API_KEY"))


def get_default_client() -> LLMClient:
    """
    デフォルトの Gemini クライアントを作成

    Returns:
        LLMClient: Gemini クライアント

    Raises:
        ValueError: GOOGLE_API_KEY が未設定の場合
    """
    if not is_api_available():
        raise ValueError("No LLM API key configured. Set GOOGLE_API_KEY in ~/.env.local")

    return LLMClient()
