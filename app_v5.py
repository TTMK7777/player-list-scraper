#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プレイヤーリスト調査システム GUI v5.0
=====================================
v3（店舗調査）とv4（正誤チェック）を統合。
AI調査をデフォルトとし、スクレイピングはオプションとして併存。

【機能】
- プレイヤーリスト正誤チェック（v4から継承）
- 店舗・教室調査（AI調査 推奨 + スクレイピング オプション）

【調査モード】
- AI調査（推奨）: LLMによるWeb検索ベース
- スクレイピング: サイト直接クローリング
- ハイブリッド: AI調査 → 低信頼度時にスクレイピング補完

【使用方法】
```bash
streamlit run app_v5.py
```
"""

import asyncio
import io
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# 自作モジュールのパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from core.async_helpers import run_async
from core.excel_handler import (
    ExcelHandler,
    ValidationReportExporter,
    StoreInvestigationExporter,
    PlayerData,
)
from core.llm_client import LLMClient, get_available_providers, get_default_client
from investigators.base import (
    AlertLevel,
    ChangeType,
    ValidationStatus,
    ValidationResult,
    StoreInvestigationResult,
)
from investigators.player_validator import PlayerValidator
from investigators.store_investigator import StoreInvestigator, InvestigationMode
from ui.attribute_tab import render_attribute_tab
from ui.newcomer_tab import render_newcomer_tab
from ui.workflow_tab import render_workflow_tab

# ページ設定
st.set_page_config(
    page_title="プレイヤーリスト調査システム v6.0",
    page_icon="🔍",
    layout="wide",
)

# カスタムCSS
st.markdown("""
<style>
    /* アラートバッジ */
    .alert-critical {
        background-color: #FF6B6B;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
    }
    .alert-warning {
        background-color: #FFD93D;
        color: #333;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
    }
    .alert-info {
        background-color: #6BCB77;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
    }
    .alert-ok {
        background-color: #4ECDC4;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
    }
    .alert-uncertain {
        background-color: #FFA500;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
    }

    /* サマリーカード */
    .summary-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        border-left: 5px solid #4A90D9;
    }

    /* 進捗ログ */
    .progress-log {
        background-color: #1a1a2e;
        color: #16f4d0;
        padding: 15px;
        border-radius: 8px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 13px;
        max-height: 300px;
        overflow-y: auto;
    }

    /* 警告ボックス */
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    }
    .warning-box h4 {
        color: #856404;
        margin-top: 0;
    }
    .warning-box ul {
        margin-bottom: 0;
        color: #856404;
    }

    /* 結果テーブル */
    .result-table {
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)


# ====================================
# セッション状態
# ====================================
def init_session_state() -> None:
    """Streamlit セッション状態を初期化"""
    # 正誤チェック用
    if "players" not in st.session_state:
        st.session_state.players = []
    if "validation_results" not in st.session_state:
        st.session_state.validation_results = []

    # 店舗調査用
    if "store_companies" not in st.session_state:
        st.session_state.store_companies = []
    if "store_results" not in st.session_state:
        st.session_state.store_results = []

    # 共通
    if "progress_logs" not in st.session_state:
        st.session_state.progress_logs = []
    if "is_running" not in st.session_state:
        st.session_state.is_running = False


# ====================================
# API初期化
# ====================================
def init_apis() -> dict[str, bool]:
    """API設定を初期化し、利用可能なプロバイダーを返す"""
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".env.local", override=True)

    providers = get_available_providers()
    return providers


