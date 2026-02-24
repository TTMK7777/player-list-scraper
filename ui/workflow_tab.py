#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3段階チェック体制UIタブ
========================
実査前 → 確定時 → 発表前のワークフローを管理。
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.async_helpers import run_async
from core.check_history import CheckHistory, CheckRecord
from core.check_workflow import (
    CheckWorkflow,
    CheckPhase,
    PHASE_LABELS,
    PHASE_CONFIG,
)
from core.llm_client import LLMClient
from core.excel_handler import ExcelHandler
from investigators.player_validator import PlayerValidator
from investigators.base import AlertLevel, ValidationResult


def render_workflow_tab(industry: str):
    """3段階チェックタブのUIをレンダリング"""

    st.subheader("3段階チェック体制")

    if not industry:
        st.warning("サイドバーで業界を選択してください。")
        return

    # ワークフロー管理初期化
    workflow = CheckWorkflow()
    status = workflow.get_status(industry)

    # ステータス表示
    st.markdown("### ワークフロー進捗")

    col1, col2, col3 = st.columns(3)

    phases = [
        (CheckPhase.PRE_SURVEY, col1),
        (CheckPhase.RANKING_CONFIRMED, col2),
        (CheckPhase.PRE_RELEASE, col3),
    ]

    for phase, col in phases:
        with col:
            record = status.phases.get(phase.value)
            label = PHASE_LABELS[phase]

            if record is not None:
                st.success(f"**{label}**\n\n完了: {record.executed_at[:10]}\n\n対象: {record.player_count}件")
            elif status.current_phase == phase.value:
                st.info(f"**{label}**\n\n→ 次に実行")
            else:
                st.markdown(f"**{label}**\n\n未実施")

    st.divider()

    # フェーズ選択
    st.markdown("### フェーズ選択")

    phase_choice = st.radio(
        "実行するフェーズ",
        [p.value for p in CheckPhase],
        format_func=lambda x: PHASE_LABELS[CheckPhase(x)],
        horizontal=True,
        key="workflow_phase_choice",
    )

    selected_phase = CheckPhase(phase_choice)
    config = PHASE_CONFIG[selected_phase]

    # フェーズ内容の説明
    with st.expander("フェーズの実行内容"):
        st.markdown(f"**{config['label']}**: {config['description']}")
        st.markdown(f"- 正誤チェック: `{config['validation_scope']}`")
        st.markdown(f"- 新規参入検出: `{'あり' if config['newcomer_detection'] else 'なし'}`")
        st.markdown(f"- 汎用調査: `{config['attribute_scope']}`")

        diff_base = config.get("diff_base_phase")
        if diff_base:
            st.markdown(f"- 差分基準: `{PHASE_LABELS[diff_base]}`")
        else:
            st.markdown("- 差分基準: なし（ベースライン作成）")

    st.divider()

    # プレイヤーリスト入力
    st.markdown("### プレイヤーリスト")

    uploaded_file = st.file_uploader(
        "プレイヤーリストExcelをアップロード",
        type=["xlsx", "xls"],
        key="workflow_excel_upload",
    )

    if "workflow_players" not in st.session_state:
        st.session_state.workflow_players = []
    if "workflow_results" not in st.session_state:
        st.session_state.workflow_results = []
    if "workflow_diff" not in st.session_state:
        st.session_state.workflow_diff = None

    if uploaded_file:
        try:
            temp_dir = Path(tempfile.gettempdir()) / "workflow_checker"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / uploaded_file.name
            temp_path.write_bytes(uploaded_file.getvalue())

            handler = ExcelHandler()
            players = handler.load(temp_path)
            st.session_state.workflow_players = players
            st.success(f"{len(players)}件のプレイヤーを読み込みました")

        except Exception as e:
            st.error(f"Excelの読み込みに失敗: {e}")

    # 実行ボタン
    players = st.session_state.workflow_players

    col1, col2 = st.columns([1, 3])
    with col1:
        check_limit = st.number_input(
            "チェック件数",
            min_value=1,
            max_value=len(players) if players else 100,
            value=min(10, len(players)) if players else 10,
            key="workflow_check_limit",
        )

    with col2:
        run_button = st.button(
            f"{PHASE_LABELS[selected_phase]}を実行",
            type="primary",
            disabled=not players or st.session_state.get("is_running", False),
            use_container_width=True,
            key="workflow_run_button",
        )

    st.divider()

    if run_button:
        st.session_state.is_running = True
        progress_container = st.empty()
        status_container = st.empty()

        # フェーズに応じた対象絞り込み
        target_players = workflow.get_validation_players(
            selected_phase, players[:check_limit], industry
        )

        logs = []

        def on_progress(current, total, name):
            log_msg = f"[{current}/{total}] チェック中: {name}"
            logs.append(log_msg)
            log_text = "\n".join(logs[-15:])
            progress_container.markdown(
                f'<div class="progress-log">{log_text}</div>',
                unsafe_allow_html=True,
            )

        status_container.info(
            f"{PHASE_LABELS[selected_phase]}: {len(target_players)}件をチェック中..."
        )

        try:
            llm = LLMClient()
            validator = PlayerValidator(llm_client=llm)

            results = run_async(validator.validate_batch(
                target_players,
                industry=industry,
                on_progress=on_progress,
                concurrency=2,
                delay_seconds=1.5,
            ))

            # 記録保存 + 差分計算
            summary = {
                "critical": sum(1 for r in results if r.alert_level == AlertLevel.CRITICAL),
                "warning": sum(1 for r in results if r.alert_level == AlertLevel.WARNING),
                "info": sum(1 for r in results if r.alert_level == AlertLevel.INFO),
                "ok": sum(1 for r in results if r.alert_level == AlertLevel.OK),
            }

            record = workflow.create_record(
                phase=selected_phase,
                industry=industry,
                player_count=len(results),
                summary=summary,
            )

            saved_record, diff_report = workflow.save_and_diff(record, results)

            st.session_state.workflow_results = results
            st.session_state.workflow_diff = diff_report

            status_container.success(
                f"{PHASE_LABELS[selected_phase]}完了: {len(results)}件チェック済み"
            )

        except Exception as e:
            status_container.error(f"エラー: {type(e).__name__}: {str(e)}")
            st.session_state.workflow_results = []

        st.session_state.is_running = False

    # 結果表示
    if st.session_state.workflow_results:
        results = st.session_state.workflow_results

        # サマリー
        st.markdown("### チェック結果サマリー")

        alert_counts = {}
        for level in AlertLevel:
            alert_counts[level] = sum(1 for r in results if r.alert_level == level)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("緊急", f"{alert_counts.get(AlertLevel.CRITICAL, 0)}件")
        with col2:
            st.metric("警告", f"{alert_counts.get(AlertLevel.WARNING, 0)}件")
        with col3:
            st.metric("情報", f"{alert_counts.get(AlertLevel.INFO, 0)}件")
        with col4:
            st.metric("正常", f"{alert_counts.get(AlertLevel.OK, 0)}件")

        # 差分レポート
        diff = st.session_state.workflow_diff
        if diff:
            st.markdown("### 前回との差分レポート")

            if diff.total_changes == 0:
                st.success("前回からの変更はありません。")
            else:
                st.warning(f"総変更数: {diff.total_changes}件")

                if diff.new_alerts:
                    st.markdown("**新規アラート:**")
                    for item in diff.new_alerts:
                        st.markdown(f"- {item.player_name}: {item.description}")

                if diff.resolved_alerts:
                    st.markdown("**解消アラート:**")
                    for item in diff.resolved_alerts:
                        st.markdown(f"- {item.player_name}: {item.description}")

                if diff.new_players:
                    st.markdown(f"**新規プレイヤー:** {', '.join(diff.new_players)}")

                if diff.removed_players:
                    st.markdown(f"**削除プレイヤー:** {', '.join(diff.removed_players)}")

                if diff.changed_attributes:
                    st.markdown("**属性変更:**")
                    for item in diff.changed_attributes:
                        st.markdown(f"- {item.player_name}: {item.description}")

    # 履歴表示
    st.divider()
    with st.expander("チェック履歴"):
        records = workflow.history.list_records(industry=industry)
        if records:
            history_data = []
            for r in records:
                history_data.append({
                    "ID": r.record_id,
                    "フェーズ": PHASE_LABELS.get(CheckPhase(r.phase), r.phase) if r.phase else "",
                    "実行日時": r.executed_at[:19] if r.executed_at else "",
                    "対象数": r.player_count,
                    "サマリー": str(r.summary),
                })
            st.dataframe(pd.DataFrame(history_data), use_container_width=True)
        else:
            st.info("チェック履歴はありません。")
