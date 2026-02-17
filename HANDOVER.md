# プレイヤーリスト調査システム - Handover Document

> **最終更新**: 2026-02-17
> **担当**: Claude Opus 4.6 + たいむさん
> **バージョン**: v6.2.1

## セッション: 2026-02-17 (2)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | /技術参謀 全体分析 → Important 3件を並列修正 |
| **変更ファイル** | `store_scraper_v3.py`, `core/async_helpers.py` |
| **テスト** | 367件全パス（回帰なし） |
| **ステータス** | 完了 |

### 変更詳細
- **/技術参謀 分析**: 全24ファイル(~9,100行)を3レンズ(偵察/査閲/策定)で分析 → 🟡 CONDITIONAL (F=0, I=3, R=8, E=3)
- **[I1] 例外処理の具体化** (`store_scraper_v3.py`): `except Exception` 15箇所を具体的な例外型に変更、握り潰し8箇所に `logger.warning()` 追加、セーフティネット3箇所は `logger.error(exc_info=True)` 追加
- **[I2] スレッドプールリーク修正** (`core/async_helpers.py`): グローバル即時生成 → `_get_executor()` 遅延初期化 + `atexit` 自動シャットダウン + `cleanup()` 公開API新設
- **[I3] 郵便番号DRY違反解消** (`store_scraper_v3.py`): ~96行の重複 `POSTAL_PREF_MAP` 削除、`core.postal_prefecture` からの import に統一
- **判定更新**: 🟡 CONDITIONAL → 🟢 APPROVE

### 次回やること / 残課題
- [R] `import_from_excel()` の Workbook を try/finally でクローズ
- [R] `render_investigation_tab()` の関数分割（425行 → 4関数）
- [R] 一時ファイル作成ヘルパーの共通化
- [R] `store_scraper_v3.py` Long Function 分割 (`_scrape_static` 100行+, `_scrape_playwright` 150行+)
- [R] Deep Nesting 解消 (`_scrape_playwright` 4-5階層)
- [R] Magic Number 定数化 (timeout=10, default=0.5 等)
- [R] `excel_handler.py` SRP違反解消（741行に4責務混在 → パッケージ分割）
- [E] テンプレートIDのASCIIスラッグ化（CI/CD環境対応）
- [E] contextフィールドのサニタイズ強化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] Dataclass → Pydantic v2 統一
- [E] LLMClient の AsyncContextManager 化

---

