# player-list-scraper メモリ

## 失敗と教訓

### Streamlit Cloud 全件ボタンバグ (v7.0)
- session_state への直接代入がレンダリング済みウィジェットで例外発生
- 教訓: Streamlit 公式推奨パターン（on_click コールバック + setdefault）に常に準拠すること
- ローカルで再現しない環境依存バグは3脳レビュー（AI-2G）が有効

### bool is int 分岐順序バグ (v7.1)
- Python の `isinstance(True, int)` が `True` を返す仕様
- 教訓: bool/int 混在データでは `is True`/`is False` を `isinstance` より先にチェック

### LLM応答解析失敗 (v6.5.1)
- Gemini use_search=True 時にJSON無視のテキスト回答
- 教訓: LLM応答は常にフォールバック解析を用意する

## 不採用記録

### st.rerun() / pop() / フラグ方式 (v7.0)
- 全件ボタンの実装で試行したが、全てStreamlit Cloudで問題発生
- 最終的に on_click コールバック方式を採用

### Perplexity API (sonar-pro / deep-research) (v6.3)
- Gemini + Google検索グラウンディングに統一し、Perplexity APIを廃止
- 理由: API統一、メンテナンス性

## フィードバック

### 現場FB v7.1 (2026-03-10)
- テンプレート編集、判定理由表示、都道府県別数値、SAMANSAバグ → 対応済み

### 現場FB v7.2 (2026-03-24)
- 安全性・合法性が最優先 → robots.txt準拠、レート制限、監査ログ実装
- 期間制約の強化
- 店舗調査で0件問題 → 2段階ブランド発見で対応
