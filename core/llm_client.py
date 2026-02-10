#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM APIクライアント
==================
Perplexity / Gemini API への統一インターフェース

【対応プロバイダー】
- Perplexity (sonar, sonar-pro, sonar-reasoning-pro)
- Gemini (gemini-2.0-flash, gemini-1.5-pro)
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# 環境変数読み込み（override=True で .env.local を優先）
load_dotenv(Path.home() / ".env.local", override=True)


class LLMClient:
    """
    LLM API クライアント

    【使用例】
    ```python
    client = LLMClient(provider="perplexity")
    response = await client.call_async("質問内容", model="sonar-pro")
    ```
    """

    # Perplexity モデル
    PERPLEXITY_MODELS = {
        "sonar": "sonar",
        "sonar-pro": "sonar-pro",
        "sonar-reasoning": "sonar-reasoning",
        "sonar-reasoning-pro": "sonar-reasoning-pro",
        "sonar-deep-research": "sonar-deep-research",
    }

    # Gemini モデル（2026年1月時点の最新）
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
        provider: str = "perplexity",
        enable_cache: bool = False,
    ):
        """
        Args:
            api_key: API キー（未指定時は環境変数から取得）
            provider: LLMプロバイダー ("perplexity" or "gemini")
            enable_cache: レスポンスキャッシュを有効化（デフォルト無効）
        """
        self.provider = provider
        self._cache = None

        if enable_cache:
            from core.llm_cache import LLMCache
            self._cache = LLMCache(ttl_seconds=3600, max_size=500)

        if provider == "perplexity":
            self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        elif provider == "gemini":
            self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        else:
            raise ValueError(f"Unknown provider: {provider}")

        if not self.api_key:
            raise ValueError(f"{provider.upper()}_API_KEY is required")

    def call(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        system_prompt: str = None,
    ) -> str:
        """
        LLM API を同期呼び出し

        Args:
            prompt: ユーザープロンプト
            model: モデル名（未指定時はデフォルト）
            temperature: 生成温度
            max_tokens: 最大トークン数
            system_prompt: システムプロンプト（オプション）

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
        if self.provider == "perplexity":
            result = self._call_perplexity(prompt, model, temperature, max_tokens, system_prompt)
        elif self.provider == "gemini":
            result = self._call_gemini(prompt, model, temperature, max_tokens, system_prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        # キャッシュに保存（有効時のみ）
        if self._cache is not None and cache_key is not None:
            self._cache.set(cache_key, result)

        return result

    def _call_perplexity(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        system_prompt: str = None,
    ) -> str:
        """Perplexity API 呼び出し"""
        model = model or "sonar-pro"

        # モデル名を正規化
        if model in self.PERPLEXITY_MODELS:
            model = self.PERPLEXITY_MODELS[model]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=180,  # 3分
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout as e:
            raise RuntimeError(f"Perplexity API タイムアウト（180秒）: {e}")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                raise RuntimeError("Perplexity API 認証エラー: APIキーを確認してください")
            elif e.response is not None and e.response.status_code == 429:
                raise RuntimeError("Perplexity API レート制限: しばらく待ってから再試行してください")
            raise RuntimeError(f"Perplexity API HTTPエラー: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Perplexity API 接続エラー: {e}")

    def _call_gemini(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 8000,
        system_prompt: str = None,
    ) -> str:
        """Gemini API 呼び出し（新しい google.genai パッケージ使用）"""

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

            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
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


def get_available_providers() -> dict[str, bool]:
    """
    利用可能なLLMプロバイダーを確認

    Returns:
        dict: {provider_name: is_available}
    """
    return {
        "perplexity": bool(os.getenv("PERPLEXITY_API_KEY")),
        "gemini": bool(os.getenv("GOOGLE_API_KEY")),
    }


def get_default_client() -> LLMClient:
    """
    利用可能なプロバイダーでデフォルトのクライアントを作成

    Returns:
        LLMClient: 利用可能なクライアント

    Raises:
        ValueError: 利用可能なプロバイダーがない場合
    """
    providers = get_available_providers()

    if providers.get("perplexity"):
        return LLMClient(provider="perplexity")
    elif providers.get("gemini"):
        return LLMClient(provider="gemini")
    else:
        raise ValueError("No LLM API key configured. Set PERPLEXITY_API_KEY or GOOGLE_API_KEY")
