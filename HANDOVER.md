# プレイヤーリスト調査システム - Handover Document

> **最終更新**: 2026-03-24
> **担当**: Claude Opus 4.6 + たいむさん
> **バージョン**: v7.2

## セッション: 2026-03-24

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v7.2: 現場FB対応第2弾 — 安全性・合法性フレームワーク + 期間制約強化 + 2段階ブランド発見 |
| **変更ファイル** | 10ファイル変更 + 8ファイル新規（+364行） |
| **テスト** | 522件全パス（492既存 + 30新規、回帰なし） |
| **品質ゲート** | 取締役会（プラン審査）→ センチネル自律処理 → コードドクター（3件修正） |
| **実行方式** | センチネル Pikmin Swarm: 4ピクミン（Opus×3 + Sonnet×1）、2 Wave並列 |
| **ステータス** | 完了（未コミット） |

### 背景: 現場FB 7件
v7.1で対応済み4件（テンプレート編集、判定理由表示、都道府県別数値、SAMANSAバグ）をスルーし、残存3課題を実装。最優先は安全性・合法性。

### TASK 1: 安全性・合法性フレームワーク（最優先）
**新規ファイル（5件）:**
- `core/robots_checker.py`: robots.txt自動準拠チェッカー（ドメインキャッシュ1h TTL、async対応）
- `core/constants.py`: `__version__='7.2'` + `TOOL_USER_AGENT` / `BROWSER_USER_AGENT` 一元管理
- `core/rate_limiter.py`: ドメイン別レート制限（最小0.5秒間隔、asyncio.Lock）
- `core/request_audit.py`: HTTPリクエスト監査ログ（JSONL形式、30日ローテーション）
- `docs/scraping_policy.md`: スクレイピングポリシー文書

**統合（3ファイル変更）:**
- `store_scraper_v3.py`: robots_checker + rate_limiter + audit_log + UA統合（`_fetch_page()` + BrowserAutomation）
- `core/sanitizer.py`: `verify_url()` の UA変更 + 監査ログ追加
- `ui/store_tab.py`: スクレイピング同意チェックボックス追加

### TASK 2: 最新動向の期間制約強化
- `investigators/player_validator.py`: 確認事項1-4に `{current_year-1}年1月以降` を明示追加、古いイベント→`change_type="none"` を強化、否定例追加

### TASK 3: 店舗調査2段階ブランド発見
- `investigators/store_investigator.py`: `_discover_brands()` 新メソッド（企業名→ブランド特定）、0件時のみ自動リトライ（1回限り保証）
- `core/llm_schemas.py`: `BrandDiscoveryLLMResponse` Pydanticモデル追加
- `_build_ai_prompt()` に `brands` パラメータ追加

### コードドクター指摘修正（3件）
1. **[HIGH]** `store_investigator.py`: `_discover_brands()` の `except Exception: pass` → `logging.warning` 追加
2. **[MEDIUM]** `store_scraper_v3.py`: `_check_sync()` プライベートメソッド呼出 → `await is_allowed()` に変更
3. **[MEDIUM]** `store_investigator.py`: `brands: list[str] = None` → `Optional[list[str]] = None`

### 新規テスト（30件）
- `test_robots_checker.py` (8件): robots.txtパース、キャッシュ、タイムアウト、404
- `test_rate_limiter.py` (8件): ドメイン別制限、並行アクセス
- `test_request_audit.py` (8件): JSONL形式、フィールド検証
- `test_player_validator.py` (+2件): プロンプト日付制約、古いイベント非報告
- `test_store_investigator.py` (+4件): ブランド発見、0件リトライ、プロンプト検証

### 未完了・継続課題
- [ ] 正誤チェック解析失敗の対策実装（前回からの引き継ぎ）
- [ ] Gemini API不安定対応（既存ハイブリッドモードで対応済み、大改修は別チケット）
- [ ] コミット＆プッシュ（本セッション内で実施予定）

---