## セッション: 2026-02-17

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v6.2 汎用調査エンジン — テンプレート管理 + context対応 + UI統合 |
| **変更ファイル** | 10 modified + 6 new (core/investigation_templates.py, templates/builtin/*.json, tests/test_investigation_templates.py) |
| **テスト** | 367件全パス（v6.1の325件 + 新規42件、回帰なし） |
| **ステータス** | 完了 |

### 変更詳細
- 調査テンプレートデータモデル新規作成（InvestigationTemplate + TemplateManager）
- 組み込みテンプレート4種（動画配信ジャンル、クレカブランド、8地方区分、47都道府県）
- attribute_investigator.py に context パラメータ追加（LLMプロンプトに判定基準注入）
- ui/attribute_tab.py を汎用調査タブに大幅リファクタ（テンプレート選択・管理UI）
- app_v5.py タブ名称変更、workflow_tab.py ラベル更新
- /審査官 レビュー → 🟡 CONDITIONAL（3件対応済み）
- /技術参謀 レビュー → 🟢 APPROVE（F=0, I=0, R=3, E=3）

### 次回やること / 残課題
- [R] `import_from_excel()` の Workbook を try/finally でクローズ
- [R] `render_investigation_tab()` の関数分割（425行 → 4関数）
- [R] 一時ファイル作成ヘルパーの共通化
- [E] テンプレートIDのASCIIスラッグ化（CI/CD環境対応）
- [E] contextフィールドのサニタイズ強化
- [E] カテゴリ値対応（boolean以外の多値分類）

---

## 1. プロジェクト概要

### 目的
オリコン業務における**プレイヤーリストの調査・正誤チェック**を自動化するシステム。

### 対象業界
| 業界 | プレイヤー数 | ファイル |
|------|-------------|----------|
| クレジットカード | 539件 | 【2026年_クレジットカード】プレイヤーリスト.xlsx |
| 動画配信サービス | 36件 | 【2025年_定額制動画配信サービス】プレイヤーリスト.xlsx |
| 中古車販売店 | 16件 | 【20241217修正】2025_中古車販売店_プレイヤーリスト.xlsx |

### 主な機能
1. **プレイヤー正誤チェック** (v4.0)
   - 撤退・統合・名称変更の自動検出
   - Perplexity/Gemini APIによる最新情報取得
   - アラートレベル別レポート出力

2. **汎用調査（テンプレート方式）** (v6.2 NEW)
   - 調査テンプレート管理（作成・保存・再利用・インポート/エクスポート）
   - 組み込みテンプレート: 動画配信ジャンル、クレカブランド、8地方区分、47都道府県
   - 判定基準（context）をLLMプロンプトに注入可能
   - バッチプロンプト方式でコスト最適化
   - カスタム入力（保存なし）にも対応

3. **店舗・教室の都道府県別調査（従来版）** (v3.0)
   - マルチ戦略スクレイピング + AI調査
   - 静的HTML → ブラウザ自動化 → AI推論
   - ※ v6.2で汎用調査に地理系テンプレートを追加。スクレイピング機能はこのタブで引き続き利用可能

4. **新規参入プレイヤー自動検出** (v6.0)
   - LLM提案 → URL自動検証 → 手動確認の3ステップ
   - ハルシネーション対策（URL検証 + 信頼度スコアリング）
   - 自動追加なし（候補提示のみ）

5. **3段階チェック体制** (v6.0)
   - 実査前 → 確定時 → 発表前のワークフロー管理
   - フェーズ間差分レポート
   - チェック履歴の保存・閲覧

---

## 2. システム構成

```
プレイヤーリスト作成/
├── app_v5.py              # 統合GUI（Streamlit）★メイン
├── app_v4.py              # 正誤チェックGUI（旧）
├── app_v3.py              # 店舗調査GUI（旧）
│
├── core/                  # コアモジュール
│   ├── __init__.py
│   ├── async_helpers.py   # 非同期ヘルパー・動的並列化 (v6.0.1)
│   ├── excel_handler.py   # Excel読み書き + AttributeInvestigationExporter
│   ├── llm_client.py      # LLMクライアント（Perplexity/Gemini）
│   ├── llm_cache.py       # LLMレスポンスキャッシュ (TTL付き) (v6.1)
│   ├── sanitizer.py       # 入力サニタイザー共通化 (v6.0)
│   ├── safe_parse.py      # 安全な型変換 (v6.0.1)
│   ├── attribute_presets.py # 属性プリセット定義 (v6.0)
│   ├── investigation_templates.py # 調査テンプレート管理 (v6.2 NEW)
│   ├── postal_prefecture.py # 郵便番号→都道府県変換 (v6.1)
│   ├── check_history.py   # チェック履歴管理 + 差分計算 (v6.0)
│   └── check_workflow.py  # 3段階ワークフロー管理 (v6.0)
│
├── investigators/         # 調査モジュール
│   ├── __init__.py
│   ├── base.py            # データ型定義（AlertLevel, AttributeInvestigationResult等）
│   ├── player_validator.py # 正誤チェッカー
│   ├── store_investigator.py # 店舗調査
│   ├── attribute_investigator.py # 汎用調査エンジン (v6.0, v6.2 context対応)
│   └── newcomer_detector.py  # 新規参入検出 (v6.0 NEW)
│
├── ui/                    # UIモジュール (v6.0 NEW)
│   ├── __init__.py
│   ├── common.py          # 共通UIコンポーネント
│   ├── validation_tab.py  # 正誤チェックタブ (v6.1 NEW)
│   ├── store_tab.py       # 店舗調査タブ（従来版） (v6.1)
│   ├── attribute_tab.py   # 汎用調査タブ (v6.2 リファクタ)
│   ├── newcomer_tab.py    # 新規参入検出タブ
│   └── workflow_tab.py    # 3段階チェックタブ
│
├── templates/             # 調査テンプレート (v6.2 NEW)
│   ├── builtin/           # 組み込みテンプレート (git管理)
│   └── user/              # ユーザー作成 (gitignore)
│
├── tests/                 # テスト (367件)
│   ├── conftest.py
│   ├── test_investigation_templates.py # テンプレートテスト (v6.2 NEW)
│   ├── test_async_helpers.py    # 非同期ヘルパーテスト
│   ├── test_attribute_investigator.py # 汎用調査テスト
│   ├── test_check_history.py    # 履歴管理テスト
│   ├── test_check_workflow.py   # ワークフローテスト
│   ├── test_excel_handler.py    # Excel処理テスト
│   ├── test_llm_cache.py        # LLMキャッシュテスト (v6.1 NEW)
│   ├── test_llm_client.py       # LLMクライアントテスト
│   ├── test_newcomer_detector.py # 新規参入検出テスト
│   ├── test_player_validator.py # 正誤チェックテスト
│   ├── test_postal_prefecture.py # 郵便番号テスト (v6.1 NEW)
│   ├── test_safe_parse.py       # 安全な型変換テスト
│   ├── test_sanitizer.py        # サニタイザーテスト
│   ├── test_store_investigator.py # 店舗調査テスト
│   └── test_store_scraper_pages_visited.py # ページ訪問カウントテスト
│
├── docs/                  # ドキュメント・本番データ
│   └── プレイヤーリスト/  # ★本番Excel（gitignore対象）
│
├── 出力/                  # 生成ファイル（gitignore対象）
│   └── history/           # チェック履歴 (v6.0 NEW)
│
├── requirements.txt       # 依存関係
└── .gitignore             # Git除外設定
```

---

## 3. 環境設定

### 3.1 必要なAPIキー

`~/.env.local` に以下を設定：

```env
PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxxxxxx
GOOGLE_API_KEY=AIzaxxxxxxxxxxxxxxxxxxxxxxx
```

**重要**: システム環境変数に古いキーがある場合、`.env.local` が優先されます（`override=True`）

### 3.2 依存パッケージ

```bash
pip install -r requirements.txt
```

主要パッケージ:
- `streamlit` - GUI
- `openpyxl` - Excel操作
- `requests` - HTTP通信
- `python-dotenv` - 環境変数
- `google-genai` - Gemini API
- `playwright` - ブラウザ自動化（オプション）

---

## 4. 起動方法

### v6.1（統合版）★推奨
```bash
streamlit run app_v5.py
```

---

## 5. 機能詳細

### 5.1 正誤チェック

#### アラートレベル
| レベル | 意味 | 対応 |
|--------|------|------|
| 🔴 緊急 | 撤退・統合 | 即時リスト更新 |
| 🟡 警告 | 名称変更 | リスト更新推奨 |
| 🟢 情報 | URL変更等 | 参考情報 |
| ✅ 正常 | 変更なし | アクション不要 |
| ⚠️ 要確認 | 判断不能 | 手動確認必要 |

### 5.2 汎用調査（v6.2 リファクタ）

#### 調査テンプレート
| テンプレート | カテゴリ | 属性数 | 推奨バッチ | 推定コスト |
|-------------|---------|--------|-----------|-----------|
| 動画配信_ジャンル | 属性系 | 15属性 | 5社/回 | ~$0.24（36件） |
| クレカ_ブランド | 属性系 | 7属性 | 10社/回 | ~$1.62（539件） |
| 地方区分_8地方 | 地理系 | 8属性 | 10社/回 | コスト同等 |
| 都道府県_47 | 地理系 | 47属性 | 3社/回 | 件数次第 |
| カスタム | - | ユーザー定義 | 自動決定 | 件数次第 |

#### テンプレート管理
- **作成**: テンプレート名、カテゴリ、属性リスト、判定基準（context）を定義
- **保存**: `templates/user/` にJSON永続化（再利用可能）
- **インポート**: テキスト（カンマ/改行区切り）またはExcel（第1列）から属性を取り込み
- **エクスポート**: テンプレートをJSON形式で書き出し
- **判定基準（context）**: LLMに具体的な判定ガイダンスを渡す（例: 「有償=年会費が発生するもの」）

#### 出力形式
- **マトリクス表示**: ○/×/? のテーブル
- **Excel**: 色分け付き（緑=○、赤=×、黄=?）
- **CSV**: 全データエクスポート

### 5.3 新規参入検出（v6.0 NEW）

#### ハルシネーション対策
| ステップ | 内容 |
|---------|------|
| 1. LLM提案 | 業界+既存リスト → 候補生成 |
| 2. URL検証 | HEAD リクエストで公式サイト存在確認 |
| 3. 信頼度調整 | URL不明 → 信頼度50%減 |
| 4. 手動確認 | チェックボックスで選択 → エクスポート |

#### 検証バッジ
| バッジ | 意味 |
|--------|------|
| 🟢 URL検証済み | 公式サイト存在確認OK |
| 🔴 URL不明 | URLにアクセスできなかった（要注意） |
| 🟡 未検証 | URLが提供されていない |

### 5.4 3段階チェック体制（v6.0 NEW）

| フェーズ | タイミング | 実行内容 | 差分基準 |
|----------|----------|----------|---------|
| 実査前 | 調査設計時 | 正誤全件 + 新規参入 + 属性全件 | ベースライン作成 |
| 確定時 | 集計後 | 正誤全件 + 属性（変更ありのみ） | 実査前との差分 |
| 発表前 | 公開直前 | CRITICALのみ再検証 + 最終確認 | 確定時との差分 |

---

## 6. 変更履歴

### v6.2 (2026-02-17) - 汎用調査エンジン

#### 調査テンプレート管理
- `core/investigation_templates.py` - InvestigationTemplate + TemplateManager 新規作成
- テンプレートの作成・保存・削除・インポート/エクスポート
- JSON永続化（`templates/builtin/` git管理 + `templates/user/` gitignore）
- 組み込みテンプレート4種: 動画配信ジャンル、クレカブランド、8地方区分、47都道府県

#### プロンプトエンジン強化
- `investigators/attribute_investigator.py` に `context` パラメータ追加
- 判定基準（context）をLLMプロンプトに「■判定基準」セクションとして注入
- `investigate_batch()`, `investigate_single()`, `_build_batch_prompt()` 全メソッド対応

#### UI統合
- `ui/attribute_tab.py` → `render_investigation_tab()` にリネーム（後方互換ラッパー維持）
- テンプレート選択・管理UI追加（カテゴリ別グループ化、作成/削除/インポート）
- 「カスタム（保存なしで調査）」オプション維持
- バッチサイズ上書きオプション追加
- `app_v5.py`: 「📊 属性調査」→「📊 汎用調査」、「🏪 店舗調査」→「🏪 店舗調査（従来版）」
- `ui/workflow_tab.py`: 表示ラベル更新

#### テスト
- `test_investigation_templates.py` (34件) + context テスト (8件) 新規追加
- 合計: 367件（v6.1の325件 → 367件）

### v6.1 (2026-02-10) - UI分離・品質改善

#### UI分離
- `ui/validation_tab.py` - 正誤チェックUIをapp_v5.pyから分離
- `ui/store_tab.py` - 店舗調査UIをapp_v5.pyから分離
- attribute_tab.py のパターンに準拠した統一設計

#### LLMキャッシュ
- `core/llm_cache.py` - TTL付きインメモリキャッシュ（スレッドセーフ）
- 属性調査・店舗調査（AIモード）で有効化、正誤チェック・新規参入検出は対象外（opt-in方式）

#### 動的並列化
- `core/async_helpers.py` に `optimal_concurrency()` 追加
- プレイヤー数に応じた最適並列数を自動決定

#### 住所精度改善
- `core/postal_prefecture.py` - 郵便番号上位3桁→都道府県マッピング
- 全47都道府県対応、〒付き・スペース付き形式に対応

#### テスト
- `test_llm_cache.py` (18件) + `test_postal_prefecture.py` (26件+47パラメータ化) 追加
- 合計: 325件（v6.0.1の213件 → 310件 → 325件）

### v6.0.1 (2026-02-09) - バグ修正
- 18件のバグ修正
- `core/safe_parse.py` 追加（安全な型変換）
- `core/async_helpers.py` 追加（非同期ヘルパー）
- テスト213件

### v6.0 (2026-02-09) - 4機能追加

#### Phase 0: 共通基盤
- `core/sanitizer.py` - 入力サニタイザーの共通化
- `player_validator.py`, `store_investigator.py` の重複コードを統合

#### Phase 1: 属性調査エンジン
- `investigators/attribute_investigator.py` - バッチプロンプト方式
- `core/attribute_presets.py` - 動画配信ジャンル/クレカブランドのプリセット
- `core/excel_handler.py` - `AttributeInvestigationExporter` 追加

#### Phase 2: 新規参入検出
- `investigators/newcomer_detector.py` - LLM + URL自動検証
- 信頼度スコアリング（URL不明時50%ペナルティ）

#### Phase 3: 3段階チェック体制
- `core/check_history.py` - 履歴管理 + 差分計算
- `core/check_workflow.py` - フェーズ管理
- `difflib.SequenceMatcher` による名称類似度判定

#### Phase 4: UI統合
- `ui/` ディレクトリ新設 - UIモジュール分割
- `app_v5.py` に3つの新タブ追加
- 5機能のラジオボタン切り替え

#### テスト
- 新規テスト: 114件（sanitizer 28 + attribute 30 + newcomer 17 + history 21 + workflow 18）
- 既存テスト: 97件
- 合計: 211件

### v5.1 (2026-02-05) - 店舗調査精度向上
- プロンプト最適化で「?」率を70% → 30%以下に改善
- AI調査モード選択UI追加（高速/精密）

### v5.0 (2026-02-05) - v3+v4統合
- `app_v5.py` - 正誤チェック + 店舗調査を統合GUI化

### v4.0 (2026-02-04) - 正誤チェック
- `core/`, `investigators/` モジュール群の新規実装
- セキュリティ改善（APIキー非表示、入力サニタイズ）

---

## 7. 既知の課題・今後の拡張

### 7.1 改善候補
- [x] バッチ処理の並列化強化（v6.1: 動的並列化 optimal_concurrency 実装済み）
- [x] キャッシュ機能（v6.1: LLMCache 実装済み、TTL付きインメモリキャッシュ）
- [x] 汎用調査エンジン（v6.2: テンプレート管理 + context対応 実装済み）
- [ ] Slack/Teams通知連携
- [ ] カテゴリ値対応（boolean以外の多値分類、例: プレミアム/スタンダード/なし）
- [ ] テンプレートIDのASCIIスラッグ化（CI/CD環境対応）
- [ ] contextフィールドのサニタイズ強化

### 7.2 注意事項
- Perplexity APIは従量課金（1件約$0.01-0.05）
- 大量チェック時はコスト注意（属性調査のコスト概算UI参照）
- 信頼度60%未満は手動確認推奨
- 新規参入候補は**必ず手動確認してからエクスポート**

---

## 8. トラブルシューティング

### Q: APIエラー 401 Unauthorized
**A**: `.env.local` のキーが古い可能性。
- `~/.env.local` を確認
- システム環境変数に古いキーがないか確認

### Q: Excelが読み込めない
**A**: ヘッダー行の位置を確認。
- 4行目にヘッダーがある形式に対応
- 「サービス名」「事業者名」列を自動検出

### Q: Gemini APIエラー
**A**: モデル名が古い可能性。
- `gemini-2.5-flash` を使用（2.0は廃止予定）
- `google-genai` パッケージを更新

### Q: asyncio.run() エラー
**A**: Streamlit環境でasyncioループが衝突する場合あり。
- 直接 `asyncio.run()` で呼び出し（`nest_asyncio` 不要）
- Playwright併用時は非同期ループの競合に注意

---

## 9. コンタクト

- **開発**: Claude Opus 4.6 (AI)
- **運用**: たいむさん
- **リポジトリ**: プライベート（GitHub）

---

*このドキュメントは引き継ぎ・メンテナンス用です。*
