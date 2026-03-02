# プレイヤーリスト調査システム v7.0

オリコン業務向けの**プレイヤーリスト調査・正誤チェック自動化ツール**。

## 主な機能

### 1. プレイヤーの最新動向（v7.0 統合タブ）
3つのサブタブで既存リストの更新を一括管理:
- **変更点調査**: 撤退・統合・名称変更の自動検出（Gemini API）
- **新規参入検出**: 既存リストにない新規参入企業を自動検索
- **最新版リスト作成**: 調査結果を統合し最新版リストをエクスポート
- **業界定義**: 任意で業界の範囲・除外条件を指定しAI判定精度を向上

### 2. カテゴリチェック（テンプレート方式）
- **調査テンプレート管理**: 作成・保存・再利用・インポート/エクスポート
- 組み込みテンプレート: 動画配信ジャンル、クレカブランド、8地方区分、47都道府県
- **判定基準（context）**: LLMに具体的な判定ガイダンスを注入可能
- バッチプロンプト方式でコスト最適化
- カスタム入力（保存なし）にも対応

### 3. 店舗・教室調査
- AI調査（推奨）: LLMによるWeb検索ベースの調査
- スクレイピング: サイト直接クローリング（3段階戦略）
- ハイブリッド: AI調査 + スクレイピング補完

### 4. 3段階チェック（ワークフロー）
- Phase 1: 実査前チェック（正誤全件 + 新規参入 + 属性全件）
- Phase 2: ランキング確定時チェック（正誤全件 + 属性変更分）
- Phase 3: 発表前チェック（CRITICALのみ再検証 + 最終確認）

---

## クイックスタート

### ローカル実行

```bash
# 依存パッケージインストール
pip install -r requirements.txt

# APIキーを設定（~/.env.local）
echo "GOOGLE_API_KEY=AIzaSy-xxxxx" >> ~/.env.local

# 起動
streamlit run app_v5.py
```

### Streamlit Cloud（デプロイ済み）

Settings → Secrets に以下を設定:

```toml
GOOGLE_API_KEY = "AIzaSy-xxxxx"
APP_PASSWORD   = "チームで決めたパスワード"
```

アクセス時はパスワード入力画面が表示されます。

| ファイル | 説明 |
|----------|------|
| `start.bat` | ランチャー（メニュー選択式） |
| `start_v5.bat` | v5/v6 統合GUI起動 |
| `install.bat` | 初回セットアップ |
| `run_tests.bat` | テスト実行 |

---

## アラートレベル（正誤チェック）

| レベル | 意味 | 対応 |
|--------|------|------|
| 🔴 緊急 | 撤退・統合 | 即時リスト更新 |
| 🟡 警告 | 名称変更 | リスト更新推奨 |
| 🟢 情報 | URL変更等 | 参考情報 |
| ✅ 正常 | 変更なし | アクション不要 |

---

## ファイル構成