# ====================================
# 正誤チェック実行
# ====================================
async def run_validation(
    players: list[PlayerData],
    industry: str,
    provider: str,
    progress_container,
    status_container,
) -> list[ValidationResult]:
    """正誤チェックを実行"""

    logs = []

    def on_progress(current: int, total: int, name: str):
        log_msg = f"[{current}/{total}] チェック中: {name}"
        logs.append(log_msg)
        log_text = "\n".join(logs[-15:])
        progress_container.markdown(
            f'<div class="progress-log">{log_text}</div>',
            unsafe_allow_html=True
        )

    status_container.info(f"🔍 {len(players)}件のプレイヤーをチェック中...")

    try:
        llm = LLMClient(provider=provider)
        validator = PlayerValidator(llm_client=llm)

        results = await validator.validate_batch(
            players,
            industry=industry,
            on_progress=on_progress,
            concurrency=2,
            delay_seconds=1.5,
        )

        status_container.success(f"✅ チェック完了: {len(results)}件")
        return results

    except Exception as e:
        status_container.error(f"❌ エラー: {type(e).__name__}: {str(e)}")
        return []


# ====================================
# 店舗調査実行
# ====================================
async def run_store_investigation(
    companies: list[dict],
    mode: InvestigationMode,
    provider: str,
    progress_container,
    status_container,
    ai_model: str = "sonar-pro",
) -> list[StoreInvestigationResult]:
    """店舗調査を実行

    Args:
        companies: 調査対象企業リスト
        mode: 調査モード（AI / SCRAPING / HYBRID）
        provider: LLMプロバイダー（perplexity / gemini）
        progress_container: 進捗表示用Streamlitコンテナ
        status_container: ステータス表示用Streamlitコンテナ
        ai_model: AIモデル（sonar-pro / sonar-deep-research）
    """

    logs = []

    def on_progress(current: int, total: int, name: str):
        log_msg = f"[{current}/{total}] 調査中: {name}"
        logs.append(log_msg)
        log_text = "\n".join(logs[-15:])
        progress_container.markdown(
            f'<div class="progress-log">{log_text}</div>',
            unsafe_allow_html=True
        )

    model_label = "精密" if ai_model == "sonar-deep-research" else "高速"
    status_container.info(f"🏪 {len(companies)}件の企業を調査中... (モード: {model_label})")

    try:
        llm = LLMClient(provider=provider)
        investigator = StoreInvestigator(llm_client=llm, model=ai_model)

        results = await investigator.investigate_batch(
            companies,
            mode=mode,
            on_progress=on_progress,
            concurrency=2,
            delay_seconds=1.5,
        )

        status_container.success(f"✅ 調査完了: {len(results)}件")
        return results

    except Exception as e:
        status_container.error(f"❌ エラー: {type(e).__name__}: {str(e)}")
        return []


# ====================================
# 結果表示（正誤チェック）
# ====================================
def display_validation_summary(results: list[ValidationResult]):
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


def display_validation_table(results: list[ValidationResult]):
    """正誤チェック結果テーブルを表示"""

    alert_order = {
        AlertLevel.CRITICAL: 0,
        AlertLevel.WARNING: 1,
        AlertLevel.INFO: 2,
        AlertLevel.OK: 3,
    }
    sorted_results = sorted(
        results,
        key=lambda r: (alert_order.get(r.alert_level, 4), not r.needs_manual_review)
    )

    data = []
    for result in sorted_results:
        data.append({
            "アラート": result.alert_level.value,
            "プレイヤー名（元）": result.player_name_original,
            "プレイヤー名（現在）": result.player_name_current,
            "変更タイプ": result.change_type.value,
            "変更内容": " / ".join(result.change_details) if result.change_details else "-",
            "信頼度": f"{result.confidence * 100:.0f}%",
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
            "信頼度": st.column_config.TextColumn("信頼度", width="small"),
            "要確認": st.column_config.TextColumn("要確認", width="small"),
        }
    )


# ====================================
# 結果表示（店舗調査）
# ====================================
def display_store_summary(results: list[StoreInvestigationResult]):
    """店舗調査結果サマリーを表示"""

    # None対策: total_stores や confidence が None の場合に備える
    total_stores = sum((r.total_stores or 0) for r in results)
    high_conf = sum(1 for r in results if (r.confidence or 0) >= 0.8)
    medium_conf = sum(1 for r in results if 0.5 <= (r.confidence or 0) < 0.8)
    low_conf = sum(1 for r in results if (r.confidence or 0) < 0.5)
    need_verify = sum(1 for r in results if r.needs_verification)

    st.markdown("### 📊 店舗調査結果サマリー")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("総店舗数", f"{total_stores:,}店舗")

    with col2:
        st.metric("🟢 高信頼度", f"{high_conf}件")

    with col3:
        st.metric("🟡 中信頼度", f"{medium_conf}件")

    with col4:
        st.metric("🔴 低信頼度", f"{low_conf}件")

    with col5:
        st.metric("⚠️ 要確認", f"{need_verify}件")