## セッション: 2026-03-10

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v7.1: 現場FB対応 — 全investigator期間制約 + 店舗調査精度向上 + 都道府県別数値 |
| **変更ファイル** | 9ファイル変更（+137行 -34行） |
| **テスト** | 467件全パス（464既存 + 3新規、回帰なし） |
| **品質ゲート** | コードドクター → HIGH 1件修正（bool⊂int 分岐順序バグ） |
| **ステータス** | 完了 |

### 改修A: 全investigatorプロンプトに動的期間制約追加（5ファイル）
- `player_validator.py`: `直近1-2年` → `{current_year-1}年1月以降`、`2024年以降` → 動的年号
- `newcomer_detector.py`: `【時間スコープ】` セクション追加（新規参入の時間定義を明確化）
- `player_list_generator.py`: `■時間スコープ` セクション追加（撤退済み除外・統合名称対応）
- `store_investigator.py`: 最新店舗データ優先 + 閉店済み除外指示
- `attribute_investigator.py`: `{current_year}年時点の最新情報` 判定ルール追加

### 改修B: 店舗調査の精度向上 + 都道府県別数値（3ファイル）
- `store_investigator.py`: ブランド展開調査手順追加、都道府県を `bool` → `int` に変更、レスポンス解析で数値保持
- `excel_handler.py`: 都道府県数値をExcelにそのまま出力（旧 `True/False` 互換維持）
- `store_tab.py`: ラベル「店舗・教室数」に変更、数値表示対応

### コードドクター指摘修正
- **[HIGH] bool⊂int 分岐順序バグ**: Python の `isinstance(True, int) == True` 問題。`is True`/`is False` チェックを `isinstance` の前に移動（3ファイル）

### 新規テスト（3件）
- `test_build_ai_prompt_contains_dynamic_year`: プロンプトに動的年号あり・ハードコード年号なし
- `test_parse_ai_response_preserves_prefecture_numbers`: 数値/0/None/True/False の6パターン保持
- `test_query_latest_info_contains_dynamic_year`: validator プロンプトの動的年号検証

### 未完了・継続課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [ ] Gemini API不安定対応（既存ハイブリッドモードで対応済み、大改修が必要なため別チケット化）
- [R] `excel_handler.py` SRP違反解消
- [E] テンプレートIDのASCIIスラッグ化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] LLMClient の AsyncContextManager 化

---

## セッション: 2026-03-09

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | コードドクター全65件修正（CRITICAL 1 + HIGH 13 + MEDIUM 27 + LOW 24） |
| **変更ファイル** | 24ファイル変更 + 1新規（+447行 -240行） |
| **テスト** | 438件全パス（405既存 + 33新規、回帰なし） |
| **品質ゲート** | 4並列コードレビュー → 3フェーズ修正 → 全テストパス |
| **ステータス** | 完了 |

### 修正概要（3フェーズ構成）

#### Phase 1: セキュリティ (8件)
- **XSS防止**: `html.escape()` を ui/ 4ファイルに適用
- **プロンプトインジェクション**: `DANGEROUS_PATTERNS` 9パターン追加 + context に `sanitize_input()` 適用
- **認証改善**: `hmac.compare_digest()` + 試行回数制限(5回) + 空パスワード防御
- **パストラバーサル**: `Path(...).name` で5箇所サニタイズ
- **SSRF防止**: `_validate_url()` メソッド新設（スキーム+プライベートIP検証）
- **HTTPエラー**: `raise_for_status()` を全HTTPリクエスト箇所に追加

#### Phase 2: バグ修正 (13件)
- **並列化修正**: `attribute_investigator` の for→gather 変換
- **イベントループ保護**: `store_investigator` の `llm.call()` を `asyncio.to_thread` 化
- **セマフォ最適化**: sleep をセマフォ外に移動（player_validator + store_investigator）
- **session_state分離**: `is_running` → `attr_is_running` / `workflow_is_running`
- **finally パターン**: is_running 確実リセット（attribute_tab + player_trend_tab）
- **原子的保存**: `os.replace()` 統一（check_history + investigation_templates）
- **例外処理**: `KeyboardInterrupt` 非捕捉、正規表現 non-greedy 化

