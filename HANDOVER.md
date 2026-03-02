# プレイヤーリスト調査システム - Handover Document

> **最終更新**: 2026-03-02
> **担当**: Claude Opus 4.6 + たいむさん
> **バージョン**: v6.6

## セッション: 2026-03-02 (2)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v6.6: 複数シート対応 + DEFAULT_MODEL(pro)一元化 + UI改善 |
| **変更ファイル** | 17ファイル（+97行 -56行） |
| **テスト** | 405件全パス（回帰なし） |
| **品質ゲート** | moderate — プラン承認済み |
| **ステータス** | 完了 |

### 変更詳細

#### 1. DEFAULT_MODEL 定数化 (`core/llm_client.py`)
- `DEFAULT_MODEL = "gemini-2.5-pro"` 定数を新設
- `_call_gemini()` のフォールバック `"gemini-2.5-flash"` → `DEFAULT_MODEL` に置換
- **全 investigator（5個）+ store_scraper_v3 + scripts** がこの定数を参照
- コスト増はユーザー了承済み（精度向上が優先）

#### 2. 複数シート対応 (`core/excel_handler.py`)
- `get_sheet_names(file_path)` 静的メソッド追加（read_only で高速にシート名一覧取得）
- `load()` に `sheet_name` パラメータ追加（未指定時は従来通り active シート）
- 存在しないシート名指定時は `ValueError` 送出

#### 3. シート選択ヘルパー (`ui/common.py`)
- `select_sheet_if_multiple(file_path, key_prefix)` 追加
- 複数シート時のみ selectbox 表示、単一シートなら None を返す

#### 4. 5タブにシート選択UI追加
- validation_tab, newcomer_tab, store_tab, workflow_tab, attribute_tab
- 各タブの Excel アップロード処理に2行追加（`select_sheet_if_multiple` + `load(sheet_name=)`)

#### 5. 店舗調査モード選択UI簡略化 (`ui/store_tab.py`)
- 「AI調査（高速）/ AI調査（精密）」→「AI調査」に統合（DEFAULT_MODEL で一本化）
- `ai_model` 変数、`st.warning` 精密モード注意事項を削除
- `_run_investigation()` から `ai_model` 引数を削除

#### 6. UI表示改善 (`app_v5.py`)
- API接続表示: `✅ Gemini: 接続OK` → `✅ Gemini: 接続OK（モデル: gemini-2.5-pro）`
- 業界設定 help: 「入力を推奨します」のメモ追加

#### 7. テスト修正 (`tests/test_store_investigator.py`)
- `test_init` のデフォルトモデルアサーション値を `gemini-2.5-pro` に更新

### 残課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [ ] 複数シートExcel（生産性AIプレイヤーリスト.xlsx）でシート選択→正誤チェック実行を目視確認
- [ ] 単一シートExcelで従来動作が維持されることを目視確認
- (継続) [R] `excel_handler.py` SRP違反解消
- (継続) [E] テンプレートIDのASCIIスラッグ化
- (継続) [E] カテゴリ値対応（boolean以外の多値分類）
- (継続) [E] LLMClient の AsyncContextManager 化

---

## セッション: 2026-03-02

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | コスト表示の日本円化 + 正誤チェック解析失敗のデバッグログ追加 |
| **変更ファイル** | `ui/common.py`, `investigators/player_validator.py` (2ファイル, +32行 -5行) |
| **テスト** | 表示層のみの変更、既存405件に影響なし |
| **品質ゲート** | simple（表示変更+ログ追加）、省略 |
| **ステータス** | 完了 |

### 変更詳細

#### 1. コスト表示の日本円化 (`ui/common.py`)
- `USD_TO_JPY = 150` 定数を追加（固定レート）
- `display_cost_estimate()`: `約$0.450（30回 × $0.015/正誤チェック）` → `約67.5円（30回 × 2.25円/正誤チェック）`
- `display_cost_warning()`: `約$0.45（30件 × 2バッチ）` → `約67.5円（30件 × 2バッチ）`
- investigator側の `COST_PER_CALL` はUSD維持（API料金がUSD建てのため、表示層のみ変換）
- 全6タブ（generator, newcomer, store, validation, workflow, attribute）に自動反映

