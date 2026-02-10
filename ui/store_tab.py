#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗調査 UIタブ
================
app_v5.py から店舗調査関連UIを分離。
attribute_tab.py のパターンに準拠。
"""

import io
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.async_helpers import run_async
from core.excel_handler import ExcelHandler, StoreInvestigationExporter
from core.llm_client import LLMClient
from investigators.base import StoreInvestigationResult
from investigators.store_investigator import StoreInvestigator, InvestigationMode
from ui.common import display_progress_log, display_filter_multiselect


# ====================================
# 内部関数
# ====================================
async def _run_investigation(
    companies: list[dict],
    mode: InvestigationMode,
    provider: str,
    progress_container,
    status_container,
    ai_model: str = "sonar-pro",
) -> list[StoreInvestigationResult]:
    """店舗調査を実行"""

    logs: list[str] = []

    def on_progress(current: int, total: int, name: str) -> None:
        log_msg = f"[{current}/{total}] 調査中: {name}"
        logs.append(log_msg)
        display_progress_log(logs, progress_container)

    model_label = "精密" if ai_model == "sonar-deep-research" else "高速"
    status_container.info(f"🏪 {len(companies)}件の企業を調査中... (モード: {model_label})")

    try:
        # 店舗調査は短時間で変わらないのでキャッシュ有効
        llm = LLMClient(provider=provider, enable_cache=True)
        investigator = StoreInvestigator(llm_client=llm, model=ai_model)

        results = await investigator.investigate_batch(
            companies,
            mode=mode,
            on_progress=on_progress,
            delay_seconds=1.5,
        )

        status_container.success(f"✅ 調査完了: {len(results)}件")
        return results

    except Exception as e:
        status_container.error(f"❌ エラー: {type(e).__name__}: {str(e)}")
        return []


def _display_summary(results: list[StoreInvestigationResult]):
    """店舗調査結果サマリーを表示"""

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


def _display_table(results: list[StoreInvestigationResult]) -> None:
    """店舗調査結果テーブルをフィルター付きで表示。

    Args:
        results: 店舗調査結果のリスト。
    """
    # --- フィルター ---
    confidence_options = ["高信頼度 (80%以上)", "中信頼度 (50-79%)", "低信頼度 (50%未満)"]
    col_filter1, col_filter2 = st.columns(2)

    with col_filter1:
        selected_confidence = display_filter_multiselect(
            "信頼度で絞り込み",
            options=confidence_options,
            key="store_filter_confidence",
        )

    with col_filter2:
        show_verify_only = st.checkbox(
            "要確認のみ表示",
            value=False,
            key="store_filter_verify",
        )

    # --- フィルター適用 ---
    def _confidence_matches(conf: float) -> bool:
        """信頼度がフィルター条件に合致するか判定する。"""
        if conf >= 0.8 and "高信頼度 (80%以上)" in selected_confidence:
            return True
        if 0.5 <= conf < 0.8 and "中信頼度 (50-79%)" in selected_confidence:
            return True
        if conf < 0.5 and "低信頼度 (50%未満)" in selected_confidence:
            return True
        return False

    filtered_results = [
        r for r in results
        if _confidence_matches(r.confidence or 0)
        and (not show_verify_only or r.needs_verification)
    ]

    st.caption(f"表示中: {len(filtered_results)} / {len(results)} 件")

    # --- ソート & テーブル表示 ---
    sorted_results = sorted(
        filtered_results,
        key=lambda r: (r.needs_verification, -(r.confidence or 0)),
    )

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
        },
    )


def _export_results(results: list[StoreInvestigationResult]) -> bytes:
    """店舗調査結果をExcelエクスポート"""

    buffer = io.BytesIO()

    temp_path = Path(tempfile.gettempdir()) / "store_results_temp.xlsx"
    exporter = StoreInvestigationExporter(include_prefectures=True)
    exporter.export(results, temp_path)

    with open(temp_path, "rb") as f:
        buffer.write(f.read())

    temp_path.unlink(missing_ok=True)

    return buffer.getvalue()


def _display_scraping_warning():
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


def _display_company_detail(result: StoreInvestigationResult):
    """企業別詳細を表示"""
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


# ====================================
# メインレンダリング
# ====================================
def render_store_tab(provider: str, industry: str):
    """店舗調査タブのUIをレンダリング"""

    # タブ固有のセッション状態初期化
    if "store_companies" not in st.session_state:
        st.session_state.store_companies = []
    if "store_results" not in st.session_state:
        st.session_state.store_results = []
    if "store_is_running" not in st.session_state:
        st.session_state.store_is_running = False

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
    ai_model = "sonar-pro"

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
        _display_scraping_warning()

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
            "企業名\t公式URL の形式で入力（タブ区切り or カンマ区切り）",
            placeholder="スターバックス\thttps://www.starbucks.co.jp/\nドトール\thttps://www.doutor.co.jp/",
            height=150,
        )

        if st.button("📝 入力内容を反映", key="apply_direct_input"):
            companies = []
            for line in input_text.strip().split("\n"):
                if not line.strip():
                    continue
                # タブ区切りを優先、なければカンマの最後の出現位置で分割
                if "\t" in line:
                    parts = line.split("\t", 1)
                elif ",http" in line:
                    # URL部分を安全に分離（企業名にカンマが含まれるケース対応）
                    idx = line.index(",http")
                    parts = [line[:idx], line[idx + 1:]]
                else:
                    parts = line.split(",", 1)
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
            disabled=not st.session_state.store_companies or st.session_state.store_is_running,
            use_container_width=True,
            key="store_run_button",
        )

    st.divider()

    if run_button:
        st.session_state.store_is_running = True

        progress_container = st.empty()
        status_container = st.empty()

        companies_to_check = st.session_state.store_companies[:check_limit]

        try:
            results = run_async(_run_investigation(
                companies_to_check,
                mode=investigation_mode,
                provider=provider,
                progress_container=progress_container,
                status_container=status_container,
                ai_model=ai_model,
            ))

            st.session_state.store_results = results
        except Exception as e:
            st.error(f"予期しないエラーが発生しました: {type(e).__name__}: {e}")
        finally:
            st.session_state.store_is_running = False

    # 結果表示
    if st.session_state.store_results:
        results = st.session_state.store_results

        _display_summary(results)

        st.divider()

        st.subheader("📋 詳細結果")
        _display_table(results)

        st.divider()

        st.subheader("📥 結果エクスポート")

        col1, col2 = st.columns(2)

        with col1:
            excel_data = _export_results(results)
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
            _display_company_detail(result)
