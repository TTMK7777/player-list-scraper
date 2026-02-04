#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
正誤チェック機能のテスト（1件のみ）
"""

import asyncio
import sys
import io
from pathlib import Path

# Windows環境でのUnicode出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# モジュールパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from core.llm_client import get_available_providers, get_default_client
from investigators.player_validator import PlayerValidator
from investigators.base import AlertLevel


async def test_single_validation():
    """単一プレイヤーの正誤チェックテスト"""

    print("=" * 60)
    print("🔍 正誤チェック機能テスト")
    print("=" * 60)

    # API確認
    providers = get_available_providers()
    print(f"\n📡 利用可能なAPI:")
    for name, available in providers.items():
        status = "✅" if available else "❌"
        print(f"  {status} {name}")

    if not any(providers.values()):
        print("\n❌ APIキーが設定されていません")
        print("~/.env.local に PERPLEXITY_API_KEY または GOOGLE_API_KEY を設定してください")
        return

    # テスト対象（実在のサービス）
    test_cases = [
        {
            "player_name": "楽天カード",
            "official_url": "https://www.rakuten-card.co.jp/",
            "company_name": "楽天カード株式会社",
            "industry": "クレジットカード",
        },
    ]

    # バリデーター作成（Perplexityを優先 - Web検索能力が高い）
    try:
        from core.llm_client import LLMClient
        # Perplexityを優先で使用
        if providers.get("perplexity"):
            llm = LLMClient(provider="perplexity")
            validator = PlayerValidator(llm_client=llm, model="sonar-pro")
            print("\n📌 使用API: Perplexity (sonar-pro)")
        elif providers.get("gemini"):
            llm = LLMClient(provider="gemini")
            validator = PlayerValidator(llm_client=llm, model="gemini-2.5-flash")
            print("\n📌 使用API: Gemini (gemini-2.5-flash)")
    except Exception as e:
        print(f"\n❌ バリデーター作成エラー: {e}")
        return

    for case in test_cases:
        print(f"\n{'='*60}")
        print(f"📋 テスト対象: {case['player_name']}")
        print(f"{'='*60}")
        print(f"  URL: {case['official_url']}")
        print(f"  事業者: {case['company_name']}")
        print(f"  業界: {case['industry']}")

        print("\n🔄 チェック実行中...")

        try:
            result = await validator.validate_player(
                player_name=case["player_name"],
                official_url=case["official_url"],
                company_name=case["company_name"],
                industry=case["industry"],
            )

            print(f"\n📊 チェック結果:")
            print(f"  アラートレベル: {result.alert_level.value}")
            print(f"  ステータス: {result.status.value}")
            print(f"  変更タイプ: {result.change_type.value}")
            print(f"  信頼度: {result.confidence * 100:.0f}%")
            print(f"  要手動確認: {'はい' if result.needs_manual_review else 'いいえ'}")

            if result.player_name_original != result.player_name_current:
                print(f"  名称変更: {result.player_name_original} → {result.player_name_current}")

            if result.change_details:
                print(f"  変更内容:")
                for detail in result.change_details:
                    print(f"    - {detail}")

            if result.news_summary:
                print(f"  関連ニュース: {result.news_summary}")

            if result.source_urls:
                print(f"  情報ソース:")
                for url in result.source_urls[:3]:
                    print(f"    - {url}")

        except Exception as e:
            print(f"\n❌ エラー: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("✅ テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_single_validation())
