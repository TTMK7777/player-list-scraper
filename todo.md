# player-list-scraper タスク

## 進行中
- (なし)

## 未着手
- [ ] 正誤チェック解析失敗の対策実装（ログ確認後）
- [ ] Gemini API不安定対応（既存ハイブリッドモードで対応済み、大改修は別チケット）
- [ ] [R] `excel_handler.py` SRP違反解消
- [ ] [E] テンプレートIDのASCIIスラッグ化
- [ ] [E] カテゴリ値対応（boolean以外の多値分類）
- [ ] [E] LLMClient の AsyncContextManager 化
- [ ] [E] `player_trend_tab.py` のサブタブ分離ファイル化
- [ ] [E] `store_scraper_v3.py` は将来的に削除検討（スクレイピング廃止済み）
- [ ] contextフィールドのサニタイズ強化
- [ ] コミット＆プッシュ (v7.2 + v7.3)

## 完了
- [x] v7.3: デバッグログUI（StreamlitLogHandler + expander表示 + コピペ案内）
- [x] v7.3: URLクリッカブル化（最新動向プレビュー → LinkColumn）
- [x] v7.3: アラートURL拡充（公式告知・プレスリリースURL指示追加）
- [x] v7.3: 「要確認のみ表示」フィルタ修正（CRITICAL/WARNING/要確認を対象に）
- [x] v7.3: スクレイピング機能廃止 → Gemini+Perplexity 2段階AIチェック
- [x] v7.3: 動的コスト算出（LLMClient トークン追跡）+ 目立つ表示（st.metric）
- [x] ORICON-CS-DASHBOARD にもデバッグログUI追加（全4モード対応）
- [x] v7.2: 安全性・合法性フレームワーク（robots.txt準拠、レート制限、監査ログ）
- [x] v7.2: 最新動向の期間制約強化
- [x] v7.2: 店舗調査2段階ブランド発見
- [x] v7.2: コードドクター指摘修正3件
- [x] v7.1: 全investigatorプロンプトに動的期間制約
- [x] v7.1: 店舗調査精度向上 + 都道府県別数値
- [x] v7.0: UI大改修 -- タブ統合(6→4) + 定義フィールド + 全件ボタン
- [x] v6.6: 複数シート対応 + DEFAULT_MODEL一元化
- [x] v6.5: P2修正 + コスト表示 + 0ベースリスト生成
- [x] コードドクター全65件修正（CRITICAL 1 + HIGH 13 + MEDIUM 27 + LOW 24）
- [x] Streamlit Cloud デプロイ + パスワード認証

## 保留
- (なし)