def display_store_table(results: list[StoreInvestigationResult]):
    """店舗調査結果テーブルを表示"""

    # 信頼度でソート（低い順）、None対策
    sorted_results = sorted(results, key=lambda r: (r.needs_verification, -(r.confidence or 0)))

    data = []
    for result in sorted_results:
        data.append({
            "企業名": result.company_name,
            "店舗数": result.total_stores or 0,
            "直営店": result.direct_stores if result.direct_stores is not None else "-",
            "FC店": result.franchise_stores if result.franchise_stores is not None else "-",
            "調査モード": result.investigation_mode,
            "信頼度": f"{(result.confidence or 0) * 100:.0f}%",
            "要確認": "⚠️" if result.needs_verification else "",
            "ソースURL": ", ".join(result.source_urls[:2]) if result.source_urls else "-",
        })

    df = pd.DataFrame(data)

    st.dataframe(
        df,
        use_container_width=True,
        height=400,
        column_config={
            "企業名": st.column_config.TextColumn("企業名", width="medium"),
            "店舗数": st.column_config.NumberColumn("店舗数", width="small"),
            "直営店": st.column_config.TextColumn("直営店", width="small"),
            "FC店": st.column_config.TextColumn("FC店", width="small"),
            "調査モード": st.column_config.TextColumn("調査モード", width="small"),
            "信頼度": st.column_config.TextColumn("信頼度", width="small"),
            "要確認": st.column_config.TextColumn("要確認", width="small"),
            "ソースURL": st.column_config.TextColumn("ソースURL", width="large"),
        }
    )


# ====================================
# エクスポート
# ====================================
def export_validation_results(results: list[ValidationResult]) -> bytes:
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
            "信頼度": f"{result.confidence * 100:.0f}%",
            "要確認フラグ": "TRUE" if result.needs_manual_review else "FALSE",
            "関連ニュース": result.news_summary,
            "情報ソース": "\n".join(result.source_urls) if result.source_urls else "",
            "チェック日時": result.checked_at.strftime("%Y-%m-%d %H:%M:%S") if result.checked_at else "",
        })

    df_report = pd.DataFrame(report_data)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_report.to_excel(writer, index=False, sheet_name="チェック結果")

        worksheet = writer.sheets["チェック結果"]
        for idx, col in enumerate(df_report.columns):
            max_length = max(
                df_report[col].astype(str).map(len).max(),
                len(col)
            ) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)

    return buffer.getvalue()


def export_store_results(results: list[StoreInvestigationResult]) -> bytes:
    """店舗調査結果をExcelエクスポート"""

    buffer = io.BytesIO()

    # 一時ファイルに保存
    temp_path = Path(tempfile.gettempdir()) / "store_results_temp.xlsx"
    exporter = StoreInvestigationExporter(include_prefectures=True)
    exporter.export(results, temp_path)

    # バイナリ読み込み
    with open(temp_path, "rb") as f:
        buffer.write(f.read())

    # 一時ファイル削除
    temp_path.unlink(missing_ok=True)

    return buffer.getvalue()


