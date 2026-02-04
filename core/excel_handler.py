#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Excel読み書きハンドラー
======================
プレイヤーリストExcelの読み込み・書き出しを担当

対応フォーマット:
- クレジットカード プレイヤーリスト
- 動画配信サービス プレイヤーリスト
- 中古車販売店 プレイヤーリスト
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


@dataclass
class PlayerData:
    """プレイヤーデータ"""
    row_index: int  # 元のExcel行番号
    player_name: str  # プレイヤー名（サービス名/企業名）
    official_url: str = ""  # 公式URL
    company_name: str = ""  # 運営会社名
    category: str = ""  # カテゴリ（業界固有）
    notes: str = ""  # 備考
    extra_data: dict = field(default_factory=dict)  # その他のカラムデータ


class ExcelHandler:
    """
    Excelファイルの読み書きを担当

    【対応列の自動検出】
    - プレイヤー名/サービス名/企業名 列を自動検出
    - URL/公式URL/公式サイト 列を自動検出
    - 運営会社/事業者 列を自動検出
    """

    # 列名の候補パターン（優先度順）
    PLAYER_NAME_PATTERNS = [
        r"^サービス名$", r"^プレイヤー名$", r"^ブランド名$", r"^企業名$", r"^会社名$",
        r"サービス名", r"プレイヤー名", r"ブランド名",
        r"player.*name", r"service.*name", r"brand",
    ]
    URL_PATTERNS = [
        r"^URL$", r"^公式URL$", r"^公式サイト$", r"^ホームページ$", r"^HP$",
        r"URL", r"公式URL", r"公式サイト", r"ホームページ", r"HP",
        r"official.*url", r"website", r"site",
    ]
    COMPANY_PATTERNS = [
        r"^事業者名$", r"^運営会社$", r"^運営元$",
        r"事業者名", r"事業者", r"運営会社", r"運営元",
        r"operator", r"company",
    ]

    # ヘッダー行検出用のキーワード（これらが含まれる行をヘッダーと判定）
    HEADER_KEYWORDS = [
        "サービス名", "プレイヤー名", "ブランド名", "企業名", "会社名",
        "事業者名", "調査票用No", "調査対象",
    ]

    def __init__(self):
        self.workbook = None
        self.sheet = None
        self.header_row = 1
        self.column_map: dict[str, int] = {}  # 列名 -> 列インデックス

    def load(self, file_path: str | Path) -> list[PlayerData]:
        """
        Excelファイルを読み込み、プレイヤーデータのリストを返す

        Args:
            file_path: Excelファイルパス

        Returns:
            list[PlayerData]: プレイヤーデータのリスト
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        self.workbook = openpyxl.load_workbook(file_path, data_only=True)
        self.sheet = self.workbook.active

        # ヘッダー行を探す
        self._find_header_row()

        # 列マッピングを作成
        self._create_column_map()

        # データを読み込み
        players = []
        for row_idx in range(self.header_row + 1, self.sheet.max_row + 1):
            player = self._read_row(row_idx)
            if player and player.player_name.strip():
                players.append(player)

        return players

    def _find_header_row(self) -> None:
        """ヘッダー行を探す（キーワードマッチングで検出）"""
        best_row = 1
        best_score = 0

        for row_idx in range(1, min(15, self.sheet.max_row + 1)):
            row_values = [
                str(cell.value or "").strip()
                for cell in self.sheet[row_idx]
            ]
            row_text = " ".join(row_values)

            # ヘッダーキーワードのマッチ数をスコアとする
            score = 0
            for keyword in self.HEADER_KEYWORDS:
                if keyword in row_text:
                    score += 1

            # より多くのキーワードがマッチする行をヘッダーとする
            if score > best_score:
                best_score = score
                best_row = row_idx

        self.header_row = best_row

    def _create_column_map(self) -> None:
        """列名とインデックスのマッピングを作成"""
        self.column_map = {}

        header_cells = list(self.sheet[self.header_row])
        for col_idx, cell in enumerate(header_cells, 1):
            col_name = str(cell.value or "").strip()
            if not col_name:
                continue

            # 列名をそのまま保存
            self.column_map[col_name] = col_idx

            # 特殊な列を検出
            for pattern in self.PLAYER_NAME_PATTERNS:
                if re.search(pattern, col_name, re.IGNORECASE):
                    self.column_map["_player_name"] = col_idx
                    break

            for pattern in self.URL_PATTERNS:
                if re.search(pattern, col_name, re.IGNORECASE):
                    self.column_map["_url"] = col_idx
                    break

            for pattern in self.COMPANY_PATTERNS:
                if re.search(pattern, col_name, re.IGNORECASE):
                    self.column_map["_company"] = col_idx
                    break

    def _read_row(self, row_idx: int) -> Optional[PlayerData]:
        """1行をPlayerDataに変換"""
        # プレイヤー名を取得
        player_name_col = self.column_map.get("_player_name", 1)
        player_name = str(self.sheet.cell(row_idx, player_name_col).value or "").strip()

        if not player_name:
            return None

        # URLを取得
        url_col = self.column_map.get("_url")
        official_url = ""
        if url_col:
            official_url = str(self.sheet.cell(row_idx, url_col).value or "").strip()

        # 運営会社を取得
        company_col = self.column_map.get("_company")
        company_name = ""
        if company_col:
            company_name = str(self.sheet.cell(row_idx, company_col).value or "").strip()

        # その他のデータを収集
        extra_data = {}
        for col_name, col_idx in self.column_map.items():
            if col_name.startswith("_"):
                continue
            value = self.sheet.cell(row_idx, col_idx).value
            if value is not None:
                extra_data[col_name] = str(value).strip()

        return PlayerData(
            row_index=row_idx,
            player_name=player_name,
            official_url=official_url,
            company_name=company_name,
            extra_data=extra_data,
        )

    def get_column_names(self) -> list[str]:
        """検出された列名のリストを返す"""
        return [k for k in self.column_map.keys() if not k.startswith("_")]


class ValidationReportExporter:
    """
    正誤チェック結果をExcelにエクスポート

    【出力形式】
    - アラートレベル別の色分け
    - 要確認行のハイライト
    """

    # アラートレベル別の色
    ALERT_COLORS = {
        "CRITICAL": "FF6B6B",   # 赤
        "WARNING": "FFD93D",    # 黄色
        "INFO": "6BCB77",       # 緑
        "OK": "FFFFFF",         # 白
        "UNCERTAIN": "FFA500",  # オレンジ
    }

    # ヘッダー列
    REPORT_COLUMNS = [
        "アラート",
        "プレイヤー名（元）",
        "プレイヤー名（現在）",
        "変更タイプ",
        "変更内容",
        "公式URL（元）",
        "公式URL（現在）",
        "運営会社（元）",
        "運営会社（現在）",
        "信頼度",
        "要確認フラグ",
        "関連ニュース",
        "情報ソース",
        "チェック日時",
    ]

    def __init__(self):
        self.workbook = openpyxl.Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "チェック結果"

    def export(
        self,
        results: list,  # list[ValidationResult]
        output_path: str | Path,
    ) -> Path:
        """
        チェック結果をExcelファイルに出力

        Args:
            results: ValidationResult のリスト
            output_path: 出力ファイルパス

        Returns:
            出力されたファイルのパス
        """
        output_path = Path(output_path)

        # ヘッダー行を作成
        self._write_header()

        # データ行を書き込み
        for row_idx, result in enumerate(results, start=2):
            self._write_row(row_idx, result)

        # 列幅を調整
        self._adjust_column_widths()

        # 保存
        self.workbook.save(output_path)
        return output_path

    def _write_header(self) -> None:
        """ヘッダー行を書き込み"""
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4A90D9", end_color="4A90D9", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for col_idx, col_name in enumerate(self.REPORT_COLUMNS, start=1):
            cell = self.sheet.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment

        # ヘッダー行を固定
        self.sheet.freeze_panes = "A2"

    def _write_row(self, row_idx: int, result) -> None:
        """1行を書き込み"""
        # アラートレベルに応じた色
        alert_level = result.alert_level.name if hasattr(result.alert_level, "name") else str(result.alert_level)
        fill_color = self.ALERT_COLORS.get(alert_level, "FFFFFF")
        row_fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

        # 要確認の場合はオレンジ背景
        if result.needs_manual_review:
            row_fill = PatternFill(start_color="FFA500", end_color="FFA500", fill_type="solid")

        # データを書き込み
        row_data = [
            result.alert_level.value if hasattr(result.alert_level, "value") else str(result.alert_level),
            result.player_name_original,
            result.player_name_current,
            result.change_type.value if hasattr(result.change_type, "value") else str(result.change_type),
            "\n".join(result.change_details) if result.change_details else "",
            result.url_original,
            result.url_current,
            getattr(result, "company_name_original", ""),
            getattr(result, "company_name_current", ""),
            f"{result.confidence * 100:.0f}%",
            "TRUE" if result.needs_manual_review else "FALSE",
            result.news_summary or "",
            "\n".join(result.source_urls) if result.source_urls else "",
            result.checked_at.strftime("%Y-%m-%d %H:%M:%S") if result.checked_at else "",
        ]

        for col_idx, value in enumerate(row_data, start=1):
            cell = self.sheet.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = row_fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    def _adjust_column_widths(self) -> None:
        """列幅を調整"""
        column_widths = [8, 20, 20, 15, 40, 30, 30, 20, 20, 10, 12, 40, 40, 20]
        for col_idx, width in enumerate(column_widths, start=1):
            col_letter = get_column_letter(col_idx)
            self.sheet.column_dimensions[col_letter].width = width
