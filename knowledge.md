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
`pytest tests/ -v` で全522件実行。カバレッジ付きは `pytest tests/ --cov=. --cov-report=html`。
