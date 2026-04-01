# player-list-scraper ナレッジ

## 技術判断

### Perplexity→Gemini一本化 (v6.3)
- sonar-pro/deep-research を廃止し、Gemini + Google検索グラウンディングに統一
- openaiパッケージを削除
- 理由: API統一によるメンテナンス性向上、Google検索グラウンディングの精度

### DEFAULT_MODEL = gemini-2.5-pro (v6.6)
- 全investigator + store_scraper がこの定数を参照
- flash→pro への変更でコスト増だが、精度向上を優先（ユーザー了承済み）

### Streamlit公式パターン準拠 (v7.0)
- `on_click` コールバックで `st.session_state[key]` を設定
- `st.session_state.setdefault()` で初期値制御（`value` パラメータ依存を排除）
- `st.rerun()` / `pop()` / フラグ方式を全て廃止

### 調査期間のユーザー指定 (v7.3)
- サイドバーに「開始年」「開始月」の number_input を追加（デフォルト: 前年1月）
- start_year / start_month を app → タブUI → investigator に伝搬
- プロンプト内では `period_label = f"{sy}年{sm}月以降"` で動的生成
- store_investigator は `self._start_year` 属性で受け渡し（investigate メソッドの引数ではなくインスタンス変数）

### バージョン表記の一元化 (v7.3)
- app_v5.py の page_title / st.title が v7.0 ハードコードのまま放置されていた
- `core/constants.py` の `__version__` を f-string で参照する形に修正
- バージョン変更は constants.py の1箇所のみで済む

### スクレイピング廃止 → AI 2段階チェック (v7.3)
- スクレイピング（InvestigationMode.SCRAPING/HYBRID）を法的リスクのため廃止
- Gemini AI がメイン調査、needs_verification 時に Perplexity で補助検証
- store_scraper_v3.py は未削除だが、store_investigator からの参照は除去済み

### LLMClient トークン追跡 (v7.3)
- `_usage` dict で calls / input_tokens / output_tokens / cached_hits を追跡
- `usage_summary` プロパティで実コスト (USD/JPY) を算出
- google.genai の `response.usage_metadata` から取得

### デバッグログUI (v7.3)
- core/app_logger.py: StreamlitLogHandler → session_state.log_buffer (deque, 500行)
- render_debug_log(): expander + st.code(language="log") + コピペ案内メッセージ
- CS-creative-maker の実装パターンを踏襲

### 安全性・合法性フレームワーク (v7.2)
- robots.txt自動準拠チェッカー（ドメインキャッシュ1h TTL）
- ドメイン別レート制限（最小0.5秒間隔、asyncio.Lock）
- HTTPリクエスト監査ログ（JSONL形式、30日ローテーション）
- User-Agent識別（TOOL_USER_AGENT / BROWSER_USER_AGENT 一元管理）

## 知見

### bool is int 問題 (Python)
- `isinstance(True, int) == True` なので、`is True`/`is False` チェックを `isinstance` の前に配置する必要がある
- 店舗調査の都道府県データ（bool/int混在）で発生

### Streamlit Cloud 環境依存バグ
- `st.session_state[key]` への直接代入はレンダリング済みウィジェットキーで例外発生
- ローカルでは再現しない

### 「LLMからの応答を解析できませんでした」問題
- Gemini `use_search=True` 時にJSON形式を無視したテキスト回答が返る場合がある
- 30件中5件で発生（Azure OpenAI Service, ナレフルチャット等）
- デバッグログ追加済み、根本対策は未実装

### コードドクター全65件修正の構成
- Phase 1: セキュリティ (8件) -- XSS, プロンプトインジェクション, 認証, パストラバーサル, SSRF
- Phase 2: バグ修正 (13件) -- 並列化, イベントループ, セマフォ, session_state分離
- Phase 3: MEDIUM+LOW改善 (56件) -- パフォーマンス, 非同期統一, 型ヒント

## 外部リソース

| リソース | 説明 |
|---------|------|
| Gemini API | google-genai パッケージ、Google検索グラウンディング |
| Streamlit Cloud | デプロイ先、Secrets で API キー管理 |

## FAQ

### Q: APIキーの設定方法は？
`~/.env.local` に `GOOGLE_API_KEY=AIzaSy-xxxxx` を設定。Streamlit Cloud では Settings > Secrets に設定。

### Q: Excel読み込みの形式は？
4行目ヘッダー形式、「サービス名」「事業者名」列を自動検出。

### Q: テストの実行方法は？
`pytest tests/ -v` で全518件実行。カバレッジ付きは `pytest tests/ --cov=. --cov-report=html`。
