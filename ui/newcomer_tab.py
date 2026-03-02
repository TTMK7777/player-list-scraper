#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新規参入プレイヤー検出UIタブ
============================
"""

import asyncio
import re
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.async_helpers import run_async
from core.excel_handler import ExcelHandler
from core.llm_client import LLMClient
from core.sanitizer import sanitize_input
from investigators.newcomer_detector import NewcomerDetector
from ui.common import display_verification_badge, display_cost_estimate, select_sheet_if_multiple


def render_newcomer_tab():
    """新規参入検出タブのUIをレンダリング"""

    st.subheader("新規参入プレイヤー検出")

    st.info("既存プレイヤーリストにない**新規参入企業**をAIが自動検索します。ファイルアップロードまたは直接入力で既存リストを登録後、検索を実行してください。")

    # 既存プレイヤーリスト入力
    st.markdown("**既存プレイヤーリストを入力**")

    input_tab1, input_tab2 = st.tabs(["📤 Excelアップロード", "✏️ 直接入力"])

    with input_tab1:
        uploaded_file = st.file_uploader(
            "既存プレイヤーリストExcelをアップロード",
            type=["xlsx", "xls"],
            help="既存のプレイヤーリスト（サービス名を含むExcel）",
            key="newcomer_excel_upload",
        )

        if uploaded_file:
            try:
                temp_dir = Path(tempfile.gettempdir()) / "newcomer_detector"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = temp_dir / uploaded_file.name
                temp_path.write_bytes(uploaded_file.getvalue())

                selected_sheet = select_sheet_if_multiple(temp_path, "newcomer")
                handler = ExcelHandler()
                players_data = handler.load(temp_path, sheet_name=selected_sheet)

                existing_names = [p.player_name for p in players_data]
                st.session_state.existing_players = existing_names
                st.session_state.newcomer_uploaded_filename = uploaded_file.name
                st.success(f"{len(existing_names)}件の既存プレイヤーを読み込みました")

            except Exception as e:
                st.error(f"Excelの読み込みに失敗: {e}")
                st.session_state.existing_players = []

    with input_tab2:
        input_text = st.text_area(
            "既存プレイヤー名を1行1件で入力",
            placeholder="Netflix\nHulu\nABEMAプレミアム\nU-NEXT",
            height=150,
            key="newcomer_direct_input",
        )

        if st.button("入力内容を反映", key="newcomer_apply_input"):
            names = [sanitize_input(n.strip()) for n in input_text.strip().split("\n") if n.strip()]
            if names:
                st.session_state.existing_players = names
                st.success(f"{len(names)}件の既存プレイヤーを登録しました")

    # セッション状態初期化
    if "existing_players" not in st.session_state:
        st.session_state.existing_players = []
    if "newcomer_candidates" not in st.session_state:
        st.session_state.newcomer_candidates = []

    st.divider()

    # 業界（ファイル名から自動推測）
    st.markdown("**対象業界**")
    auto_industry = ""
    filename = st.session_state.get("newcomer_uploaded_filename", "")
    if filename:
        # ファイル名から業界を推測（例: "動画配信プレイヤーリスト.xlsx" → "動画配信サービス"）
        stem = Path(filename).stem
        # ノイズ語・数字・記号・バージョン番号を除去
        stem = re.sub(r"(プレイヤーリスト|一覧|リスト|調査|用)", "", stem)
        stem = re.sub(r"[_\-v\d\.]+", "", stem)  # バージョン番号・記号除去
        stem = stem.strip()
        auto_industry = stem if stem else ""  # 空文字フォールバック（ユーザーが手入力）
    industry = st.text_input(
        "業界名",
        value=auto_industry,
        placeholder="例: 動画配信サービス、クレジットカード",
        help="ファイル名から自動推測します。必要に応じて修正してください。",
        key="newcomer_industry_input",
    )

    # コスト概算表示
    if st.session_state.existing_players and industry:
        cost = NewcomerDetector.estimate_cost()
        display_cost_estimate(
            call_count=cost["call_count"],
            cost_per_call=cost["cost_per_call"],
            label="新規参入検出",
        )

    # 検出実行
    run_button = st.button(
        "新規参入を検索",
        type="primary",
        disabled=not st.session_state.existing_players or not industry or st.session_state.get("is_running", False),
        use_container_width=True,
        key="newcomer_run_button",
    )

    if not industry:
        st.warning("業界を入力してください。")

    st.divider()

    if run_button:
        st.session_state.is_running = True
        progress_container = st.empty()
        status_container = st.empty()

        def on_progress(current, total, name):
            progress_container.markdown(
                f'<div class="progress-log">[{current}/{total}] {name}</div>',
                unsafe_allow_html=True,
            )

        # UI境界: 空文字→None正規化
        industry_normalized = industry.strip() or None if industry else None
        status_container.info("新規参入候補を検索中...")

        try:
            llm = LLMClient()
            detector = NewcomerDetector(llm_client=llm)

            candidates = run_async(detector.detect(
                industry=industry_normalized,
                existing_players=st.session_state.existing_players,
                on_progress=on_progress,
            ))

            st.session_state.newcomer_candidates = candidates
            status_container.success(f"検出完了: {len(candidates)}件の候補")

        except Exception as e:
            status_container.error(f"エラー: {type(e).__name__}: {str(e)}")
            st.session_state.newcomer_candidates = []

        st.session_state.is_running = False

    # 結果表示
    if st.session_state.newcomer_candidates:
        candidates = st.session_state.newcomer_candidates

        st.subheader("候補一覧")

        st.warning(
            "候補はAIの提案です。必ず手動確認してからエクスポートしてください。\n\n"
            "URL検証バッジの見方:\n"
            "- URL検証済み: 公式サイトの存在を確認\n"
            "- URL不明: URLにアクセスできなかった（要注意）\n"
            "- 未検証: URLが提供されていない"
        )

        # 候補テーブル
        for i, candidate in enumerate(candidates):
            badge = display_verification_badge(candidate.verification_status)

            with st.container():
                col1, col2, col3 = st.columns([0.5, 3, 3])

                with col1:
                    # チェックボックス（選択用）
                    key = f"newcomer_select_{i}"
                    if key not in st.session_state:
                        st.session_state[key] = candidate.verification_status == "verified"
                    st.checkbox("", key=key, label_visibility="collapsed")

                with col2:
                    st.markdown(f"**{candidate.player_name}** {badge}", unsafe_allow_html=True)
                    if candidate.official_url:
                        st.caption(candidate.official_url)

                with col3:
                    st.caption(f"運営: {candidate.company_name}" if candidate.company_name else "")
                    st.caption(f"理由: {candidate.reason}" if candidate.reason else "")

            st.divider()

        # エクスポート（選択した候補のみ）
        st.subheader("選択した候補をエクスポート")

        selected = []
        for i, candidate in enumerate(candidates):
            if st.session_state.get(f"newcomer_select_{i}", False):
                selected.append(candidate)

        st.info(f"選択中: {len(selected)}件 / {len(candidates)}件")

        if selected:
            # CSV エクスポート
            csv_data = [c.to_dict() for c in selected]
            df = pd.DataFrame(csv_data)
            csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "選択した候補をExcelエクスポート",
                csv_bytes,
                f"newcomer_candidates_{timestamp}.csv",
                "text/csv",
                use_container_width=True,
            )
