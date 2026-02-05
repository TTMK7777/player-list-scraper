#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Excel Handler のテスト
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.excel_handler import ExcelHandler, PlayerData, ValidationReportExporter


class TestExcelHandler:
    """ExcelHandler のテストクラス"""

    def test_load_excel_success(self, temp_excel_file):
        """正常なExcelファイルの読み込み"""
        handler = ExcelHandler()
        players = handler.load(temp_excel_file)

        assert len(players) == 3
        assert players[0].player_name == "テストサービスA"
        assert players[0].company_name == "テスト株式会社A"
        assert players[0].official_url == "https://test-a.example.com/"

    def test_load_excel_detects_header_row(self, temp_excel_file):
        """ヘッダー行の自動検出"""
        handler = ExcelHandler()
        handler.load(temp_excel_file)

        # ヘッダー行が4行目であることを確認
        assert handler.header_row == 4

    def test_load_excel_detects_columns(self, temp_excel_file):
        """列の自動検出"""
        handler = ExcelHandler()
        handler.load(temp_excel_file)

        column_names = handler.get_column_names()
        assert "サービス名" in column_names
        assert "事業者名" in column_names
        assert "公式URL" in column_names

    def test_load_nonexistent_file(self):
        """存在しないファイルの読み込み"""
        handler = ExcelHandler()

        with pytest.raises(FileNotFoundError):
            handler.load("/nonexistent/path/file.xlsx")

    def test_player_data_with_empty_url(self, temp_excel_file):
        """URLが空のプレイヤーデータ"""
        handler = ExcelHandler()
        players = handler.load(temp_excel_file)

        # 3番目のデータはURLが空
        player_c = [p for p in players if p.player_name == "テストサービスC"][0]
        assert player_c.official_url == ""

    def test_player_data_row_index(self, temp_excel_file):
        """行インデックスが正しく保持されているか"""
        handler = ExcelHandler()
        players = handler.load(temp_excel_file)

        # データ行は5行目から開始
        assert players[0].row_index == 5
        assert players[1].row_index == 6
        assert players[2].row_index == 7


class TestValidationReportExporter:
    """ValidationReportExporter のテストクラス"""

    def test_export_creates_file(self, tmp_path):
        """エクスポートがファイルを作成するか"""
        from investigators.base import (
            AlertLevel, ChangeType, ValidationStatus, ValidationResult
        )
        from datetime import datetime

        results = [
            ValidationResult(
                player_name_original="テストサービス",
                player_name_current="テストサービス",
                status=ValidationStatus.UNCHANGED,
                alert_level=AlertLevel.OK,
                change_type=ChangeType.NO_CHANGE,
                url_original="https://example.com",
                url_current="https://example.com",
                confidence=0.95,
                checked_at=datetime.now(),
            )
        ]

        exporter = ValidationReportExporter()
        output_path = tmp_path / "test_report.xlsx"
        result_path = exporter.export(results, output_path)

        assert result_path.exists()

    def test_export_with_critical_alert(self, tmp_path):
        """緊急アラートのエクスポート"""
        from investigators.base import (
            AlertLevel, ChangeType, ValidationStatus, ValidationResult
        )
        from datetime import datetime

        results = [
            ValidationResult(
                player_name_original="撤退サービス",
                player_name_current="撤退サービス",
                status=ValidationStatus.CONFIRMED,
                alert_level=AlertLevel.CRITICAL,
                change_type=ChangeType.WITHDRAWAL,
                change_details=["2025年3月にサービス終了"],
                url_original="https://example.com",
                url_current="",
                confidence=0.9,
                needs_manual_review=False,
                checked_at=datetime.now(),
            )
        ]

        exporter = ValidationReportExporter()
        output_path = tmp_path / "test_critical_report.xlsx"
        result_path = exporter.export(results, output_path)

        assert result_path.exists()

        # ファイルを読み込んで内容を確認
        import openpyxl
        wb = openpyxl.load_workbook(result_path)
        ws = wb.active

        # 2行目（データ行）のアラートレベルを確認
        assert "緊急" in ws.cell(row=2, column=1).value
