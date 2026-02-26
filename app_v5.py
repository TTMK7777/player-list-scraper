#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プレイヤーリスト調査システム GUI v6.3
=====================================
v3（店舗調査）とv4（正誤チェック）を統合。
AI調査をデフォルトとし、スクレイピングはオプションとして併存。

【機能】
- プレイヤーリスト正誤チェック
- 店舗・教室調査（AI調査 推奨 + スクレイピング オプション）
- 属性調査（カテゴリ/ブランド）
- 新規参入検出
- 3段階チェック（ワークフロー）

【使用方法】
```bash
streamlit run app_v5.py
```
"""

import os
import sys
from pathlib import Path

import streamlit as st

# 自作モジュールのパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from core.logger import setup_logging
from core.llm_client import is_api_available

# ロギング設定（モジュール読み込み時に1度だけ実行）
setup_logging()
from ui.attribute_tab import render_investigation_tab
from ui.newcomer_tab import render_newcomer_tab
from ui.store_tab import render_store_tab
from ui.validation_tab import render_validation_tab
from ui.workflow_tab import render_workflow_tab

# ページ設定
st.set_page_config(
    page_title="プレイヤーリスト調査システム v6.3",
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
# API初期化
# ====================================
def init_apis() -> bool:
    """API設定を初期化し、Gemini API の利用可否を返す"""
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".env.local", override=True)

    # Streamlit Cloud: st.secrets → os.environ に注入
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            os.environ["GOOGLE_API_KEY"] = st.secrets["GOOGLE_API_KEY"]
    except Exception:
        pass  # ローカル環境では st.secrets が存在しないため無視

    return is_api_available()


# ====================================
# パスワード認証
# ====================================
def check_password() -> bool:
    """パスワード認証画面を表示し、認証済みなら True を返す"""
    if st.session_state.get("authenticated"):
        return True

    st.title("🔐 プレイヤーリスト調査システム")
    st.subheader("ログイン")
    password = st.text_input("パスワード", type="password", placeholder="パスワードを入力")

    if st.button("ログイン", type="primary"):
        app_password = st.secrets.get("APP_PASSWORD", "")
        if app_password and password == app_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")

    st.stop()


# ====================================
# メインUI
# ====================================
def main():
    check_password()
    st.title("🔍 プレイヤーリスト調査システム v6.3")
    st.caption("正誤チェック + 汎用調査 + 店舗調査 + 新規参入検出 + 3段階チェック | AI調査（推奨）")

    # ====================================
    # サイドバー
    # ====================================
    with st.sidebar:
        st.header("⚙️ 設定")

        # API状態
        api_available = init_apis()

        st.subheader("🔑 API接続")
        if api_available:
            st.success("✅ Gemini: 接続OK")
        else:
            st.error("❌ GOOGLE_API_KEY が設定されていません")
            st.info("~/.env.local またはStreamlit Cloud の Secrets に GOOGLE_API_KEY を設定してください")
            st.stop()

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

        **汎用調査**
        1. テンプレート選択 → Excel入力 → 「調査開始」

        **新規参入検出**
        1. 既存リスト入力 → 「新規参入を検索」

        **3段階チェック**
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
            "📊 汎用調査",
            "🏪 店舗調査（従来版）",
            "🆕 新規参入検出",
            "📋 3段階チェック",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    # ====================================
    # 機能分岐（各タブモジュールに委譲）
    # ====================================
    if "汎用調査" in function_type:
        render_investigation_tab(industry=industry)
    elif "新規参入検出" in function_type:
        render_newcomer_tab(industry=industry)
    elif "3段階チェック" in function_type:
        render_workflow_tab(industry=industry)
    elif "正誤チェック" in function_type:
        render_validation_tab(industry=industry)
    elif "店舗調査" in function_type:
        render_store_tab(industry=industry)


if __name__ == "__main__":
    main()