#### Phase 3: MEDIUM+LOW改善 (56件 + auto-fix 7件)
- **パフォーマンス**: `compute_diff` O(N²)→O(N+MK)、URL検証並列化（`asyncio.gather`）
- **非同期統一**: `run_in_executor` → `asyncio.to_thread` 2箇所統一
- **コード品質**: `_deduplicate` キー統一（3戦略）、`_sanitize_input` ラッパー廃止、デッドコード削除
- **型ヒント**: `Optional[str]`/`Optional[int]` 修正8箇所、戻り値型ヒント追加
- **堅牢性**: `_executor._shutdown` ガード、三項演算子の優先順位明確化（4箇所）
- **セキュリティ残件**: `_validate_url` を `_scrape_page` にも追加、`unsafe_allow_html` 排除

### 新規テスト (33件)
- `test_sanitizer.py`: 新パターン19件（`TestNewDangerousPatterns`）
- `test_llm_client.py`: non-greedy JSON + KeyboardInterrupt 伝播 2件
- `test_store_scraper_v3.py` (新規): SSRF防止8件 + HTTPエラー4件

### 主な変更ファイル
| ファイル群 | 変更数 | 主な修正 |
|-----------|--------|---------|
| `core/` (8ファイル) | 16件 | O(N²)改善、例外処理、原子的保存、型ヒント |
| `investigators/` (5ファイル) | 15件 | gather並列化、to_thread統一、URL検証並列化 |
| `ui/` (5ファイル) | 18件 | XSS、session_state分離、finally化、型ヒント |
| `app_v5.py` + `store_scraper_v3.py` | 15件 | 認証、SSRF、raise_for_status、dedup統一 |
| `tests/` (5ファイル) | 33件 | 新規テスト + _sanitize_input テスト更新 |

### 未完了・継続課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [R] `excel_handler.py` SRP違反解消
- [E] テンプレートIDのASCIIスラッグ化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] LLMClient の AsyncContextManager 化
- [E] `store_scraper_v3.py` 1,550行を戦略別モジュールに分割
- [E] `StaticHTMLStrategy` インスタンス毎回生成の改善（TODO コメント追記済み）

---

## セッション: 2026-03-02 (5)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v7.0 全件ボタンのStreamlit Cloud対応バグ修正 |
| **変更ファイル** | `ui/common.py`（1ファイル） |
| **テスト** | 405件全パス（回帰なし） |
| **品質ゲート** | AI-2G 3脳レビュー（Claude + Gemini + GPT） |
| **ステータス** | 完了 |

### 変更詳細

#### 全件ボタン修正 (`ui/common.py` — `number_input_with_max()`)

**問題**: Streamlit Cloudで全件ボタンを押すとStreamlitAPIExceptionが発生。
ローカルでは再現しない環境依存バグ。

**原因（3脳共通見解）**:
1. `st.session_state[key] = max_value`（直接代入）→ レンダリング済みウィジェットキーへの代入は不可
2. フラグ方式 + `value` パラメータ → session_stateに既存値があるとvalueパラメータは無視される
3. `st.session_state.pop(key)` → ウィジェットライフサイクルとの衝突リスク

**修正**: Streamlit公式推奨パターンに準拠
- `on_click` コールバックで `st.session_state[key] = safe_max` を設定
- `st.session_state.setdefault()` で初期値制御（`value` パラメータ依存を排除）
- `max_value` 変動時のクランプ追加（Excel再アップロード時の安全性）
- `st.rerun()` / `pop()` / フラグ方式を全て廃止

**コミット**: `67a0088` → `223010b`（2段階修正）

### 未完了・継続課題
- (前セッションから継続、変更なし)

---

## セッション: 2026-03-02 (4)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v7.0: UI大改修 — タブ統合(6→4) + 定義フィールド + 全件ボタン |
| **変更ファイル** | 10ファイル変更 + 1新規 + 2アーカイブ（+115行 -57行 + 884行新規） |
| **テスト** | 405件全パス（回帰なし） |
| **品質ゲート** | collaborative — 取締役会 条件付きGo（CTO指摘2点反映済み） |
| **ステータス** | 完了 |

### 変更詳細

