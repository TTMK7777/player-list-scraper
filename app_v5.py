#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プレイヤーリスト調査システム GUI v7.0
=====================================
プレイヤーの最新動向（正誤チェック+新規参入+リスト作成）を統合タブで提供。

【機能】
- プレイヤーの最新動向（変更点調査 + 新規参入検出 + 最新版リスト作成）
- カテゴリチェック（属性調査）
- 店舗・教室調査（AI調査 推奨 + スクレイピング オプション）
- 3段階チェック（ワークフロー）

【使用方法】
```bash
streamlit run app_v5.py
```
"""

import hmac
import os
import sys
from pathlib import Path

import streamlit as st

# 自作モジュールのパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from core.constants import __version__
from core.logger import setup_logging
from core.app_logger import setup_app_logging, render_debug_log
from core.llm_client import is_api_available, DEFAULT_MODEL
from core.perplexity_client import is_perplexity_available

# ロギング設定（モジュール読み込み時に1度だけ実行）
setup_logging()
setup_app_logging()
from ui.attribute_tab import render_investigation_tab
from ui.player_trend_tab import render_player_trend_tab
from ui.store_tab import render_store_tab
from ui.workflow_tab import render_workflow_tab

# ページ設定
st.set_page_config(
    page_title=f"プレイヤーリスト調査システム v{__version__}",
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

    # Perplexity APIキーも同様に st.secrets から読み込み（Streamlit Cloud対応）
    try:
        if "PERPLEXITY_API_KEY" in st.secrets:
            os.environ["PERPLEXITY_API_KEY"] = st.secrets["PERPLEXITY_API_KEY"]
    except Exception:
        pass

    return is_api_available()


# ====================================
# パスワード認証
# ====================================
def check_password() -> bool:
    """パスワード認証画面を表示し、認証済みなら True を返す"""
    if st.session_state.get("authenticated"):
        return True

    # ログイン試行回数の初期化
    if "login_attempts" not in st.session_state:
        st.session_state.login_attempts = 0

    st.title("🔐 プレイヤーリスト調査システム")
    st.subheader("ログイン")

    if st.session_state.login_attempts >= 5:
        st.error("ログイン試行回数の上限を超えました。しばらく時間をおいてから再度お試しください。")
        st.stop()

    password = st.text_input("パスワード", type="password", placeholder="パスワードを入力")

    if st.button("ログイン", type="primary"):
        app_password = st.secrets.get("APP_PASSWORD", "")
        if not app_password:
            st.error("APP_PASSWORD が設定されていません。管理者に連絡してください。")
            st.stop()
        if hmac.compare_digest(password, app_password):
            st.session_state.authenticated = True
            st.session_state.login_attempts = 0
            st.rerun()
        else:
            st.session_state.login_attempts += 1
            st.error("パスワードが違います")

    st.stop()


# ====================================
# メインUI
# ====================================
def main():
    check_password()
    st.title(f"🔍 プレイヤーリスト調査システム v{__version__}")
    st.caption("プレイヤーの最新動向 + カテゴリチェック + 店舗・教室調査 + 3段階チェック | AI調査（推奨）")

    # ====================================
    # サイドバー
    # ====================================
    with st.sidebar:
        st.header("⚙️ 設定")

        # API状態
        api_available = init_apis()

        st.subheader("🔑 API接続")
        if api_available:
            st.success(f"✅ Gemini: 接続OK（モデル: {DEFAULT_MODEL}）")
        else:
            st.error("❌ GOOGLE_API_KEY が設定されていません")
            st.info("~/.env.local またはStreamlit Cloud の Secrets に GOOGLE_API_KEY を設定してください")
            st.stop()

        # Perplexity 補助検索エンジンの状態表示
        if is_perplexity_available():
            st.success("✅ Perplexity: 接続OK（補助検索）")
        else:
            st.info("💡 Perplexity: 未設定（補助検索なしで動作します）")

        st.divider()

        # 業界設定（validation/attribute/workflow で使用）
        st.subheader("📋 業界設定")
        industry = st.text_input(
            "対象業界",
            placeholder="例: クレジットカード、動画配信サービス",
        )
        st.caption("⚡ 設定すると検索精度が向上します（最新動向・カテゴリチェック・3段階チェックで使用）")

        definition = st.text_area(
            "定義（任意）",
            placeholder="例: 月額課金制の映像ストリーミング。無料動画共有は除外",
            height=80,
            max_chars=200,
        )
        st.caption("💡 仮でもOK。業界の範囲や除外条件を指定するとAI判定の精度が上がります")

        st.divider()

        # 調査期間設定（任意）
        st.subheader("📅 調査期間")
        from datetime import datetime as _dt
        _current_year = _dt.now().year
        _current_month = _dt.now().month
        _default_year = _current_year - 1
        _col_y, _col_m = st.columns(2)
        with _col_y:
            st.number_input(
                "開始年",
                min_value=_current_year - 5,
                max_value=_current_year,
                value=_default_year,
                step=1,
                key="global_start_year",
            )
        with _col_m:
            st.number_input(
                "開始月",
                min_value=1,
                max_value=12,
                value=1,
                step=1,
                key="global_start_month",
            )
        st.caption(f"⚙️ 任意設定です。デフォルトは直近1年（{_default_year}年1月〜）")

        st.divider()

    # ====================================
    # メインエリア: 機能選択
    # ====================================
    st.subheader("📌 機能を選択")

    function_type = st.radio(
        "機能タイプ",
        [
            "📋 プレイヤーの最新動向",
            "📊 カテゴリチェック",
            "🏪 店舗・教室調査",
            "📋 3段階チェック",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    # ====================================
    # 機能分岐（各タブモジュールに委譲）
    # ====================================
    if "最新動向" in function_type:
        render_player_trend_tab(industry=industry, definition=definition)
    elif "カテゴリチェック" in function_type:
        render_investigation_tab(industry=industry, definition=definition)
    elif "店舗・教室調査" in function_type:
        render_store_tab()
    elif "3段階チェック" in function_type:
        render_workflow_tab(industry=industry, definition=definition)

    # デバッグログ表示
    render_debug_log()


if __name__ == "__main__":
    main()
