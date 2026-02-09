#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
属性調査（カテゴリ/ブランド）UIタブ
====================================
"""

import asyncio
import io
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.attribute_presets import ATTRIBUTE_PRESETS, get_preset, get_preset_labels
from core.excel_handler import ExcelHandler, AttributeInvestigationExporter
from core.llm_client import LLMClient
from investigators.attribute_investigator import AttributeInvestigator
from ui.common import display_cost_warning, export_to_excel_bytes


def render_attribute_tab(provider: str, industry: str):
    """属性調査タブのUIをレンダリング"""

    st.subheader("📊 属性調査（カテゴリ/ブランド）")

    # プリセット選択
    preset_labels = get_preset_labels()
    preset_options = list(preset_labels.keys()) + ["カスタム"]

    preset_choice = st.selectbox(
        "プリセット選択",
        preset_options,
        format_func=lambda x: preset_labels.get(x, "カスタム（ユーザー定義属性）"),
    )

    # 属性リスト取得
    if preset_choice != "カスタム":
        preset = get_preset(preset_choice)
        attributes = preset["attributes"]
        batch_size = preset.get("batch_size")
        st.info(f"属性数: {len(attributes)}項目 / 推奨バッチ: {batch_size}社/回")
        with st.expander("調査対象属性"):
            st.write(", ".join(attributes))
    else:
        custom_input = st.text_area(
            "属性をカンマ区切りで入力",
            placeholder="例: 邦画, 洋画, アニメ, ドキュメンタリー",
            height=80,
        )
        attributes = [a.strip() for a in custom_input.split(",") if a.strip()] if custom_input else []
        batch_size = None

        if attributes:
            st.info(f"属性数: {len(attributes)}項目")

    st.divider()

    # 入力方法
    st.subheader("📂 プレイヤー情報入力")

    input_tab1, input_tab2 = st.tabs(["📤 Excelアップロード", "✏️ 直接入力"])

    with input_tab1:
        uploaded_file = st.file_uploader(
            "プレイヤーリストExcelをアップロード",
            type=["xlsx", "xls"],
            help="サービス名/プレイヤー名、公式URL を含むExcelファイル",
            key="attr_excel_upload",
        )

        if uploaded_file:
            try:
                temp_dir = Path(tempfile.gettempdir()) / "attribute_investigator"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = temp_dir / uploaded_file.name
                temp_path.write_bytes(uploaded_file.getvalue())

                handler = ExcelHandler()
                players_data = handler.load(temp_path)

                players = [
                    {
                        "player_name": p.player_name,
                        "official_url": p.official_url,
                    }
                    for p in players_data
                ]

                st.session_state.attr_players = players
                st.success(f"{len(players)}件のプレイヤーを読み込みました")

            except Exception as e:
                st.error(f"Excelの読み込みに失敗: {e}")
                st.session_state.attr_players = []

    with input_tab2:
        input_text = st.text_area(
            "サービス名,公式URL の形式で入力（1行1サービス）",
            placeholder="Netflix,https://www.netflix.com/jp/\nHulu,https://www.hulu.jp/",
            height=120,
            key="attr_direct_input",
        )

        if st.button("入力内容を反映", key="attr_apply_input"):
            players = []
            for line in input_text.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(",")
                player_name = parts[0].strip()
                official_url = parts[1].strip() if len(parts) > 1 else ""
                players.append({
                    "player_name": player_name,
                    "official_url": official_url,
                })

            if players:
                st.session_state.attr_players = players
                st.success(f"{len(players)}件のプレイヤーを登録しました")

    st.divider()

    # セッション状態初期化
    if "attr_players" not in st.session_state:
        st.session_state.attr_players = []
    if "attr_results" not in st.session_state:
        st.session_state.attr_results = []

    # コスト概算 & 調査実行
    players = st.session_state.attr_players

    if players and attributes:
        investigator = AttributeInvestigator()
        cost_info = investigator.estimate_cost(
            player_count=len(players),
            attribute_count=len(attributes),
            batch_size=batch_size,
        )

        display_cost_warning(
            cost_info["estimated_cost"],
            cost_info["batch_count"],
            len(players),
        )

    col1, col2 = st.columns([1, 3])
    with col1:
        check_limit = st.number_input(
            "調査件数",
            min_value=1,
            max_value=len(players) if players else 100,
            value=min(10, len(players)) if players else 10,
            help="初回は少数でテスト推奨",
            key="attr_check_limit",
        )

    with col2:
        run_button = st.button(
            "属性調査開始",
            type="primary",
            disabled=not players or not attributes or st.session_state.get("is_running", False),
            use_container_width=True,
            key="attr_run_button",
        )

    st.divider()

    if run_button:
        st.session_state.is_running = True
        progress_container = st.empty()
        status_container = st.empty()

        players_to_check = players[:check_limit]

        logs = []

        def on_progress(current, total, name):
            log_msg = f"[{current}/{total}] 調査中: {name}"
            logs.append(log_msg)
            log_text = "\n".join(logs[-15:])
            progress_container.markdown(
                f'<div class="progress-log">{log_text}</div>',
                unsafe_allow_html=True,
            )

        status_container.info(f"{len(players_to_check)}件のプレイヤーを属性調査中...")

        try:
            llm = LLMClient(provider=provider)
            inv = AttributeInvestigator(llm_client=llm)

            results = asyncio.run(inv.investigate_batch(
                players_to_check,
                attributes,
                industry=industry,
                batch_size=batch_size,
                on_progress=on_progress,
            ))

            st.session_state.attr_results = results
            status_container.success(f"調査完了: {len(results)}件")

        except Exception as e:
            status_container.error(f"エラー: {type(e).__name__}: {str(e)}")
            st.session_state.attr_results = []

        st.session_state.is_running = False

    # 結果表示
    if st.session_state.attr_results:
        results = st.session_state.attr_results

        # マトリクステーブル表示
        st.subheader("結果: 属性マトリクス")

        matrix_data = []
        for r in results:
            row = {"プレイヤー名": r.player_name}
            for attr in attributes:
                val = (r.attribute_matrix or {}).get(attr)
                if val is True:
                    row[attr] = "○"
                elif val is False:
                    row[attr] = "×"
                else:
                    row[attr] = "?"
            row["信頼度"] = f"{r.confidence * 100:.0f}%"
            row["要確認"] = "!" if r.needs_verification else ""
            matrix_data.append(row)

        df = pd.DataFrame(matrix_data)
        st.dataframe(df, use_container_width=True, height=400)

        st.divider()

        # エクスポート
        st.subheader("結果エクスポート")

        col1, col2 = st.columns(2)

        with col1:
            exporter = AttributeInvestigationExporter(attributes=attributes)
            excel_data = export_to_excel_bytes(exporter, results)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "Excel ダウンロード（属性調査結果）",
                excel_data,
                f"attribute_investigation_{timestamp}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        with col2:
            csv_data = []
            for r in results:
                csv_data.append(r.to_dict())
            df_csv = pd.DataFrame(csv_data)
            csv_bytes = df_csv.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                "CSV ダウンロード",
                csv_bytes,
                f"attribute_investigation_{timestamp}.csv",
                "text/csv",
                use_container_width=True,
            )
