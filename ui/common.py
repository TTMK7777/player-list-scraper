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

import pandas as pd
import streamlit as st


def display_progress_log(logs: list[str], container) -> None:
    """進捗ログを表示"""
    log_text = "\n".join(logs[-15:])
    container.markdown(
        f'<div class="progress-log">{log_text}</div>',
        unsafe_allow_html=True,
    )


def display_cost_warning(estimated_cost: float, batch_count: int, player_count: int) -> None:
    """コスト概算の警告を表示"""
    st.warning(
        f"推定コスト: 約${estimated_cost:.2f}（{player_count}件 × {batch_count}バッチ）\n\n"
        "初回は少数でテストすることを推奨します。"
    )


def display_verification_badge(status: str) -> str:
    """検証ステータスに応じたバッジHTMLを返す"""
    badges = {
        "verified": '<span style="background-color:#6BCB77;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">URL検証済み</span>',
        "url_error": '<span style="background-color:#FF6B6B;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">URL不明</span>',
        "unverified": '<span style="background-color:#FFD93D;color:#333;padding:2px 8px;border-radius:10px;font-size:12px;">未検証</span>',
    }
    return badges.get(status, badges["unverified"])


def export_to_excel_bytes(exporter, results, **kwargs) -> bytes:
    """Excelエクスポーターを使ってバイト列を生成"""
    buffer = io.BytesIO()
    temp_path = Path(tempfile.gettempdir()) / f"export_temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"

    exporter.export(results, temp_path)

    with open(temp_path, "rb") as f:
        buffer.write(f.read())

    temp_path.unlink(missing_ok=True)
    return buffer.getvalue()
