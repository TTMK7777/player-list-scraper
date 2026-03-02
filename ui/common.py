#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
共通UIコンポーネント
====================
進捗表示、エクスポート、コスト表示等の共通部品。
"""

import io
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.excel_handler import ExcelHandler

# USD → JPY 換算レート（固定）
USD_TO_JPY = 150


def display_progress_log(logs: list[str], container) -> None:
    """進捗ログを表示"""
    log_text = "\n".join(logs[-15:])
    container.markdown(
        f'<div class="progress-log">{log_text}</div>',
        unsafe_allow_html=True,
    )


def display_cost_warning(estimated_cost: float, batch_count: int, player_count: int) -> None:
    """コスト概算の警告を表示（attribute_tab 用の既存関数）

    Args:
        estimated_cost: 推定コスト（USD）。
        batch_count: バッチ数。
        player_count: プレイヤー数。
    """
    estimated_cost_jpy = estimated_cost * USD_TO_JPY
    st.warning(
        f"推定コスト: 約{estimated_cost_jpy:.1f}円（{player_count}件 × {batch_count}バッチ）\n\n"
        "初回は少数でテストすることを推奨します。"
    )


def display_cost_estimate(
    call_count: int,
    cost_per_call: float,
    label: str = "API呼び出し",
) -> None:
    """汎用コスト概算を表示

    Args:
        call_count: API呼び出し回数
        cost_per_call: 1回あたりのコスト（USD）
        label: 表示ラベル
    """
    estimated_cost_usd = call_count * cost_per_call
    estimated_cost_jpy = estimated_cost_usd * USD_TO_JPY
    cost_per_call_jpy = cost_per_call * USD_TO_JPY
    st.info(
        f"推定コスト: 約{estimated_cost_jpy:.1f}円"
        f"（{call_count}回 × {cost_per_call_jpy:.2f}円/{label}）"
    )


def display_verification_badge(status: str) -> str:
    """検証ステータスに応じたバッジHTMLを返す"""
    badges = {
        "verified": '<span style="background-color:#6BCB77;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">URL検証済み</span>',
        "url_error": '<span style="background-color:#FF6B6B;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">URL不明</span>',
        "unverified": '<span style="background-color:#FFD93D;color:#333;padding:2px 8px;border-radius:10px;font-size:12px;">未検証</span>',
    }
    return badges.get(status, badges["unverified"])


def display_filter_multiselect(
    label: str,
    options: list[str],
    default: list[str] | None = None,
    key: str | None = None,
) -> list[str]:
    """フィルター用のmultiselectを表示し、選択された値を返す。

    Args:
        label: ラベル文字列。
        options: 選択肢のリスト。
        default: デフォルト選択値。Noneの場合は全選択。
        key: Streamlit widget key。

    Returns:
        選択された値のリスト。
    """
    if default is None:
        default = options
    return st.multiselect(
        label,
        options=options,
        default=default,
        key=key,
    )


def select_sheet_if_multiple(file_path, key_prefix: str) -> Optional[list[str]]:
    """複数シートがある場合にmultiselectを表示、単一シートならNoneを返す

    Args:
        file_path: Excelファイルパス
        key_prefix: Streamlit widget key のプレフィックス

    Returns:
        選択されたシート名のリスト、または単一シートの場合は None
    """
    sheet_names = ExcelHandler.get_sheet_names(file_path)
    if len(sheet_names) > 1:
        selected = st.multiselect(
            "読み込むシートを選択（複数選択可）",
            sheet_names,
            default=[sheet_names[0]],
            key=f"{key_prefix}_sheet_select",
        )
        return selected if selected else None
    return None


def number_input_with_max(
    label: str,
    max_value: int,
    default_value: int = 10,
    key: str = "",
    help: str = "APIコスト削減のため、最初は少数でテストしてください",
) -> int:
    """「全件」ボタン付き number_input

    2カラムレイアウト: [number_input | 全件ボタン]
    全件クリック時は session_state[key] を max_value に設定してリランする。

    Args:
        label: 入力ラベル
        max_value: 最大値（全件ボタンで設定される値）
        default_value: 初期デフォルト値
        key: Streamlit widget の session state key
        help: ヘルプテキスト

    Returns:
        現在の値
    """
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        value = st.number_input(
            label,
            min_value=1,
            max_value=max(1, max_value),
            value=min(default_value, max(1, max_value)),
            key=key,
            help=help,
        )
    with col_btn:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        if st.button("全件", key=f"{key}_max_btn", use_container_width=True):
            st.session_state[key] = max_value
            st.rerun()

    return value


def export_to_excel_bytes(exporter, results, **kwargs) -> bytes:
    """Excelエクスポーターを使ってバイト列を生成"""
    buffer = io.BytesIO()
    temp_path = Path(tempfile.gettempdir()) / f"export_temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"

    exporter.export(results, temp_path)

    with open(temp_path, "rb") as f:
        buffer.write(f.read())

    temp_path.unlink(missing_ok=True)
    return buffer.getvalue()
