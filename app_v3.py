#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗情報スクレイピングツール GUI v3.0
=====================================
マルチ戦略対応 - どんな事業者でも店舗情報を抽出

【3段階アプローチ】
1. 静的HTML解析（高速・低コスト）
2. ブラウザ自動操作（JavaScript対応）
3. AI推論 + 複合アプローチ（最終手段）
"""

import asyncio
import csv
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

from store_scraper_v3 import MultiStrategyScraper, ScrapingResult

# ページ設定
st.set_page_config(
    page_title="店舗情報スクレイパー v3.0",
    page_icon="🏪",
    layout="wide"
)

# カスタムCSS
st.markdown("""
<style>
    .strategy-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
    }
    .strategy-static { background-color: #2ecc71; color: white; }
    .strategy-browser { background-color: #3498db; color: white; }
    .strategy-ai { background-color: #9b59b6; color: white; }
    .strategy-combined { background-color: #e74c3c; color: white; }
    .progress-log {
        background-color: #1a1a2e;
        color: #16f4d0;
        padding: 10px;
        border-radius: 5px;
        font-family: 'Consolas', monospace;
        font-size: 12px;
        max-height: 300px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)


# ====================================
# 初期化
# ====================================
def init_session_state():
    """セッション状態の初期化"""
    if "results" not in st.session_state:
        st.session_state.results = []
    if "progress_logs" not in st.session_state:
        st.session_state.progress_logs = []


def init_apis():
    """API初期化"""
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".env.local", override=True)

    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    gemini_key = os.getenv("GOOGLE_API_KEY")

    return perplexity_key, gemini_key


def get_strategy_badge(strategy: str) -> str:
    """戦略に応じたバッジを返す"""
    badges = {
        "static_html": ("静的解析", "strategy-static"),
        "browser_automation": ("ブラウザ", "strategy-browser"),
        "ai_inference": ("AI推論", "strategy-ai"),
        "combined": ("複合", "strategy-combined"),
    }
    label, css_class = badges.get(strategy, ("不明", "strategy-combined"))
    return f'<span class="strategy-badge {css_class}">{label}</span>'


# ====================================
# スクレイピング実行
# ====================================
async def run_scraping(
    company_name: str,
    url: str,
    provider: str,
    progress_container,
    status_container
) -> ScrapingResult:
    """スクレイピングを実行"""

    logs = []

    def on_progress(msg: str):
        logs.append(msg)
        # 最新10件を表示
        log_text = "\n".join(logs[-15:])
        progress_container.markdown(
            f'<div class="progress-log">{log_text}</div>',
            unsafe_allow_html=True
        )

    status_container.info(f"🚀 {company_name} をスクレイピング中...")

    try:
        scraper = MultiStrategyScraper(provider=provider)
        result = await scraper.scrape(
            company_name,
            url,
            on_progress=on_progress
        )

        if result.stores:
            status_container.success(
                f"✅ 完了: {len(result.stores)}件の店舗を抽出 "
                f"（戦略: {result.strategy_used}, 時間: {result.elapsed_time:.1f}秒）"
            )
        else:
            status_container.warning("⚠️ 店舗情報が取得できませんでした")

        return result

    except Exception as e:
        status_container.error(f"❌ エラー: {str(e)}")
        return ScrapingResult(
            company_name=company_name,
            url=url,
            stores=[],
            strategy_used="error",
            pages_visited=0,
            elapsed_time=0,
            errors=[str(e)]
        )


# ====================================
# UI
# ====================================
def main():
    init_session_state()

    st.title("🏪 店舗情報スクレイパー v3.0")
    st.caption("マルチ戦略対応 - どんな事業者でも店舗情報を自動抽出")

    # サイドバー
    with st.sidebar:
        st.header("⚙️ 設定")

        perplexity_key, gemini_key = init_apis()

        # API状態表示
        st.subheader("🔑 API接続")
        if perplexity_key:
            st.success(f"✅ Perplexity: ...{perplexity_key[-8:]}")
        else:
            st.warning("⚠️ Perplexity: 未設定")

        if gemini_key:
            st.success(f"✅ Gemini: ...{gemini_key[-8:]}")
        else:
            st.warning("⚠️ Gemini: 未設定")

        if not perplexity_key and not gemini_key:
            st.error("❌ 少なくとも1つのAPIキーが必要です")
            st.info("~/.env.local に設定してください")
            return

        # プロバイダー選択
        st.subheader("🤖 LLMプロバイダー")
        available_providers = []
        if perplexity_key:
            available_providers.append("perplexity")
        if gemini_key:
            available_providers.append("gemini")

        provider = st.selectbox(
            "使用するLLM",
            available_providers,
            format_func=lambda x: "Perplexity (推奨)" if x == "perplexity" else "Gemini"
        )

        st.divider()

        # 戦略説明
        st.subheader("📋 3段階戦略")
        st.markdown("""
        **1️⃣ 静的HTML解析**
        - 高速・低コスト
        - シンプルなサイト向け

        **2️⃣ ブラウザ自動操作**
        - JavaScript対応
        - 動的サイト向け

        **3️⃣ AI推論 + 複合**
        - 最終手段
        - APIエンドポイント推測
        - 外部検索活用
        """)

    # メインエリア
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📝 入力")

        input_method = st.radio(
            "入力方法",
            ["URL直接入力", "CSVアップロード", "サンプル企業"],
            horizontal=True
        )

        companies = []

        if input_method == "URL直接入力":
            company_name = st.text_input(
                "企業名",
                placeholder="例: アップルネット"
            )
            company_url = st.text_input(
                "公式サイトURL",
                placeholder="https://www.applenet.co.jp"
            )

            if company_name and company_url:
                companies = [(company_name, company_url)]

        elif input_method == "CSVアップロード":
            uploaded = st.file_uploader(
                "CSVファイル",
                type=["csv"],
                help="列: 企業名, URL"
            )
            if uploaded:
                content = uploaded.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    name = row.get("企業名", row.get("name", ""))
                    url = row.get("URL", row.get("url", ""))
                    if name and url:
                        companies.append((name, url))
                st.info(f"📂 {len(companies)}社を読み込み")

        else:
            # サンプル企業
            st.info("テスト用サンプル企業")
            samples = [
                ("アップルネット", "https://www.applenet.co.jp"),
                ("ライフスタジオ", "https://www.lifestudio.jp"),
                ("スターバックス", "https://www.starbucks.co.jp"),
            ]
            selected = st.selectbox(
                "サンプル企業を選択",
                samples,
                format_func=lambda x: f"{x[0]} ({x[1][:30]}...)"
            )
            if selected:
                companies = [selected]

        # 実行ボタン
        run_button = st.button(
            "🚀 スクレイピング開始",
            type="primary",
            disabled=not companies,
            use_container_width=True
        )

    with col2:
        st.subheader("📊 結果")
        result_area = st.container()

    # 実行処理
    if run_button and companies:
        all_stores = []
        all_results = []

        with result_area:
            for i, (name, url) in enumerate(companies):
                st.markdown(f"### {i+1}/{len(companies)}: {name}")

                progress_container = st.empty()
                status_container = st.empty()

                # 非同期実行
                result = asyncio.run(run_scraping(
                    name, url, provider,
                    progress_container, status_container
                ))

                all_results.append(result)
                all_stores.extend(result.stores)

                st.divider()

            # 結果表示
            if all_stores:
                st.success(f"🎉 合計 {len(all_stores)} 件の店舗を抽出")

                # 戦略サマリー
                strategies_used = set(r.strategy_used for r in all_results if r.strategy_used)
                st.markdown(
                    "**使用戦略**: " +
                    " ".join(get_strategy_badge(s) for s in strategies_used),
                    unsafe_allow_html=True
                )

                # データフレーム
                df = pd.DataFrame([asdict(s) for s in all_stores])
                df.columns = ["企業名", "店舗名", "住所", "電話番号", "URL", "都道府県", "営業時間", "FAX", "メール"]

                # 表示用に列を選択
                display_cols = ["企業名", "店舗名", "住所", "電話番号", "都道府県"]
                st.dataframe(
                    df[display_cols],
                    use_container_width=True,
                    height=400
                )

                # ダウンロードボタン
                col_a, col_b = st.columns(2)

                with col_a:
                    csv_data = df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        "📥 CSV ダウンロード",
                        csv_data,
                        f"店舗一覧_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv",
                        use_container_width=True
                    )

                with col_b:
                    # Excel出力
                    try:
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                            df.to_excel(writer, index=False, sheet_name="店舗一覧")
                        st.download_button(
                            "📥 Excel ダウンロード",
                            buffer.getvalue(),
                            f"店舗一覧_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except ImportError:
                        st.info("openpyxlが必要です: pip install openpyxl")

                # 詳細統計
                with st.expander("📈 詳細統計"):
                    st.write("**企業別店舗数**")
                    company_counts = df["企業名"].value_counts()
                    st.bar_chart(company_counts)

                    st.write("**都道府県別店舗数**")
                    pref_counts = df["都道府県"].value_counts()
                    st.bar_chart(pref_counts)

                    st.write("**処理時間**")
                    for result in all_results:
                        st.write(f"- {result.company_name}: {result.elapsed_time:.1f}秒 ({result.strategy_used})")

            else:
                st.warning("店舗情報が取得できませんでした")

                # エラー詳細
                for result in all_results:
                    if result.errors:
                        with st.expander(f"❌ {result.company_name} エラー詳細"):
                            for error in result.errors:
                                st.error(error)


if __name__ == "__main__":
    main()
