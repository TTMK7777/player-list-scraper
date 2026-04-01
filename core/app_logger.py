"""
Streamlit アプリ内デバッグログ表示
==================================
ログを deque バッファに書き込み、Streamlit UI の expander で表示可能にする。
不具合発生時にユーザーがログをコピーして開発者に送付できる。
"""

import logging
from collections import deque

import streamlit as st

MAX_LOG_LINES = 500  # バッファ上限（メモリ肥大化防止）


class StreamlitLogHandler(logging.Handler):
    """ログを deque バッファに書き込み、Streamlit UI で表示可能にする"""

    def __init__(self, buffer: deque):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(self.format(record))


def setup_app_logging() -> None:
    """session_state にログバッファを初期化し、ハンドラを登録"""
    if "log_buffer" not in st.session_state:
        st.session_state.log_buffer = deque(maxlen=MAX_LOG_LINES)

    buf = st.session_state.log_buffer
    root_logger = logging.getLogger()

    # 重複登録防止: 既存ハンドラがあればバッファ参照を更新
    for h in root_logger.handlers:
        if isinstance(h, StreamlitLogHandler):
            h.buffer = buf  # session_state のバッファに再接続
            return

    handler = StreamlitLogHandler(buf)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)


def get_log_text() -> str:
    """現在のログバッファ内容を返す（最新 MAX_LOG_LINES 行）"""
    buf = st.session_state.get("log_buffer")
    return "\n".join(buf) if buf else ""


def render_debug_log() -> None:
    """デバッグログ expander を表示する"""
    with st.expander("デバッグログ", expanded=False):
        st.caption(
            "不具合があった際は下記をコピペして開発者に送ってください"
        )
        st.code(get_log_text() or "(ログなし)", language="log")