#### 1. タブ再編（6→4タブ）(`app_v5.py`)
- 正誤チェック + 新規参入検出 + リスト生成 → **プレイヤーの最新動向** に統合
- 汎用調査 → **カテゴリチェック** にラベル変更
- 店舗調査（従来版） → **店舗・教室調査** にラベル変更
- 3段階チェック → そのまま

#### 2. 統合タブ新規作成 (`ui/player_trend_tab.py` NEW, 884行)
- 3サブタブ構成: 変更点調査 / 新規参入検出 / 最新版リスト作成
- 共有Excelアップロード（サブタブ上部）
- Sub-tab 3: コンパイルロジック（WITHDRAWAL/MERGERのみ除外、他はデフォルトキープ）
- `st.data_editor` で最終調整 → Excel/CSVエクスポート
- セッション状態は `trend_` プレフィックスで衝突回避

#### 3. サイドバー改修 (`app_v5.py`)
- 業界 help テキストを入力欄の外に移動（`st.caption()`）
- **定義フィールド** 新設（`st.text_area`, 200文字上限）
- 定義のキャプション: 「仮でもOK」の案内付き

#### 4. 定義パラメータ追加（4 investigator）
- `player_validator.py`, `newcomer_detector.py`, `player_list_generator.py`, `attribute_investigator.py`
- 全メソッドに `definition: str = ""` 追加（後方互換）
- LLMプロンプトに `【業界定義・範囲】` セクションとして注入

#### 5. 全件ボタン (`ui/common.py`)
- `number_input_with_max()` ヘルパー関数追加
- 2カラム: [number_input | 全件ボタン]
- 4タブ（trend, attribute, workflow, store）の全チェック件数入力に適用

#### 6. 旧ファイルアーカイブ
- `ui/newcomer_tab.py` → `archive/ui/newcomer_tab.py`
- `ui/generator_tab.py` → `archive/ui/generator_tab.py`
- investigator本体はそのまま維持（workflow_tab等で使用）

### 未完了・継続課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [R] `excel_handler.py` SRP違反解消
- [E] テンプレートIDのASCIIスラッグ化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] LLMClient の AsyncContextManager 化
- [E] `player_trend_tab.py` のサブタブ分離ファイル化（規模が大きくなった場合）

---

## セッション: 2026-03-02 (3)

### 作業サマリー
| 項目 | 内容 |
|------|------|
| **作業内容** | v6.6.1: Excelシート複数選択対応（selectbox → multiselect） |
| **変更ファイル** | 7ファイル（+33行 -10行） |
| **テスト** | 405件全パス（回帰なし） |
| **品質ゲート** | simple — 直接実装 |
| **ステータス** | 完了 |

### 変更詳細

#### 1. シート選択をマルチセレクトに変更 (`ui/common.py`)
- `st.selectbox` → `st.multiselect` に変更（複数シート同時選択可能に）
- 戻り値: `Optional[str]` → `Optional[list[str]]`
- デフォルト: 最初のシートが選択済み
- 何も選択しなければ None → 従来の `load()` にフォールバック

#### 2. 複数シート読み込みメソッド追加 (`core/excel_handler.py`)
- `load_multiple(file_path, sheet_names)` メソッド新設
- 複数シートを順次 `load()` して `extend()` で結合
- `sheet_names` が None/空の場合は従来の `load()` にフォールバック

#### 3. 全5タブの呼び出し変更
- `handler.load(temp_path, sheet_name=selected_sheet)` → `handler.load_multiple(temp_path, sheet_names=selected_sheet)`
- 対象: validation_tab, newcomer_tab, store_tab, workflow_tab, attribute_tab

### 未完了・継続課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [R] `excel_handler.py` SRP違反解消
- [E] テンプレートIDのASCIIスラッグ化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] LLMClient の AsyncContextManager 化

---

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
- API接続表示: `Gemini: 接続OK` → `Gemini: 接続OK（モデル: gemini-2.5-pro）`
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

## 過去セッション履歴

