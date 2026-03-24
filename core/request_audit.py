#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""リクエスト監査ログ"""
import json
import logging
import logging.handlers
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_AUDIT_DIR = Path(__file__).resolve().parent.parent / "Logs"
_AUDIT_FILE = _AUDIT_DIR / "request_audit.jsonl"


class RequestAuditLogger:
    """JSONL形式でHTTPリクエストを監査記録する。"""

    def __init__(self):
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("request_audit")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.handlers.TimedRotatingFileHandler(
                str(_AUDIT_FILE), when="midnight", backupCount=30,
                encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def log_request(self, url: str, method: str, status_code: int,
                    elapsed_ms: float, user_agent: str) -> None:
        domain = urlparse(url).netloc
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "domain": domain,
            "method": method,
            "status_code": status_code,
            "elapsed_ms": round(elapsed_ms, 1),
            "user_agent": user_agent,
        }
        self._logger.info(json.dumps(entry, ensure_ascii=False))


# シングルトン
_audit_logger = RequestAuditLogger()


def log_request(url: str, method: str, status_code: int,
                elapsed_ms: float, user_agent: str) -> None:
    _audit_logger.log_request(url, method, status_code, elapsed_ms, user_agent)
