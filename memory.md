# player-list-scraper メモリ

## 失敗と教訓

### 「要確認のみ表示」フィルタの空表示 (v7.3)
- needs_manual_review は UNCERTAIN/低信頼度のみ → ユーザーの期待（変更があるもの全部）とミスマッチ
- 教訓: フィルタのラベルとロジックの意味を一致させる。CRITICAL/WARNING も「対応が必要」に含める

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

### 現場FB v7.3 (2026-04-01)
- URLをプレビュー画面からも飛べるようにしたい → LinkColumn 導入
- アラートに公式告知・プレスリリースも含めたい → プロンプト修正
- 要確認フィルタが機能しない → フィルタロジック修正
- スクレイピングは法的リスク → 廃止し AI 2段階チェック導入
- コスト表示を目立たせたい → st.metric + 動的算出

### 現場FB v7.2 (2026-03-24)
- 安全性・合法性が最優先 → robots.txt準拠、レート制限、監査ログ実装
- 期間制約の強化
- 店舗調査で0件問題 → 2段階ブランド発見で対応