# ====================================
# スクレイピング注意事項
# ====================================
def display_scraping_warning():
    """スクレイピングモードの注意事項を表示"""
    st.markdown("""
    <div class="warning-box">
    <h4>⚠️ スクレイピングモードの注意事項</h4>
    <ul>
        <li>対象サイトの利用規約を必ずご確認ください</li>
        <li>robots.txt で禁止されている場合は使用しないでください</li>
        <li>本機能の使用による法的問題は利用者の責任となります</li>
        <li>社内利用のみを推奨します（外部公開データへの使用は非推奨）</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)


# ====================================
# メインUI
# ====================================
def main():
    init_session_state()

    st.title("🔍 プレイヤーリスト調査システム v6.0")
    st.caption("正誤チェック + 店舗調査 + 属性調査 + 新規参入検出 + 3段階チェック | AI調査（推奨）")

    # ====================================
    # サイドバー
    # ====================================
    with st.sidebar:
        st.header("⚙️ 設定")

        # API状態
        providers = init_apis()

        st.subheader("🔑 API接続")
        if providers.get("perplexity"):
            st.success("✅ Perplexity: 接続OK")
        else:
            st.warning("⚠️ Perplexity: 未設定")

        if providers.get("gemini"):
            st.success("✅ Gemini: 接続OK")
        else:
            st.warning("⚠️ Gemini: 未設定")

        if not any(providers.values()):
            st.error("❌ APIキーが設定されていません")
            st.info("~/.env.local に PERPLEXITY_API_KEY または GOOGLE_API_KEY を設定してください")
            st.stop()

        # プロバイダー選択
        available_providers = [k for k, v in providers.items() if v]
        provider = st.selectbox(
            "使用するLLM",
            available_providers,
            format_func=lambda x: "Perplexity (推奨)" if x == "perplexity" else "Gemini",
        )

        st.divider()

        # 業界選択
        st.subheader("📋 業界設定")
        industry = st.selectbox(
            "対象業界",
            [
                "",
                "クレジットカード",
                "動画配信サービス",
                "中古車販売店",
                "学習塾・予備校",
                "フィットネスクラブ",
                "飲食店",
                "小売店",
                "その他",
            ],
            format_func=lambda x: "選択してください" if x == "" else x,
        )

        if industry == "その他":
            industry = st.text_input("業界名を入力", placeholder="例: 美容室")

        st.divider()

        # 使い方
        st.subheader("📖 使い方")
        st.markdown("""
        **正誤チェック**
        1. Excelアップロード → 「正誤チェック開始」

        **店舗調査**
        1. 調査モード選択 → 企業入力 → 「店舗調査開始」

        **属性調査** (NEW)
        1. プリセット選択 → Excel入力 → 「属性調査開始」

        **新規参入検出** (NEW)
        1. 既存リスト入力 → 「新規参入を検索」

        **3段階チェック** (NEW)
        1. フェーズ選択 → Excel入力 → フェーズ実行
        """)

    # ====================================
    # メインエリア: 機能選択
    # ====================================
    st.subheader("📌 機能を選択")

    function_type = st.radio(
        "機能タイプ",
        [
            "🔍 正誤チェック",
            "🏪 店舗調査",
            "📊 属性調査",
            "🆕 新規参入検出",
            "📋 3段階チェック",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    # ====================================
    # 正誤チェック機能
    # ====================================
    if "属性調査" in function_type:
        render_attribute_tab(provider=provider, industry=industry)

    elif "新規参入検出" in function_type:
        render_newcomer_tab(provider=provider, industry=industry)

    elif "3段階チェック" in function_type:
        render_workflow_tab(provider=provider, industry=industry)

    elif "正誤チェック" in function_type:
        st.subheader("📂 Excelアップロード")

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

                handler = ExcelHandler()
                players = handler.load(temp_path)
                st.session_state.players = players

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
                st.session_state.players = []

        # チェック実行
        col1, col2 = st.columns([1, 3])
        with col1:
            check_limit = st.number_input(
                "チェック件数",
                min_value=1,
                max_value=len(st.session_state.players) if st.session_state.players else 100,
                value=min(10, len(st.session_state.players)) if st.session_state.players else 10,
                help="APIコスト削減のため、最初は少数でテストしてください",
            )

        with col2:
            run_button = st.button(
                "🚀 正誤チェック開始",
                type="primary",
                disabled=not st.session_state.players or st.session_state.is_running,
                use_container_width=True,
            )

        st.divider()

        if run_button:
            st.session_state.is_running = True

            progress_container = st.empty()
            status_container = st.empty()

            players_to_check = st.session_state.players[:check_limit]

            results = run_async(run_validation(
                players_to_check,
                industry=industry,
                provider=provider,
                progress_container=progress_container,
                status_container=status_container,
            ))

            st.session_state.validation_results = results
            st.session_state.is_running = False

        # 結果表示
        if st.session_state.validation_results:
            results = st.session_state.validation_results

            display_validation_summary(results)

            st.divider()

            st.subheader("📋 詳細結果（アラートレベル順）")
            display_validation_table(results)

            st.divider()

            st.subheader("📥 結果エクスポート")

            col1, col2 = st.columns(2)

            with col1:
                excel_data = export_validation_results(results)
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

    # ====================================
    # 店舗調査機能
    # ====================================
    elif "店舗調査" in function_type:
        st.subheader("🔧 調査モード選択")

        mode_option = st.radio(
            "調査モード",
            [
                "🤖 AI調査（高速）",
                "🔬 AI調査（精密）",
                "🔗 スクレイピング",
                "🔄 ハイブリッド（AI + スクレイピング補完）",
            ],
            horizontal=True,
            label_visibility="collapsed",
        )

        # モード変換 & モデル選択
        ai_model = "sonar-pro"  # デフォルト

        if "AI調査（高速）" in mode_option:
            investigation_mode = InvestigationMode.AI
            ai_model = "sonar-pro"
        elif "AI調査（精密）" in mode_option:
            investigation_mode = InvestigationMode.AI
            ai_model = "sonar-deep-research"
            st.warning(
                "⏳ **精密モード（sonar-deep-research）の注意事項**\n\n"
                "- 1件あたり約5分かかります\n"
                "- コストが約10〜50倍になります\n"
                "- 通常モードで `?` が多い場合のみ推奨\n\n"
                "まずは「AI調査（高速）」でテストしてください。"
            )
        elif "スクレイピング" in mode_option:
            investigation_mode = InvestigationMode.SCRAPING
        else:
            investigation_mode = InvestigationMode.HYBRID

        # スクレイピング注意事項
        if investigation_mode in (InvestigationMode.SCRAPING, InvestigationMode.HYBRID):
            display_scraping_warning()

        st.divider()

        # 入力タブ
        st.subheader("📂 企業情報入力")

        input_tab1, input_tab2 = st.tabs(["📤 Excelアップロード", "✏️ 直接入力"])

        with input_tab1:
            uploaded_file = st.file_uploader(
                "企業リストExcelをアップロード",
                type=["xlsx", "xls"],
                help="企業名、公式URL を含むExcelファイル",
                key="store_excel_upload",
            )

            if uploaded_file:
                try:
                    temp_dir = Path(tempfile.gettempdir()) / "store_investigator"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = temp_dir / uploaded_file.name
                    temp_path.write_bytes(uploaded_file.getvalue())

                    handler = ExcelHandler()
                    players = handler.load(temp_path)

                    # 企業情報に変換
                    companies = []
                    for p in players:
                        companies.append({
                            "company_name": p.company_name or p.player_name,
                            "official_url": p.official_url,
                            "industry": industry,
                        })

                    st.session_state.store_companies = companies
                    st.success(f"✅ {len(companies)}件の企業を読み込みました")

                    with st.expander("👀 データプレビュー（先頭10件）"):
                        preview_data = []
                        for c in companies[:10]:
                            preview_data.append({
                                "企業名": c["company_name"],
                                "公式URL": c["official_url"][:50] + "..." if len(c["official_url"]) > 50 else c["official_url"],
                            })
                        st.dataframe(pd.DataFrame(preview_data), use_container_width=True)

                except Exception as e:
                    st.error(f"❌ Excelの読み込みに失敗: {e}")
                    st.session_state.store_companies = []

        with input_tab2:
            st.markdown("**企業情報を直接入力**（1行1企業）")

            input_text = st.text_area(
                "企業名,公式URL の形式で入力",
                placeholder="スターバックス,https://www.starbucks.co.jp/\nドトール,https://www.doutor.co.jp/",
                height=150,
            )

            if st.button("📝 入力内容を反映", key="apply_direct_input"):
                companies = []
                for line in input_text.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split(",")
                    company_name = parts[0].strip()
                    official_url = parts[1].strip() if len(parts) > 1 else ""

                    companies.append({
                        "company_name": company_name,
                        "official_url": official_url,
                        "industry": industry,
                    })

                if companies:
                    st.session_state.store_companies = companies
                    st.success(f"✅ {len(companies)}件の企業を登録しました")
                else:
                    st.warning("⚠️ 企業情報を入力してください")

        st.divider()

        # 調査実行
        col1, col2 = st.columns([1, 3])
        with col1:
            check_limit = st.number_input(
                "調査件数",
                min_value=1,
                max_value=len(st.session_state.store_companies) if st.session_state.store_companies else 100,
                value=min(5, len(st.session_state.store_companies)) if st.session_state.store_companies else 5,
                help="APIコスト削減のため、最初は少数でテストしてください",
                key="store_check_limit",
            )

        with col2:
            run_button = st.button(
                "🚀 店舗調査開始",
                type="primary",
                disabled=not st.session_state.store_companies or st.session_state.is_running,
                use_container_width=True,
                key="store_run_button",
            )

        st.divider()

        if run_button:
            st.session_state.is_running = True

            progress_container = st.empty()
            status_container = st.empty()

            companies_to_check = st.session_state.store_companies[:check_limit]

            results = run_async(run_store_investigation(
                companies_to_check,
                mode=investigation_mode,
                provider=provider,
                progress_container=progress_container,
                status_container=status_container,
                ai_model=ai_model,
            ))

            st.session_state.store_results = results
            st.session_state.is_running = False

        # 結果表示
        if st.session_state.store_results:
            results = st.session_state.store_results

            display_store_summary(results)

            st.divider()

            st.subheader("📋 詳細結果")
            display_store_table(results)

            st.divider()

            st.subheader("📥 結果エクスポート")

            col1, col2 = st.columns(2)

            with col1:
                excel_data = export_store_results(results)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    "📥 Excel ダウンロード（店舗調査結果）",
                    excel_data,
                    f"store_investigation_{timestamp}.xlsx",
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
                    f"store_investigation_{timestamp}.csv",
                    "text/csv",
                    use_container_width=True,
                )

            # 詳細表示
            st.divider()
            st.subheader("📝 企業別詳細")

            for result in results:
                stores_display = result.total_stores or 0
                conf_display = (result.confidence or 0) * 100
                with st.expander(f"{'⚠️' if result.needs_verification else '✅'} {result.company_name} - {stores_display}店舗"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write("**基本情報**")
                        st.write(f"- 総店舗数: {stores_display}")
                        if result.direct_stores is not None:
                            st.write(f"- 直営店: {result.direct_stores}")
                        if result.franchise_stores is not None:
                            st.write(f"- FC店: {result.franchise_stores}")
                        st.write(f"- 調査モード: {result.investigation_mode}")
                        st.write(f"- 信頼度: {conf_display:.0f}%")

                    with col2:
                        st.write("**情報ソース**")
                        if result.source_urls:
                            for url in result.source_urls:
                                st.write(f"- {url}")
                        else:
                            st.write("- なし")

                    if result.prefecture_distribution:
                        st.write("**都道府県別店舗数**")
                        pref_df = pd.DataFrame([
                            {"都道府県": k, "店舗数": v}
                            for k, v in result.prefecture_distribution.items()
                        ]).sort_values("店舗数", ascending=False)
                        st.dataframe(pref_df, use_container_width=True, height=200)

                    if result.notes:
                        st.write("**備考**")
                        st.write(result.notes)


if __name__ == "__main__":
    main()
