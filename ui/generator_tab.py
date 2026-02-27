#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
0ベースプレイヤーリスト生成UIタブ
==================================
業界名+条件入力→AI生成→URL検証→手動確認→Excel出力
"""

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from core.async_helpers import run_async
from core.llm_client import LLMClient
from investigators.player_list_generator import PlayerListGenerator
from ui.common import display_verification_badge, display_cost_estimate


def render_generator_tab():
    """0ベースプレイヤーリスト生成タブのUIをレンダリング"""

    st.subheader("0ベースプレイヤーリスト生成")

    st.info(
        "既存リストなしで、**業界名+条件**からプレイヤーリストをAIが自動生成します。\n\n"
        "生成された候補は手動確認後にExcelエクスポートできます。"
    )

    # 業界名入力
    industry = st.text_input(
        "業界名",
        placeholder="例: 動画配信サービス、クレジットカード、フィットネスクラブ",
        help="対象業界を具体的に入力してください",
        key="gen_industry_input",
    )

    # 条件指定
    st.markdown("**絞り込み条件（任意）**")

    col1, col2 = st.columns(2)
    with col1:
        region = st.selectbox(
            "対象地域",
            ["日本国内のみ", "グローバル", "指定なし"],
            key="gen_region",
        )

    with col2:
        max_count = st.number_input(
            "最大件数",
            min_value=5,
            max_value=100,
            value=30,
            help="生成するプレイヤーの最大件数",
            key="gen_max_count",
        )

    custom_conditions = st.text_area(
        "追加条件（任意）",
        placeholder="例: BtoC向けサービスのみ、売上100億円以上の企業、2020年以降に設立",
        height=80,
        key="gen_custom_conditions",
    )

    # 条件テキストを組み立て
    conditions_parts = []
    if region == "日本国内のみ":
        conditions_parts.append("日本国内でサービスを提供しているもの")
    elif region == "グローバル":
        conditions_parts.append("グローバルにサービスを提供しているもの")
    if custom_conditions.strip():
        conditions_parts.append(custom_conditions.strip())
    conditions_text = "\n".join(conditions_parts)

    # コスト概算表示
    if industry:
        cost = PlayerListGenerator.estimate_cost()
        display_cost_estimate(
            call_count=cost["call_count"],
            cost_per_call=cost["cost_per_call"],
            label="リスト生成",
        )

    # 実行ボタン
    run_button = st.button(
        "リスト生成を実行",
        type="primary",
        disabled=not industry or st.session_state.get("gen_is_running", False),
        use_container_width=True,
        key="gen_run_button",
    )

    if not industry:
        st.warning("業界名を入力してください。")

    st.divider()

    # セッション状態初期化
    if "gen_candidates" not in st.session_state:
        st.session_state.gen_candidates = []

    if run_button:
        st.session_state.gen_is_running = True
        progress_container = st.empty()
        status_container = st.empty()

        def on_progress(current, total, message):
            progress_container.markdown(
                f'<div class="progress-log">[{current}/{total}] {message}</div>',
                unsafe_allow_html=True,
            )

        status_container.info("プレイヤーリストを生成中...")

        try:
            llm = LLMClient()
            generator = PlayerListGenerator(llm_client=llm)

            candidates = run_async(generator.generate(
                industry=industry,
                conditions=conditions_text,
                max_count=max_count,
                on_progress=on_progress,
            ))

            st.session_state.gen_candidates = candidates
            status_container.success(f"生成完了: {len(candidates)}件の候補")

        except Exception as e:
            status_container.error(f"エラー: {type(e).__name__}: {str(e)}")
            st.session_state.gen_candidates = []

        st.session_state.gen_is_running = False

    # 結果表示
    if st.session_state.gen_candidates:
        candidates = st.session_state.gen_candidates

        st.subheader("生成されたプレイヤー候補")

        # サマリー
        verified_count = sum(1 for c in candidates if c.url_verified)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("候補数", f"{len(candidates)}件")
        with col2:
            st.metric("URL検証済み", f"{verified_count}件")
        with col3:
            st.metric("未検証/エラー", f"{len(candidates) - verified_count}件")

        st.warning(
            "候補はAIの生成結果です。必ず手動確認してからエクスポートしてください。\n\n"
            "- URL検証済み: 公式サイトの存在を確認\n"
            "- 未検証: URLにアクセスできなかった、またはURLが未提供"
        )

        # 候補テーブル（チェックボックス付き）
        for i, candidate in enumerate(candidates):
            badge = display_verification_badge(
                "verified" if candidate.url_verified else "unverified"
            )

            with st.container():
                col1, col2, col3 = st.columns([0.5, 3, 3])

                with col1:
                    key = f"gen_select_{i}"
                    if key not in st.session_state:
                        st.session_state[key] = candidate.url_verified
                    st.checkbox("", key=key, label_visibility="collapsed")

                with col2:
                    st.markdown(f"**{candidate.player_name}** {badge}", unsafe_allow_html=True)
                    if candidate.official_url:
                        st.caption(candidate.official_url)

                with col3:
                    st.caption(f"運営: {candidate.company_name}" if candidate.company_name else "")
                    st.caption(f"理由: {candidate.reason}" if candidate.reason else "")

            st.divider()

        # エクスポート
        st.subheader("選択した候補をエクスポート")

        selected = []
        for i, candidate in enumerate(candidates):
            if st.session_state.get(f"gen_select_{i}", False):
                selected.append(candidate)

        st.info(f"選択中: {len(selected)}件 / {len(candidates)}件")

        if selected:
            # Excel エクスポート
            export_data = [c.to_dict() for c in selected]
            df = pd.DataFrame(export_data)

            # Excel形式
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="プレイヤーリスト")

                from openpyxl.utils import get_column_letter
                worksheet = writer.sheets["プレイヤーリスト"]
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).map(len).max(),
                        len(str(col))
                    ) + 2
                    worksheet.column_dimensions[get_column_letter(idx + 1)].width = min(max_length, 50)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Excel ダウンロード",
                    buffer.getvalue(),
                    f"player_list_{timestamp}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            with col2:
                csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "CSV ダウンロード",
                    csv_bytes,
                    f"player_list_{timestamp}.csv",
                    "text/csv",
                    use_container_width=True,
                )
