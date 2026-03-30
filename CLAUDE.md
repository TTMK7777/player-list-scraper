# player-list-scraper - 仕様駆動ワークフロー

## 概要
プレイヤーリスト調査システム v7.2 -- オリコン業務向けのプレイヤーリスト調査・正誤チェック自動化ツール。

## 仕様駆動ワークフロー
1. `spec.md` で仕様を定義
2. `specs/` 配下に機能仕様を追加
3. `plan.md` で計画を管理
4. `todo.md` でタスクを追跡
5. 実装後 `knowledge.md` / `memory.md` に知見を記録

## プロジェクト構造

| パス | 説明 |
|------|------|
| `app_v5.py` | 統合GUI (Streamlit, 全4タブ) |
| `core/` | コアモジュール（共通基盤） |
| `investigators/` | 調査モジュール（調査ロジック） |
| `ui/` | UIモジュール（タブUI） |
| `templates/` | 調査テンプレート |
| `store_scraper_v3.py` | 店舗スクレイピングエンジン |
| `tests/` | テストスイート (pytest, 522件) |
| `docs/` | ドキュメント |
| `scripts/` | ユーティリティスクリプト |
| `specs/` | 機能仕様書 |

## コード規約
- 言語: Python 3
- GUI: Streamlit
- LLM: Gemini API (`gemini-2.5-pro`, `google-genai`)
- テスト: pytest (522件)
- 型ヒント: `Optional[T]` 形式
- 非同期: `asyncio.to_thread` 統一
- ロギング: `core/logger.py`（日次ローテーション、`Logs/`）
- セキュリティ: XSS防止 (`html.escape`)、SSRF防止、プロンプトインジェクション防御
- APIキー: `~/.env.local` に `GOOGLE_API_KEY` を設定

## 起動方法
```bash
pip install -r requirements.txt
streamlit run app_v5.py
```
