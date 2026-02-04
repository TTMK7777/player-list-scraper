#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プレイヤーリスト調査システム GUI v4.0
=====================================
プレイヤーリストの正誤チェック・調査を効率化する統合ツール

【機能】
- プレイヤーリスト正誤チェック（最優先）
- 店舗・教室の都道府県別調査（v3から継承）
- クレジットカード ブランド調査（予定）
- 動画配信サービス カテゴリ調査（予定）

【使用方法】
```bash
streamlit run app_v4.py
```
"""

import asyncio
import io
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# 自作モジュールのパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from core.excel_handler import ExcelHandler, ValidationReportExporter, PlayerData
from core.llm_client import LLMClient, get_available_providers, get_default_client
from investigators.base import AlertLevel, ChangeType, ValidationStatus, ValidationResult
from investigators.player_validator import PlayerValidator

# ページ設定
st.set_page_config(
    page_title="プレイヤーリスト調査システム v4.0",
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

    /* 結果テーブル */
    .result-table {
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)


# ====================================
# セッション状態
# ====================================
def init_session_state():
    """セッション状態の初期化"""
    if "players" not in st.session_state:
        st.session_state.players = []
    if "validation_results" not in st.session_state:
        st.session_state.validation_results = []
    if "progress_logs" not in st.session_state:
        st.session_state.progress_logs = []
    if "is_running" not in st.session_state:
        st.session_state.is_running = False


# ====================================
# API初期化
# ====================================
def init_apis():
    """API設定の初期化と表示"""
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
        # 最新15件を表示
        log_text = "\n".join(logs[-15:])
        progress_container.markdown(
            f'<div class="progress-log">{log_text}</div>',
            unsafe_allow_html=True
        )

    status_container.info(f"🔍 {len(players)}件のプレイヤーをチェック中...")

    try:
        # LLMクライアント作成
        llm = LLMClient(provider=provider)
        validator = PlayerValidator(llm_client=llm)

        # バッチ検証実行
        results = await validator.validate_batch(
            players,
            industry=industry,
            on_progress=on_progress,
            concurrency=2,  # 同時2件まで
            delay_seconds=1.5,  # 1.5秒間隔
        )

        status_container.success(f"✅ チェック完了: {len(results)}件")
        return results

    except Exception as e:
        status_container.error(f"❌ エラー: {str(e)}")
        return []


# ====================================
# 結果表示
# ====================================
def display_summary(results: list[ValidationResult]):
    """結果サマリーを表示"""

    # アラートレベル別にカウント
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

    # サマリーカード
    st.markdown("### 📊 チェック結果サマリー")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "🔴 緊急（撤退・統合）",
            f"{alert_counts[AlertLevel.CRITICAL]}件",
            delta=None,
        )

    with col2:
        st.metric(
            "🟡 警告（名称変更）",
            f"{alert_counts[AlertLevel.WARNING]}件",
            delta=None,
        )

    with col3:
        st.metric(
            "🟢 情報（URL変更等）",
            f"{alert_counts[AlertLevel.INFO]}件",
            delta=None,
        )

    with col4:
        st.metric(
            "✅ 変更なし",
            f"{alert_counts[AlertLevel.OK]}件",
            delta=None,
        )

    with col5:
        st.metric(
            "⚠️ 要確認",
            f"{uncertain_count}件",
            delta=None,
        )


def display_results_table(results: list[ValidationResult]):
    """結果テーブルを表示"""

    # アラートレベル順にソート（緊急 > 警告 > 情報 > 正常）
    alert_order = {
        AlertLevel.CRITICAL: 0,
        AlertLevel.WARNING: 1,
        AlertLevel.INFO: 2,
        AlertLevel.OK: 3,
    }
    sorted_results = sorted(results, key=lambda r: (alert_order.get(r.alert_level, 4), not r.needs_manual_review))

    # DataFrameに変換
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

    # テーブル表示
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


def export_results(results: list[ValidationResult]) -> tuple[bytes, bytes]:
    """結果をExcelエクスポート"""

    # レポート用DataFrame
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

    # Excelバイナリを生成
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_report.to_excel(writer, index=False, sheet_name="チェック結果")

        # 列幅調整
        worksheet = writer.sheets["チェック結果"]
        for idx, col in enumerate(df_report.columns):
            max_length = max(
                df_report[col].astype(str).map(len).max(),
                len(col)
            ) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)

    return buffer.getvalue()


# ====================================
# メインUI
# ====================================
def main():
    init_session_state()

    st.title("🔍 プレイヤーリスト調査システム v4.0")
    st.caption("プレイヤーリストの正誤チェック・変更検出を自動化")

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
                "その他",
            ],
            format_func=lambda x: "選択してください" if x == "" else x,
        )

        if industry == "その他":
            industry = st.text_input("業界名を入力", placeholder="例: フィットネスクラブ")

        st.divider()

        # 使い方
        st.subheader("📖 使い方")
        st.markdown("""
        1. **Excelアップロード**
           - プレイヤーリストをアップロード
           - 自動で列を検出

        2. **チェック実行**
           - 「正誤チェック開始」をクリック
           - 各プレイヤーの最新状態を調査

        3. **結果確認・出力**
           - アラートレベル別にサマリー表示
           - Excel形式で結果を出力
        """)

    # ====================================
    # メインエリア
    # ====================================

    # 調査タイプ選択
    st.subheader("📌 調査タイプを選択")

    investigation_type = st.radio(
        "調査タイプ",
        [
            "🔍 プレイヤーリスト 正誤チェック",
            "🏪 店舗・教室の都道府県別調査 (v3)",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    # ====================================
    # 正誤チェック
    # ====================================
    if "正誤チェック" in investigation_type:
        st.subheader("📂 Excelアップロード")

        uploaded_file = st.file_uploader(
            "プレイヤーリストExcelをアップロード",
            type=["xlsx", "xls"],
            help="サービス名/プレイヤー名、公式URL を含むExcelファイル",
        )

        if uploaded_file:
            # Excelを読み込み
            try:
                # 一時ファイルに保存
                temp_path = Path(f"/tmp/{uploaded_file.name}")
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_bytes(uploaded_file.getvalue())

                handler = ExcelHandler()
                players = handler.load(temp_path)
                st.session_state.players = players

                st.success(f"✅ {len(players)}件のプレイヤーを読み込みました")

                # 検出された列を表示
                with st.expander("📋 検出された列"):
                    cols = handler.get_column_names()
                    st.write(cols)

                # プレビュー
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

        # チェック実行ボタン
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

        # 実行処理
        if run_button:
            st.session_state.is_running = True

            progress_container = st.empty()
            status_container = st.empty()

            # チェック実行
            players_to_check = st.session_state.players[:check_limit]

            results = asyncio.run(run_validation(
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

            # サマリー
            display_summary(results)

            st.divider()

            # 詳細テーブル
            st.subheader("📋 詳細結果（アラートレベル順）")
            display_results_table(results)

            st.divider()

            # エクスポート
            st.subheader("📥 結果エクスポート")

            col1, col2 = st.columns(2)

            with col1:
                excel_data = export_results(results)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    "📥 Excel ダウンロード（チェック結果）",
                    excel_data,
                    f"validation_report_{timestamp}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            with col2:
                # CSV出力
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

            # 問題のあるプレイヤー詳細
            problem_results = [r for r in results if r.alert_level != AlertLevel.OK]
            if problem_results:
                st.divider()
                st.subheader("⚠️ 変更・問題があるプレイヤー 詳細")

                for result in problem_results:
                    with st.expander(f"{result.alert_level.value} {result.player_name_original}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**元の情報**")
                            st.write(f"- プレイヤー名: {result.player_name_original}")
                            st.write(f"- 公式URL: {result.url_original}")
                            st.write(f"- 運営会社: {result.company_name_original}")
                        with col2:
                            st.write("**現在の情報**")
                            st.write(f"- プレイヤー名: {result.player_name_current}")
                            st.write(f"- 公式URL: {result.url_current}")
                            st.write(f"- 運営会社: {result.company_name_current}")

                        st.write("**変更内容**")
                        if result.change_details:
                            for detail in result.change_details:
                                st.write(f"- {detail}")
                        else:
                            st.write("- なし")

                        if result.news_summary:
                            st.write("**関連ニュース**")
                            st.write(result.news_summary)

                        st.write(f"**信頼度**: {result.confidence * 100:.0f}%")

                        if result.source_urls:
                            st.write("**情報ソース**")
                            for url in result.source_urls:
                                st.write(f"- {url}")

    # ====================================
    # 店舗調査（v3へのリンク）
    # ====================================
    elif "店舗・教室" in investigation_type:
        st.info("🏪 店舗・教室の都道府県別調査は v3 アプリを使用してください")

        st.markdown("""
        ```bash
        # v3 アプリを起動
        streamlit run app_v3.py
        ```
        """)

        if st.button("📂 v3 アプリを起動"):
            os.system("start cmd /c streamlit run app_v3.py")
            st.success("v3 アプリを起動しました")


if __name__ == "__main__":
    main()