#### 2. 正誤チェック解析失敗のデバッグログ (`investigators/player_validator.py`)
- `logging` + `logger = getLogger(__name__)` 追加
- `_parse_response()` の2箇所にWARNINGログ追加:
  - JSON抽出失敗時: プレイヤー名、戻り値の型、raw_response（先頭2000文字）
  - pydanticバリデーション失敗時: プレイヤー名、抽出されたJSON（先頭1000文字）
- 出力先: `Logs/app.log`（既存のロギング基盤を利用）

### 調査メモ: 「LLMからの応答を解析できませんでした」問題
- **発生**: 30件中5件（Azure OpenAI Service, ナレフルチャット, AIアシスタント, Forefront AI, GitHub Copilot (法人プラン)）
- **原因箇所**: `player_validator.py:_parse_response()` → `extract_json()` が `None` を返す
- **推定原因**: Gemini `use_search=True` 時にJSON形式を無視したテキスト回答 / JSONが途中で切れる / 不正なJSON
- **次のステップ**: 再実行してログからraw_responseを確認 → 原因確定 → 対策実装（リトライ / extract_json強化 / response_mime_type等）

### 残課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [ ] 各タブのコスト日本円表示を目視確認
- (継続) [R] `excel_handler.py` SRP違反解消
- (継続) [E] テンプレートIDのASCIIスラッグ化
- (継続) [E] カテゴリ値対応（boolean以外の多値分類）
- (継続) [E] LLMClient の AsyncContextManager 化

---

## セッション: 2026-02-27

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v6.5: P2修正3件 + 新機能3件（Phase A + Phase B 一括実装） |
| **変更ファイル** | 14 modified + 6 new = 20ファイル（+365行 -136行） |
| **テスト** | 405件全パス（363既存 + 42新規、回帰なし） |
| **品質ゲート** | プラン: /取締役会 条件付きGo（I1/I2反映済み） |
| **ステータス** | 完了 |

### Phase A: P2修正（v6.4 AI-2G指摘の対応）

#### 課題2: industry型定義明確化
- 全investigator の `industry: str = ""` → `Optional[str] = None` に統一
- UI境界で `industry.strip() or None` 変換を追加
- `check_history.py` の `to_dict()` で `None → ""` JSON互換変換

#### 課題1: 判定ロジック一元化
- `base.py` に `should_need_manual_review()`, `should_need_verification()` 静的メソッド集約
- `StoreInvestigationResult.is_confident` プロパティ追加
- `player_validator.py`, `store_investigator.py` の散在ロジックを削除

#### 課題3: pydantic LLMスキーマバリデーション
- `core/llm_schemas.py` 新規作成（5スキーマ + `parse_llm_response()` ユーティリティ）
- 全4 investigator のパーサーを pydantic 経由に簡素化
- `requirements.txt` に `pydantic>=2.0.0,<3.0.0` 追加

### Phase B: 新機能

#### 課題4: コスト推定表示（全タブ展開）
- `ui/common.py` に `display_cost_estimate()` 汎用関数追加
- 全investigatorに `estimate_cost()` メソッド追加
- 正誤チェック/店舗調査/新規参入/3段階チェック全タブに表示

#### 課題6: API検索精度の全般的底上げ
- 全investigatorに `temperature=0.1` 統一
- `attribute_investigator.py` に `use_search=True` 追加（唯一の未設定）
- 全investigatorにFew-shot例示追加

#### 課題5: 0ベースプレイヤーリスト生成モード
- `investigators/player_list_generator.py` 新規（LLM→URL検証パイプライン）
- `investigators/base.py` に `GeneratedPlayer` データクラス追加
- `ui/generator_tab.py` 新規（業界名+条件→生成→手動確認→Excel出力）
- `app_v5.py` に「リスト生成」タブ追加

