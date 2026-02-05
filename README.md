# プレイヤーリスト調査システム

オリコン業務向けの**プレイヤーリスト調査・正誤チェック自動化ツール**。

## 主な機能

### 1. プレイヤー正誤チェック（v4.0 NEW）
- 撤退・統合・名称変更の**自動検出**
- Perplexity/Gemini APIで**最新情報を取得**
- アラートレベル別レポート出力（Excel/CSV）

### 2. 店舗・教室の都道府県別調査（v3.0）
- マルチ戦略スクレイピング
- 静的HTML → ブラウザ自動化 → AI推論

---

## クイックスタート

### 1. 環境設定

```bash
# 依存パッケージインストール
pip install -r requirements.txt

# APIキーを設定（~/.env.local）
echo "PERPLEXITY_API_KEY=pplx-xxxxx" >> ~/.env.local
echo "GOOGLE_API_KEY=AIzaSy-xxxxx" >> ~/.env.local
```

### 2. 起動（バッチファイル）

| ファイル | 説明 |
|----------|------|
| `start.bat` | ランチャー（メニュー選択式） |
| `start_v4.bat` | v4.1 正誤チェック起動 ★推奨 |
| `start_v3.bat` | v3.0 店舗調査起動 |
| `install.bat` | 初回セットアップ |
| `run_tests.bat` | テスト実行 |

**ダブルクリックで起動できます！**

```bash
# コマンドラインで起動する場合
streamlit run app_v4.py  # 正誤チェック
streamlit run app_v3.py  # 店舗調査
```

---

## 正誤チェック機能（v4.0）

### 対応プレイヤーリスト

| 業界 | 件数 | ファイル |
|------|------|----------|
| クレジットカード | 539件 | 【2026年_クレジットカード】プレイヤーリスト.xlsx |
| 動画配信サービス | 36件 | 【2025年_定額制動画配信サービス】プレイヤーリスト.xlsx |
| 中古車販売店 | 16件 | 【20241217修正】2025_中古車販売店_プレイヤーリスト.xlsx |

### アラートレベル

| レベル | 意味 | 対応 |
|--------|------|------|
| 🔴 緊急 | 撤退・統合 | 即時リスト更新 |
| 🟡 警告 | 名称変更 | リスト更新推奨 |
| 🟢 情報 | URL変更等 | 参考情報 |
| ✅ 正常 | 変更なし | アクション不要 |

### 使用例

```python
from investigators import PlayerValidator
from core import ExcelHandler

# Excelからプレイヤー読み込み
handler = ExcelHandler()
players = handler.load("プレイヤーリスト.xlsx")

# 正誤チェック実行
validator = PlayerValidator()
results = await validator.validate_batch(players, industry="クレジットカード")
```

---

## 店舗調査機能（v3.0）

### 3段階戦略

```
┌─────────────────────────────────────────────────────┐
│  戦略1: 静的HTML解析（高速・低コスト）              │
│  └─ BeautifulSoup + LLM抽出                        │
├─────────────────────────────────────────────────────┤
│  戦略2: ブラウザ自動操作（JavaScript対応）          │
│  └─ Playwright でレンダリング                      │
├─────────────────────────────────────────────────────┤
│  戦略3: AI推論（最終手段）                          │
│  └─ 内部API推測 + Perplexity検索                   │
└─────────────────────────────────────────────────────┘
```

### テスト結果

| サイト | 公式発表 | 抽出結果 | 一致率 |
|--------|----------|----------|--------|
| applenet.co.jp | 263店舗 | 263店舗 | 100% |
| meikogijuku.jp | ~2,000教室 | 1,648教室 | ~82% |

---

## ファイル構成

```
プレイヤーリスト作成/
├── app_v4.py              # 正誤チェックGUI ★メイン
├── app_v3.py              # 店舗調査GUI
│
├── core/                  # コアモジュール
│   ├── excel_handler.py   # Excel読み書き
│   └── llm_client.py      # LLMクライアント
│
├── investigators/         # 調査モジュール
│   ├── base.py            # データ型定義
│   └── player_validator.py # 正誤チェッカー
│
├── tests/                 # テストスイート（pytest）
│   ├── conftest.py        # 共通フィクスチャ
│   ├── test_excel_handler.py
│   ├── test_llm_client.py
│   └── test_player_validator.py
│
├── archive/               # 旧バージョン（git除外）
│   └── legacy_versions/   # v1/v2 ファイル
│
├── store_scraper_v3.py    # 店舗スクレイピング
├── docs/プレイヤーリスト/ # 本番データ（git除外）
├── HANDOVER.md            # 引き継ぎドキュメント
├── pytest.ini             # pytest設定
└── requirements.txt       # 依存関係
```

---

## 必要なAPIキー

`~/.env.local` に設定：

```bash
PERPLEXITY_API_KEY=pplx-xxxxx  # 正誤チェックに推奨
GOOGLE_API_KEY=AIzaSy-xxxxx    # Gemini用（バックアップ）
```

---

## テスト実行

```bash
# 全テスト実行
pytest tests/ -v

# カバレッジ付き
pytest tests/ --cov=. --cov-report=html
```

---

## バージョン履歴

| Ver | 日付 | 変更内容 |
|-----|------|---------|
| **v4.1** | 2026-02-05 | コード品質改善、pytest導入、フォルダ整理 |
| **v4.0** | 2026-02-04 | プレイヤー正誤チェック機能、セキュリティ改善 |
| v3.0 | 2025-12-25 | マルチ戦略スクレイピング、都道府県対応 |
| v2.0 | 2025-12-24 | 多段階ページ巡回、LLM抽出 |
| v1.0 | 2025-12-24 | 初版（Playwright + Gemini） |

---

## ライセンス

Private - Internal Use Only

---

詳細は [HANDOVER.md](./HANDOVER.md) を参照
