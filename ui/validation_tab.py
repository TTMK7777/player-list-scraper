#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
正誤チェック UIタブ
====================
app_v5.py から正誤チェック関連UIを分離。
attribute_tab.py のパターンに準拠。
"""

import io
import tempfile
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st

from core.async_helpers import run_async
from core.excel_handler import ExcelHandler, PlayerData
from core.llm_client import LLMClient
from investigators.base import AlertLevel, ValidationResult
from investigators.player_validator import PlayerValidator
from ui.common import display_progress_log, display_filter_multiselect, display_cost_estimate, select_sheet_if_multiple


# ====================================
# 内部関数
# ====================================
async def _run_validation(
    players: list[PlayerData],
    industry: str,
    progress_container,
    status_container,
) -> list[ValidationResult]:
    """正誤チェックを実行"""

    logs: list[str] = []

    def on_progress(current: int, total: int, name: str) -> None:
        log_msg = f"[{current}/{total}] チェック中: {name}"
        logs.append(log_msg)
        display_progress_log(logs, progress_container)

    status_container.info(f"🔍 {len(players)}件のプレイヤーをチェック中...")

    try:
        llm = LLMClient()
        validator = PlayerValidator(llm_client=llm)

        results = await validator.validate_batch(
            players,
            industry=industry,
            on_progress=on_progress,
            delay_seconds=1.5,
        )

        status_container.success(f"✅ チェック完了: {len(results)}件")
        return results

    except Exception as e:
        status_container.error(f"❌ エラー: {type(e).__name__}: {str(e)}")
        return []


def _display_summary(results: list[ValidationResult]):
    """正誤チェック結果サマリーを表示"""

    alert_counts = {
        AlertLevel.CRITICAL: 0,
        AlertLevel.WARNING: 0,
        AlertLevel.INFO: 0,
        AlertLevel.OK: 0,
    }
    uncertain_count = 0

    for result in results:
        alert_counts[result.alert_level] = alert_counts.get(result.alert_level, 0) + 1
        if result.needs_manual_review:
            uncertain_count += 1

    st.markdown("### 📊 チェック結果サマリー")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("🔴 緊急（撤退・統合）", f"{alert_counts[AlertLevel.CRITICAL]}件")

    with col2:
        st.metric("🟡 警告（名称変更）", f"{alert_counts[AlertLevel.WARNING]}件")

    with col3:
        st.metric("🟢 情報（URL変更等）", f"{alert_counts[AlertLevel.INFO]}件")

    with col4:
        st.metric("✅ 変更なし", f"{alert_counts[AlertLevel.OK]}件")

    with col5:
        st.metric("⚠️ 要確認", f"{uncertain_count}件")


def _display_table(results: list[ValidationResult]) -> None:
    """正誤チェック結果テーブルをフィルター付きで表示。

    Args:
        results: 正誤チェック結果のリスト。
    """
    # --- フィルター ---
    alert_labels = [level.value for level in AlertLevel]
    col_filter1, col_filter2 = st.columns(2)

    with col_filter1:
        selected_alerts = display_filter_multiselect(
            "アラートレベルで絞り込み",
            options=alert_labels,
            key="val_filter_alert",
        )

    with col_filter2:
        show_manual_only = st.checkbox(
            "要確認のみ表示",
            value=False,
            key="val_filter_manual",
        )

    # --- フィルター適用 ---
    filtered_results = [
        r for r in results
        if r.alert_level.value in selected_alerts
        and (not show_manual_only or r.needs_manual_review)
    ]

    st.caption(f"表示中: {len(filtered_results)} / {len(results)} 件")

    # --- ソート & テーブル表示 ---
    alert_order = {
        AlertLevel.CRITICAL: 0,
        AlertLevel.WARNING: 1,
        AlertLevel.INFO: 2,
        AlertLevel.OK: 3,
    }
    sorted_results = sorted(
        filtered_results,
        key=lambda r: (alert_order.get(r.alert_level, 4), not r.needs_manual_review),
    )

    data = []
    for result in sorted_results:
        data.append({
            "アラート": result.alert_level.value,
            "プレイヤー名（元）": result.player_name_original,
            "プレイヤー名（現在）": result.player_name_current,
            "変更タイプ": result.change_type.value,
            "変更内容": " / ".join(result.change_details) if result.change_details else "-",
            "要確認": "⚠️" if result.needs_manual_review else "",
        })

    df = pd.DataFrame(data)

    st.dataframe(
        df,
        use_container_width=True,
        height=400,
        column_config={
            "アラート": st.column_config.TextColumn("アラート", width="small"),
            "プレイヤー名（元）": st.column_config.TextColumn("プレイヤー名（元）", width="medium"),
            "プレイヤー名（現在）": st.column_config.TextColumn("プレイヤー名（現在）", width="medium"),
            "変更タイプ": st.column_config.TextColumn("変更タイプ", width="small"),
            "変更内容": st.column_config.TextColumn("変更内容", width="large"),
            "要確認": st.column_config.TextColumn("要確認", width="small"),
        },
    )


def _export_results(results: list[ValidationResult]) -> bytes:
    """正誤チェック結果をExcelエクスポート"""

    report_data = []
    for result in results:
        report_data.append({
            "アラート": result.alert_level.value,
            "プレイヤー名（元）": result.player_name_original,
            "プレイヤー名（現在）": result.player_name_current,
            "変更タイプ": result.change_type.value,
            "変更内容": "\n".join(result.change_details) if result.change_details else "",
            "公式URL（元）": result.url_original,
            "公式URL（現在）": result.url_current,
            "運営会社（元）": result.company_name_original,
            "運営会社（現在）": result.company_name_current,
            "要確認フラグ": "TRUE" if result.needs_manual_review else "FALSE",
            "関連ニュース": result.news_summary,
            "情報ソース": "\n".join(result.source_urls) if result.source_urls else "",
            "チェック日時": result.checked_at.strftime("%Y-%m-%d %H:%M:%S") if result.checked_at else "",
        })

    df_report = pd.DataFrame(report_data)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_report.to_excel(writer, index=False, sheet_name="チェック結果")

        from openpyxl.utils import get_column_letter

        worksheet = writer.sheets["チェック結果"]
        for idx, col in enumerate(df_report.columns):
            max_length = max(
                df_report[col].astype(str).map(len).max(),
                len(col)
            ) + 2
            worksheet.column_dimensions[get_column_letter(idx + 1)].width = min(max_length, 50)

    return buffer.getvalue()


# ====================================
# メインレンダリング
# ====================================
def render_validation_tab(industry: str):
    """正誤チェックタブのUIをレンダリング"""

    # タブ固有のセッション状態初期化
    if "val_players" not in st.session_state:
        st.session_state.val_players = []
    if "val_results" not in st.session_state:
        st.session_state.val_results = []
    if "val_is_running" not in st.session_state:
        st.session_state.val_is_running = False

    st.subheader("📂 Excelアップロード")

    st.info("既存プレイヤーリストの**撤退・統合・名称変更**をGemini AIが自動検出します。アラートレベル別にExcelレポートを出力できます。")

    uploaded_file = st.file_uploader(
        "プレイヤーリストExcelをアップロード",
        type=["xlsx", "xls"],
        help="サービス名/プレイヤー名、公式URL を含むExcelファイル",
    )

    if uploaded_file:
        try:
            temp_dir = Path(tempfile.gettempdir()) / "player_list_checker"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / uploaded_file.name
            temp_path.write_bytes(uploaded_file.getvalue())

            selected_sheet = select_sheet_if_multiple(temp_path, "val")
            handler = ExcelHandler()
            players = handler.load(temp_path, sheet_name=selected_sheet)
            st.session_state.val_players = players

            st.success(f"✅ {len(players)}件のプレイヤーを読み込みました")

            with st.expander("📋 検出された列"):
                cols = handler.get_column_names()
                st.write(cols)

            with st.expander("👀 データプレビュー（先頭10件）"):
                preview_data = []
                for p in players[:10]:
                    preview_data.append({
                        "プレイヤー名": p.player_name,
                        "公式URL": p.official_url[:50] + "..." if len(p.official_url) > 50 else p.official_url,
                        "運営会社": p.company_name,
                    })
                st.dataframe(pd.DataFrame(preview_data), use_container_width=True)

        except Exception as e:
            st.error(f"❌ Excelの読み込みに失敗: {e}")
            st.session_state.val_players = []

    # チェック実行
    col1, col2 = st.columns([1, 3])
    with col1:
        check_limit = st.number_input(
            "チェック件数",
            min_value=1,
            max_value=len(st.session_state.val_players) if st.session_state.val_players else 100,
            value=min(10, len(st.session_state.val_players)) if st.session_state.val_players else 10,
            help="APIコスト削減のため、最初は少数でテストしてください",
        )

    with col2:
        run_button = st.button(
            "🚀 正誤チェック開始",
            type="primary",
            disabled=not st.session_state.val_players or st.session_state.val_is_running,
            use_container_width=True,
        )

    # コスト概算表示
    if st.session_state.val_players:
        cost = PlayerValidator.estimate_cost(check_limit)
        display_cost_estimate(
            call_count=cost["call_count"],
            cost_per_call=cost["cost_per_call"],
            label="正誤チェック",
        )

    st.divider()

    if run_button:
        st.session_state.val_is_running = True

        progress_container = st.empty()
        status_container = st.empty()

        players_to_check = st.session_state.val_players[:check_limit]
        # UI境界: 空文字→None正規化
        industry_normalized = industry.strip() or None if industry else None

        try:
            results = run_async(_run_validation(
                players_to_check,
                industry=industry_normalized,
                progress_container=progress_container,
                status_container=status_container,
            ))

            st.session_state.val_results = results
        except Exception as e:
            st.error(f"予期しないエラーが発生しました: {type(e).__name__}: {e}")
        finally:
            st.session_state.val_is_running = False

    # 結果表示
    if st.session_state.val_results:
        results = st.session_state.val_results

        _display_summary(results)

        st.divider()

        st.subheader("📋 詳細結果（アラートレベル順）")
        _display_table(results)

        st.divider()

        st.subheader("📥 結果エクスポート")

        col1, col2 = st.columns(2)

        with col1:
            excel_data = _export_results(results)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "📥 Excel ダウンロード（チェック結果）",
                excel_data,
                f"validation_report_{timestamp}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        with col2:
            csv_data = []
            for result in results:
                csv_data.append(result.to_dict())
            df_csv = pd.DataFrame(csv_data)
            csv_bytes = df_csv.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                "📥 CSV ダウンロード",
                csv_bytes,
                f"validation_report_{timestamp}.csv",
                "text/csv",
                use_container_width=True,
            )