### 新規ファイル
| ファイル | 内容 |
|---------|------|
| `core/llm_schemas.py` | pydantic LLMレスポンススキーマ（5モデル） |
| `investigators/player_list_generator.py` | 0ベースリスト生成エンジン |
| `ui/generator_tab.py` | リスト生成タブUI |
| `tests/test_base.py` | base.pyの判定ロジックテスト（18件） |
| `tests/test_llm_schemas.py` | pydanticスキーマテスト（24件） |

### 残課題（手動確認）
- 各タブのコスト表示を目視確認（課題4）
- 「動画配信サービス」で0ベース生成→URL検証→Excel出力の一連テスト（課題5）
- クレカ20件サンプリングで精度変更前後比較（課題6）

### 未着手の改善候補（旧セッションから継続）
- [R] `excel_handler.py` SRP違反解消（741行に4責務混在）
- [E] テンプレートIDのASCIIスラッグ化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] LLMClient の AsyncContextManager 化

---

## セッション: 2026-02-26 (3)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v6.4: 信頼度削除・業界自動推測・モード説明 → /AI-2G レビュー → 指摘修正 |
| **変更ファイル** | 22ファイル（v6.4）+ 4ファイル（fix） |
| **テスト** | 363件全パス |
| **品質ゲート** | /AI-2G（Claude+Gemini+GPT）🟢 + 指摘P0/P1を即修正 |
| **ステータス** | 完了 |

### 変更詳細（v6.4）
- **信頼度（confidence）削除**: 全4データクラスから `confidence: float` を除去 → `needs_verification`/`needs_manual_review` に統一
- **業界設定簡略化**: サイドバーselectbox → text_input。newcomer_tab/store_tabはタブ内で自前管理（ファイル名自動推測）
- **モード説明追加**: 全5タブ先頭に `st.info()` で簡易説明
- **ロギング**: `core/logger.py` 新設。`Logs/app.log` に日次ローテーション（30日保持）

### 変更詳細（AI-2G指摘修正）
- **🔴 P0**: `scripts/manual_test_validation.py:83` の `result.confidence` 削除（AttributeError修正）
- **🔴 P0**: `store_tab.py` に industry 自前入力フィールド追加、`"industry":""` バグ修正
- **🟡 P1**: `store_investigator.py` に `is_confident()` ヘルパー追加、hybrid判定を `total_stores > 0` 条件追加
- **🟡 P1**: `newcomer_tab.py` 業界推測を正規表現化（バージョン番号・記号除去、空文字フォールバック）

### 残課題（AI-2G [P2]）
- `is_confident()` の判定ロジックをさらに一元化（各所の散在防止）
- `industry: Optional[str]` で型定義を明確化（空文字廃止、None明示）
- pydantic によるLLM出力スキーマバリデーション導入

---

## セッション: 2026-02-26 (2)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | 信頼度の仕様説明 + エラーログ自動収集（`core/logger.py` 新設） |
| **変更ファイル** | `core/logger.py`（新規）、`app_v5.py`、`.gitignore` |
| **テスト** | 動作確認済み（`Logs/app.log` への書き込み確認） |
| **品質ゲート** | 軽微変更につき省略 |
| **ステータス** | 完了 |

### 変更詳細
- **信頼度（confidence）説明**: `investigators/base.py:57` に定義。LLMの判定確度 0.0〜1.0。0.9=高信頼/変更なし、0.4=要確認、0.0=エラー
- **`core/logger.py` 新設**: `setup_logging()` 関数。`Logs/app.log` に日次ローテーション（30日保持）。Streamlit Cloud等書き込み不可環境ではコンソールのみにフォールバック
- **`app_v5.py`**: `setup_logging()` をモジュール読み込み時に1回実行
- **`.gitignore`**: `Logs/` ディレクトリを除外追加

### ログ仕様
- **場所**: `Logs/app.log`
- **ローテーション**: 毎日0時、`app.log.YYYY-MM-DD` 形式バックアップ
- **保持**: 30日
- **活用**: エラー発生時は `Logs/app.log` を Claude に渡してバグ解析

---

