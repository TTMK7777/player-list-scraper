#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
request_audit モジュールのテスト
"""

import json
import logging
import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_audit_logger(tmp_path, monkeypatch):
    """各テストで独立した監査ログディレクトリを使う。

    モジュールレベルのシングルトンを汚さないよう、
    テストごとにモジュール定数とロガーハンドラをリセットする。
    """
    audit_dir = tmp_path / "Logs"
    audit_file = audit_dir / "request_audit.jsonl"

    # モジュール定数をパッチ
    import core.request_audit as mod
    monkeypatch.setattr(mod, "_AUDIT_DIR", audit_dir)
    monkeypatch.setattr(mod, "_AUDIT_FILE", audit_file)

    # ロガーハンドラをリセット
    logger = logging.getLogger("request_audit")
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()

    # シングルトンを再生成
    new_logger_instance = mod.RequestAuditLogger()
    monkeypatch.setattr(mod, "_audit_logger", new_logger_instance)

    yield audit_dir, audit_file

    # クリーンアップ: ハンドラを閉じる
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()


class TestRequestAuditLogger:
    """RequestAuditLogger のテスト群。"""

    def test_log_creates_file(self, _isolate_audit_logger):
        """ログ出力後にファイルが作成される。"""
        audit_dir, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        log_request("https://example.com/page", "GET", 200, 123.4, "TestAgent/1.0")

        # ハンドラをフラッシュ
        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        assert audit_file.exists(), f"監査ログファイルが作成されていない: {audit_file}"

    def test_log_jsonl_format(self, _isolate_audit_logger):
        """出力がJSON解析可能である。"""
        _, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        log_request("https://example.com/api", "POST", 201, 50.0, "TestAgent/1.0")

        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        content = audit_file.read_text(encoding="utf-8").strip()
        assert content, "ログファイルが空"
        entry = json.loads(content)
        assert isinstance(entry, dict)

    def test_log_contains_required_fields(self, _isolate_audit_logger):
        """全フィールド (timestamp,url,domain,method,status_code,elapsed_ms,user_agent) が存在する。"""
        _, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        log_request("https://www.example.com/test", "GET", 200, 99.9, "UA/1.0")

        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        entry = json.loads(audit_file.read_text(encoding="utf-8").strip())
        required = {"timestamp", "url", "domain", "method", "status_code", "elapsed_ms", "user_agent"}
        assert required.issubset(entry.keys()), f"不足フィールド: {required - entry.keys()}"

    def test_log_domain_extraction(self, _isolate_audit_logger):
        """URLからドメインが正しく抽出される。"""
        _, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        log_request("https://shop.example.co.jp/stores/list", "GET", 200, 10.0, "UA/1.0")

        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        entry = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert entry["domain"] == "shop.example.co.jp"

    def test_log_multiple_entries(self, _isolate_audit_logger):
        """複数エントリが改行区切りで記録される。"""
        _, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        log_request("https://a.example.com/", "GET", 200, 10.0, "UA/1.0")
        log_request("https://b.example.com/", "POST", 201, 20.0, "UA/1.0")
        log_request("https://c.example.com/", "GET", 404, 30.0, "UA/1.0")

        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        lines = [l for l in audit_file.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
        assert len(lines) == 3, f"3件のエントリが期待されるが {len(lines)} 件"

        # 各行がJSONとしてパース可能
        for line in lines:
            json.loads(line)

    def test_module_level_function(self, _isolate_audit_logger):
        """log_request() モジュールレベル関数が動作する。"""
        _, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        # 例外を投げずに呼び出せることを確認
        log_request("https://example.com/", "GET", 200, 5.5, "ModuleTest/1.0")

        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        content = audit_file.read_text(encoding="utf-8").strip()
        entry = json.loads(content)
        assert entry["user_agent"] == "ModuleTest/1.0"

    def test_log_unicode_url(self, _isolate_audit_logger):
        """日本語URLが正しく記録される。"""
        _, audit_file = _isolate_audit_logger
        from core.request_audit import log_request

        unicode_url = "https://example.com/店舗/東京"
        log_request(unicode_url, "GET", 200, 15.0, "UA/1.0")

        logger = logging.getLogger("request_audit")
        for h in logger.handlers:
            h.flush()

        content = audit_file.read_text(encoding="utf-8").strip()
        entry = json.loads(content)
        assert entry["url"] == unicode_url
        # ensure_ascii=False でエンコードされているので日本語がそのまま残る
        assert "店舗" in content

    def test_log_directory_auto_create(self, tmp_path, monkeypatch):
        """Logsディレクトリが自動作成される。"""
        import core.request_audit as mod

        # まだ存在しない深いディレクトリ
        new_dir = tmp_path / "deep" / "nested" / "Logs"
        new_file = new_dir / "request_audit.jsonl"

        monkeypatch.setattr(mod, "_AUDIT_DIR", new_dir)
        monkeypatch.setattr(mod, "_AUDIT_FILE", new_file)

        # ロガーハンドラをリセット
        logger = logging.getLogger("request_audit")
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

        # 新インスタンス生成でディレクトリが作られる
        instance = mod.RequestAuditLogger()
        assert new_dir.exists(), f"ディレクトリが自動作成されていない: {new_dir}"

        # クリーンアップ
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
