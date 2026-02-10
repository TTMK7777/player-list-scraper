#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Excel読み込みテスト
"""

import sys
import io
from pathlib import Path

# Windows環境でのUnicode出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# モジュールパスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_handler import ExcelHandler

def test_load():
    """Excelファイルの読み込みテスト"""
    # テスト対象ファイル
    test_files = [
        "docs/プレイヤーリスト/【2026年_クレジットカード】プレイヤーリスト.xlsx",
        "docs/プレイヤーリスト/【2025年_定額制動画配信サービス】プレイヤーリスト.xlsx",
        "docs/プレイヤーリスト/【20241217修正】2025_中古車販売店_プレイヤーリスト.xlsx",
    ]

    for file_path in test_files:
        full_path = Path(__file__).parent.parent / file_path
        if not full_path.exists():
            print(f"❌ ファイルが見つかりません: {file_path}")
            continue

        print(f"\n{'='*60}")
        print(f"📂 ファイル: {full_path.name}")
        print(f"{'='*60}")

        try:
            handler = ExcelHandler()
            players = handler.load(full_path)

            print(f"✅ ヘッダー行: {handler.header_row}")
            print(f"✅ 検出された列: {handler.get_column_names()}")
            print(f"✅ プレイヤー数: {len(players)}件")

            # 先頭5件を表示
            print(f"\n📋 データサンプル（先頭5件）:")
            for i, player in enumerate(players[:5], 1):
                print(f"  {i}. {player.player_name}")
                if player.company_name:
                    print(f"      事業者: {player.company_name}")
                if player.official_url:
                    print(f"      URL: {player.official_url[:50]}...")

        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test_load()