## セッション: 2026-02-26

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | Streamlit Cloud デプロイ + パスワード認証 + リファクタリング（Agent Teams） |
| **変更ファイル** | `app_v5.py`, `.gitignore`, `core/excel_handler.py`, `store_scraper_v3.py`, `ui/attribute_tab.py` |
| **テスト** | 63件パス（excel:10 + attribute:38 + scraper:15） |
| **品質ゲート** | /取締役会 🟢 Go (F:0 I:0 R:2 E:0) |
| **ステータス** | 完了 |

### 変更詳細
- **Streamlit Cloud デプロイ**: `init_apis()` に `st.secrets → os.environ` 注入を追加、`.gitignore` に `.env.local` / `.streamlit/secrets.toml` 追加
- **パスワード認証**: `check_password()` 新設。`APP_PASSWORD` を `st.secrets` で管理。`main()` 先頭で呼び出し
- **リポジトリ公開**: GitHub リポジトリをパブリックに変更（コード公開可、APIキーは secrets 管理）
- **Workbook クローズ修正**: `excel_handler.py` `load()` に try/finally で `workbook.close()` を追加
- **Magic Number 定数化**: `store_scraper_v3.py` に 8定数を追加、13箇所を置換
- **Deep Nesting 解消**: `_crawl_prefecture_pages()` ヘルパーを新設、6段階 → 4段階
- **関数分割**: `render_investigation_tab()` (422行) を4関数に分割、オーケストレーターパターンに整理

### Streamlit Cloud 設定（運用情報）
- **URL**: `share.streamlit.io` でデプロイ済み
- **Secrets**: `GOOGLE_API_KEY` / `APP_PASSWORD` を設定
- **認証**: パスワード認証（コード内 `check_password()`）
- **リポジトリ**: `TTMK7777/player-list-scraper`（パブリック）

### 残課題（取締役会 [R]）
- `excel_handler.py` finally後に `self.workbook = None` / `self.sheet = None` をセット（防御的、任意）
- `_render_results_section()` の `timestamp` を関数冒頭で定義（任意）

### 未着手の改善候補（旧 [R]/[E]）
- [R] `excel_handler.py` SRP違反解消（741行に4責務混在 → パッケージ分割）
- [E] テンプレートIDのASCIIスラッグ化（CI/CD環境対応）
- [E] contextフィールドのサニタイズ強化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] Dataclass → Pydantic v2 統一
- [E] LLMClient の AsyncContextManager 化

---

## セッション: 2026-02-24

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v6.3 Perplexity→Gemini一本化 |
| **変更ファイル** | 21ファイル（core, investigators×4, ui×5, store_scraper, app, tests×3, scripts, install.bat, 設定3ファイル） |
| **テスト** | 363件全パス（Perplexityテスト削除分で367→363） |
| **品質ゲート** | /CTO 🟢 APPROVE (F=0, I=0, R=3, E=1) |
| **ステータス** | 完了 |

### 変更詳細
- **Perplexity完全削除**: sonar-pro/sonar-deep-research → gemini-2.5-flash/gemini-2.5-pro
- **Google検索グラウンディング**: `use_search=True` パラメータで最新情報取得（PlayerValidator, StoreInvestigator, NewcomerDetector）
- **LLMClient刷新**: provider パラメータ廃止、Gemini固定
- **store_scraper_v3統合**: 内蔵LLMClientを削除し core/llm_client.py に統合
- **UI簡略化**: プロバイダー選択selectbox削除、Gemini固定
- **openaiパッケージ削除**: requirements.txt から openai>=1.0.0 を削除
- **残存参照修正**: test_store_scraper_pages_visited.py, install.bat の PERPLEXITY_API_KEY 参照を修正

### 既知の軽微な課題 (CTO [R]/[E])
- キャッシュキーに `use_search` 未含（現在の利用パターンでは影響なし）
- 旧SDKフォールバック時に `use_search` が暗黙に無視される（requirements.txt 通りなら発生しない）
- `genai.Client` が毎回生成される（パフォーマンス上は問題なし）

---

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
   - Gemini APIによる最新情報取得
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
│   ├── llm_client.py      # LLMクライアント（Gemini）
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
- Gemini APIは従量課金
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