| 日付 | 概要 |
|------|------|
| 2026-02-27 | v6.5: P2修正3件（industry型明確化・判定ロジック一元化・pydanticスキーマ）+ 新機能3件（コスト推定表示・API精度底上げ・0ベースリスト生成）、20ファイル変更、405件テスト |
| 2026-02-26 (3) | v6.4: 信頼度(confidence)削除・業界自動推測・モード説明追加 + AI-2Gレビュー指摘P0/P1修正、22+4ファイル変更、363件テスト |
| 2026-02-26 (2) | 信頼度の仕様説明 + エラーログ自動収集（`core/logger.py` 新設、日次ローテーション30日保持） |
| 2026-02-26 | Streamlit Cloudデプロイ + パスワード認証 + リファクタリング（Workbookクローズ修正・Magic Number定数化・関数分割）、Agent Teams使用 |
| 2026-02-24 | v6.3: Perplexity→Gemini一本化（sonar-pro/deep-research廃止、Google検索グラウンディング、openaiパッケージ削除）、21ファイル変更、363件テスト |
| 2026-02-17 (2) | /技術参謀 全体分析(24ファイル~9,100行) → Important 3件修正（例外処理具体化・スレッドプールリーク修正・郵便番号DRY違反解消）、367件テスト |
| 2026-02-17 | v6.2: 汎用調査エンジン（テンプレート管理 + context対応 + UI統合）、10既存+6新規ファイル、367件テスト |

---

## リファレンス

### プロジェクト概要
オリコン業務の**プレイヤーリスト調査・正誤チェック自動化**システム。
Streamlit GUI (`app_v5.py`) で4タブ構成: プレイヤーの最新動向 / カテゴリチェック / 店舗・教室調査 / 3段階チェック。
対象業界: クレジットカード(539件), 動画配信(36件), 中古車販売店(16件) 他。

### 技術スタック
- **GUI**: Streamlit (Streamlit Cloud デプロイ済み、パスワード認証)
- **LLM**: Gemini API (`gemini-2.5-pro`, `google-genai`)
- **データ**: openpyxl (Excel), 複数シート対応 (`load_multiple`)
- **テスト**: pytest 405件
- **構成**: `core/`(共通基盤) + `investigators/`(調査ロジック) + `ui/`(タブUI) + `templates/`(調査テンプレート)

### 環境設定・起動
```bash
# APIキー: ~/.env.local に GOOGLE_API_KEY を設定 (override=True)
pip install -r requirements.txt
streamlit run app_v5.py
```

### 主要機能
- **正誤チェック** (v4.0): 撤退・統合・名称変更の自動検出、アラートレベル別レポート (赤:緊急/黄:警告/緑:情報/OK/要確認)
- **汎用調査** (v6.2): テンプレート方式 (組み込み4種+カスタム)、context注入、バッチプロンプト、Excel/CSV出力
- **新規参入検出** (v6.0): LLM提案 → URL検証 → 手動確認の3ステップ、ハルシネーション対策
- **3段階チェック** (v6.0): 実査前→確定時→発表前のワークフロー、フェーズ間差分レポート
- **店舗調査** (v3.0): マルチ戦略スクレイピング + AI調査
- **統合タブ** (v7.0): 変更点調査/新規参入/最新版リスト作成を1タブに統合、定義フィールド、全件ボタン
- **コスト表示**: 日本円化 (USD_TO_JPY=150)、LLMキャッシュ (TTL付き)

### 未解決課題
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [R] `excel_handler.py` SRP違反解消
- [E] テンプレートIDのASCIIスラッグ化
- [E] カテゴリ値対応（boolean以外の多値分類）
- [E] LLMClient の AsyncContextManager 化
- [E] `player_trend_tab.py` のサブタブ分離ファイル化
- [ ] contextフィールドのサニタイズ強化

### トラブルシューティング
- **401エラー**: `~/.env.local` のキー確認、システム環境変数の古いキーを削除
- **Excel読み込み不可**: 4行目ヘッダー形式、「サービス名」「事業者名」列を自動検出
- **Geminiエラー**: `google-genai` パッケージ更新、モデル名 `gemini-2.5-pro` 確認

---

*このドキュメントは引き継ぎ・メンテナンス用です。開発: Claude Opus 4.6 / 運用: たいむさん*
