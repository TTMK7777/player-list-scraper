## プラン: attribute_tab.py render_investigation_tab() 関数分割

### 変更対象ファイル
- `ui/attribute_tab.py` — render_investigation_tab() を4サブ関数に分割

### 実装順序

1. **`_render_template_section(tm: TemplateManager) -> tuple[list[str], Optional[int], str]`**
   - 行104-276 相当（テンプレート選択・詳細表示・カスタム入力・新規作成・削除）
   - 戻り値: `(attributes, batch_size, context)` — 後続セクションで必要な3値を返す

2. **`_render_player_input_section() -> None`**
   - 行282-343 相当（Excel/直接入力タブ切替 + session_state.attr_players への書き込み）
   - session_state 経由でデータを共有するため戻り値なし

3. **`_render_investigation_section(industry: str, attributes: list[str], batch_size: Optional[int], context: str) -> None`**
   - 行355-449 相当（コスト概算・バッチサイズ上書き・調査実行・進捗表示）
   - `industry` はオーケストレーターから引き渡し

4. **`_render_results_section(attributes: list[str]) -> None`**
   - 行450-512 相当（マトリクス表示・Excel/CSVダウンロード）
   - `attributes` は列ヘッダ用に必要

5. **`render_investigation_tab(industry)` をオーケストレーターに書き換え**
   - セッション状態初期化（行349-352）はオーケストレーター内に残す
   - 4関数を順番に呼び出す
   - 後方互換ラッパー `render_attribute_tab()` はそのまま維持

### session_state の扱い
- `attr_players`, `attr_results`, `is_running` は既存のまま session_state 経由で共有
- 関数間の引数渡しは最小限にし、session_state に依存する部分はそのまま

### st.divider() の配置
- 各セクション末尾の `st.divider()` はサブ関数内に含める（現状の位置を維持）

### リスク・懸念点
- Streamlit ウィジェット key の一意性は既存値を変更しないため問題なし
- `timestamp` 変数がセクション3→4を跨いでいないか確認 → 行487で新規生成しているため問題なし

### テスト方針
- `pytest tests/test_attribute_investigator.py -v` を実行し全パスを確認
- テストは AttributeInvestigator エンジン側のテストであり、UI分割で影響を受けないはず