```
プレイヤーリスト作成/
├── app_v5.py                    # 統合GUI (全4タブ, v7.0)
│
├── core/                        # コアモジュール
│   ├── async_helpers.py         # 非同期ヘルパー (run_async, 動的並列化)
│   ├── excel_handler.py         # Excel読み書き (load_multiple対応)
│   ├── llm_client.py            # LLMクライアント (Gemini)
│   ├── llm_cache.py             # LLMレスポンスキャッシュ (TTL付き)
│   ├── sanitizer.py             # 入力サニタイザー
│   ├── safe_parse.py            # 安全な型変換
│   ├── attribute_presets.py     # 属性調査プリセット (後方互換)
│   ├── investigation_templates.py # 調査テンプレート管理 (v6.2)
│   ├── postal_prefecture.py     # 郵便番号→都道府県変換
│   ├── check_history.py         # チェック履歴管理 + 差分計算
│   ├── check_workflow.py        # 3段階ワークフロー管理
│   ├── llm_schemas.py           # pydantic LLMレスポンススキーマ (v6.5)
│   └── logger.py                # ロギング設定 (日次ローテーション → Logs/)
│
├── investigators/               # 調査モジュール (全て definition 対応)
│   ├── base.py                  # データ型定義
│   ├── player_validator.py      # 正誤チェッカー
│   ├── store_investigator.py    # 店舗調査エンジン
│   ├── attribute_investigator.py # 汎用調査エンジン (v6.2 context対応)
│   ├── newcomer_detector.py     # 新規参入検出
│   └── player_list_generator.py # 0ベースリスト生成 (v6.5)
│
├── ui/                          # UIモジュール (v7.0 4タブ構成)
│   ├── common.py                # 共通コンポーネント (number_input_with_max等)
│   ├── player_trend_tab.py      # プレイヤーの最新動向タブ (v7.0 統合)
│   ├── attribute_tab.py         # カテゴリチェックタブ
│   ├── store_tab.py             # 店舗・教室調査タブ
│   └── workflow_tab.py          # 3段階チェックタブ
│
├── templates/                   # 調査テンプレート (v6.2)
│   ├── builtin/                 # 組み込みテンプレート (git管理)
│   └── user/                    # ユーザー作成 (gitignore)
│
├── store_scraper_v3.py          # 店舗スクレイピングエンジン
│
├── archive/                     # 旧ファイルアーカイブ
│   └── ui/                      # v7.0で統合された旧タブ
│       ├── newcomer_tab.py
│       ├── generator_tab.py
│       └── validation_tab.py
│
├── Logs/                        # エラーログ (gitignore, 30日保持)
│   └── app.log                  # 日次ローテーション
│
├── tests/                       # テストスイート (pytest, 405件)
│   ├── conftest.py              # 共通フィクスチャ
│   ├── test_async_helpers.py
│   ├── test_investigation_templates.py
│   ├── test_attribute_investigator.py
│   ├── test_check_history.py
│   ├── test_check_workflow.py
│   ├── test_excel_handler.py
│   ├── test_llm_cache.py
│   ├── test_llm_client.py
│   ├── test_newcomer_detector.py
│   ├── test_player_validator.py
│   ├── test_postal_prefecture.py
│   ├── test_safe_parse.py
│   ├── test_sanitizer.py
│   ├── test_store_investigator.py
│   ├── test_store_scraper_pages_visited.py
│   ├── test_base.py                 # 判定ロジックテスト (v6.5)
│   └── test_llm_schemas.py          # pydanticスキーマテスト (v6.5)
│
├── HANDOVER.md                  # 引き継ぎドキュメント
├── pytest.ini                   # pytest設定
└── requirements.txt             # 依存関係
```

---

## 必要なAPIキー

`~/.env.local` に設定：

```bash
GOOGLE_API_KEY=AIzaSy-xxxxx    # Gemini API（Google検索グラウンディング対応）
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
| **v7.0** | 2026-03-02 | UI大改修: タブ統合(6→4)、定義フィールド追加、全件ボタン、プレイヤーの最新動向統合タブ(変更点調査+新規参入+最新版リスト作成) |
| **v6.6.1** | 2026-03-02 | Excelシート複数選択対応（selectbox→multiselect）、load_multiple()メソッド追加 |
| **v6.6** | 2026-03-02 | 複数シート対応（Excel selectbox）、DEFAULT_MODEL=gemini-2.5-pro一元化、店舗調査モード簡略化、UI改善 |
| **v6.5.1** | 2026-03-02 | コスト表示の日本円化（150円/USD固定）、正誤チェック解析失敗のデバッグログ追加 |
| **v6.5** | 2026-02-27 | P2修正（industry型明確化、判定ロジック一元化、pydanticスキーマ）+ 新機能（コスト表示、API精度向上、0ベースリスト生成）、テスト405件 |
| **v6.4** | 2026-02-26 | 信頼度削除・業界自動推測・モード説明・ロギング・AI-2G指摘修正 |
| **v6.3** | 2026-02-24 | Perplexity→Gemini一本化（Google検索グラウンディング対応） |
| **v6.2** | 2026-02-17 | 汎用調査エンジン（テンプレート管理、context対応、UI統合、地理系テンプレート追加）、テスト367件 |
| **v6.1** | 2026-02-10 | UI分離(validation_tab/store_tab)、LLMキャッシュ、動的並列化、住所精度改善、テスト325件 |
| **v6.0.1** | 2026-02-09 | 18件バグ修正、safe_parse/async_helpers追加、テスト213件 |
| **v6.0** | 2026-02-09 | 4機能追加（属性調査、新規参入検出、3段階チェック、UIモジュール化） |
| **v5.1** | 2026-02-07 | 店舗調査精度向上、属性調査バッチ化 |
| **v5.0** | 2026-02-06 | v3+v4統合、属性調査・新規参入検出・3段階チェック追加 |
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
