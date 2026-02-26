#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ロギング設定モジュール
======================
日次ローテーションで Logs/ に出力する。

【動作】
- app.log に INFO 以上を書き込み
- 0時にローテーション → app.log.YYYY-MM-DD の形式でバックアップ
- 30日分保持
- Logs/ が作成/書き込み不可の場合はコンソールのみ（Streamlit Cloud 等）

【使い方】
    from core.logger import setup_logging
    setup_logging()   # 起動時に1回だけ呼ぶ
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 重複設定を防ぐフラグ（モジュールが再インポートされても1回のみ実行）
_logging_configured = False


def setup_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> None:
    """
    ルートロガーにファイルハンドラ（日次ローテーション）を設定する。

    Args:
        log_dir: ログ出力ディレクトリ。None の場合は <プロジェクトルート>/Logs/ を使用。
        level:   ログレベル（デフォルト: INFO）
    """
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    if log_dir is None:
        # このファイル (core/logger.py) の 2 階層上 = プロジェクトルート
        log_dir = Path(__file__).parent.parent / "Logs"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── コンソールハンドラ（常に追加） ──────────────────────────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # ── ファイルハンドラ（Logs/ が使える場合のみ） ───────────────────
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",   # 日付変わりにローテーション
            interval=1,        # 1日ごと
            backupCount=30,    # 30日分保持
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)

        root_logger.info(
            "ロギング開始 — 出力先: %s (30日ローテーション)", log_file
        )

    except (OSError, PermissionError) as exc:
        # Streamlit Cloud など書き込み不可の環境ではコンソールのみで継続
        root_logger.warning(
            "ログファイル設定失敗。コンソールのみに出力します。理由: %s", exc
        )
