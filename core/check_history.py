#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
チェック履歴管理 + 差分計算
============================
3段階チェック体制（実査前/確定時/発表前）の履歴を管理し、
フェーズ間の差分を計算する。

【データ保存】
- JSONファイルベース（出力/history/ ディレクトリ）
- 各チェック記録はUUID付きで一意に管理
"""

import difflib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CheckRecord:
    """1回のチェック記録"""
    record_id: str = ""                     # UUID
    phase: str = ""                         # "pre_survey" / "ranking_confirmed" / "pre_release"
    industry: str = ""                      # 業界名
    executed_at: str = ""                   # ISO 8601 形式
    player_count: int = 0                   # チェック対象数
    results_file: str = ""                  # 結果ファイルパス
    summary: dict = field(default_factory=dict)  # {critical: 0, warning: 2, ...}

    def to_dict(self) -> dict:
        """辞書変換"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CheckRecord":
        """辞書から生成"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DiffItem:
    """差分の1項目"""
    player_name: str
    diff_type: str       # "new_alert" / "resolved" / "changed_attribute" / "new_player" / "removed_player"
    description: str     # 差分の説明
    old_value: str = ""  # 変更前の値
    new_value: str = ""  # 変更後の値


@dataclass
class DiffReport:
    """差分レポート"""
    old_phase: str = ""
    new_phase: str = ""
    old_record_id: str = ""
    new_record_id: str = ""
    computed_at: str = ""
    new_alerts: list = field(default_factory=list)          # 新たに発生したアラート
    resolved_alerts: list = field(default_factory=list)     # 解消されたアラート
    changed_attributes: list = field(default_factory=list)  # 属性マトリクスの変化
    new_players: list = field(default_factory=list)         # 前回にはなかったプレイヤー
    removed_players: list = field(default_factory=list)     # 前回にはあったが今回ないプレイヤー

    @property
    def total_changes(self) -> int:
        """総変更数"""
        return (
            len(self.new_alerts)
            + len(self.resolved_alerts)
            + len(self.changed_attributes)
            + len(self.new_players)
            + len(self.removed_players)
        )

    def to_dict(self) -> dict:
        """辞書変換"""
        return {
            "old_phase": self.old_phase,
            "new_phase": self.new_phase,
            "old_record_id": self.old_record_id,
            "new_record_id": self.new_record_id,
            "computed_at": self.computed_at,
            "total_changes": self.total_changes,
            "new_alerts": [asdict(item) if hasattr(item, '__dataclass_fields__') else item for item in self.new_alerts],
            "resolved_alerts": [asdict(item) if hasattr(item, '__dataclass_fields__') else item for item in self.resolved_alerts],
            "changed_attributes": [asdict(item) if hasattr(item, '__dataclass_fields__') else item for item in self.changed_attributes],
            "new_players": self.new_players,
            "removed_players": self.removed_players,
        }


def is_same_player(name_a: str, name_b: str, threshold: float = 0.8) -> bool:
    """
    名称の類似度で同一プレイヤーか判定

    Args:
        name_a: プレイヤー名A
        name_b: プレイヤー名B
        threshold: 類似度しきい値（デフォルト0.8）

    Returns:
        同一プレイヤーと判定された場合True

    Examples:
        >>> is_same_player("楽天カード", "楽天カード（株）")  # True
        >>> is_same_player("dアニメストア", "dアニメストア for Prime Video")  # False
    """
    if not name_a or not name_b:
        return False
    ratio = difflib.SequenceMatcher(None, name_a, name_b).ratio()
    return ratio >= threshold


class CheckHistory:
    """
    チェック履歴管理（JSONファイルベース）

    【保存先】
    出力/history/
    ├── index.json            # 全チェック記録のインデックス
    ├── {record_id}.json      # 個別結果ファイル
    └── ...
    """

    DEFAULT_HISTORY_DIR = Path("出力/history")

    def __init__(self, history_dir: Optional[Path] = None):
        """
        Args:
            history_dir: 履歴保存ディレクトリ（未指定時はデフォルト）
        """
        self.history_dir = history_dir or self.DEFAULT_HISTORY_DIR
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.history_dir / "index.json"

    def _load_index(self) -> list[dict]:
        """インデックスを読み込み"""
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_index(self, index: list[dict]) -> None:
        """インデックスを保存"""
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def save_record(
        self,
        record: CheckRecord,
        results: list,
    ) -> Path:
        """
        チェック記録を保存

        Args:
            record: チェック記録
            results: 結果リスト（to_dict() 可能なオブジェクト）

        Returns:
            保存されたファイルのパス
        """
        # record_id が未設定の場合、生成
        if not record.record_id:
            record.record_id = str(uuid.uuid4())[:8]

        if not record.executed_at:
            record.executed_at = datetime.now().isoformat()

        # 結果ファイルを保存
        results_filename = f"{record.record_id}.json"
        results_path = self.history_dir / results_filename
        record.results_file = results_filename

        results_data = []
        for r in results:
            if hasattr(r, "to_dict"):
                results_data.append(r.to_dict())
            elif isinstance(r, dict):
                results_data.append(r)

        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)

        # インデックスに追加
        index = self._load_index()
        index.append(record.to_dict())
        self._save_index(index)

        return results_path

    def load_latest(
        self,
        industry: str,
        phase: str,
    ) -> Optional[CheckRecord]:
        """
        指定業界・フェーズの最新チェック記録を取得

        Args:
            industry: 業界名
            phase: フェーズ名

        Returns:
            最新の CheckRecord、なければ None
        """
        index = self._load_index()

        # 条件に合致するレコードを逆順（新しい順）で探す
        matching = [
            r for r in index
            if r.get("industry") == industry and r.get("phase") == phase
        ]

        if not matching:
            return None

        # executed_at で最新のものを取得
        latest = max(matching, key=lambda r: r.get("executed_at", ""))
        return CheckRecord.from_dict(latest)

    def load_results(self, record: CheckRecord) -> list[dict]:
        """
        チェック記録の結果を読み込み

        Args:
            record: チェック記録

        Returns:
            結果リスト（dict の list）
        """
        results_path = self.history_dir / record.results_file
        if not results_path.exists():
            return []

        with open(results_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def compute_diff(
        self,
        old_results: list[dict],
        new_results: list[dict],
        old_phase: str = "",
        new_phase: str = "",
    ) -> DiffReport:
        """
        2回のチェック結果間の差分を計算

        Args:
            old_results: 前回の結果リスト
            new_results: 今回の結果リスト
            old_phase: 前回のフェーズ
            new_phase: 今回のフェーズ

        Returns:
            DiffReport
        """
        report = DiffReport(
            old_phase=old_phase,
            new_phase=new_phase,
            computed_at=datetime.now().isoformat(),
        )

        # プレイヤー名でマッピング
        old_by_name = {}
        for r in old_results:
            name = r.get("player_name_original") or r.get("player_name") or r.get("company_name", "")
            if name:
                old_by_name[name] = r

        new_by_name = {}
        for r in new_results:
            name = r.get("player_name_original") or r.get("player_name") or r.get("company_name", "")
            if name:
                new_by_name[name] = r

        old_names = set(old_by_name.keys())
        new_names = set(new_by_name.keys())

        # 新規プレイヤー（今回にはあるが前回にはない）
        for name in new_names:
            # 類似度チェック
            found_match = False
            for old_name in old_names:
                if is_same_player(name, old_name):
                    found_match = True
                    break
            if not found_match:
                report.new_players.append(name)

        # 削除プレイヤー（前回にはあるが今回にはない）
        for name in old_names:
            found_match = False
            for new_name in new_names:
                if is_same_player(name, new_name):
                    found_match = True
                    break
            if not found_match:
                report.removed_players.append(name)

        # 共通プレイヤーの差分チェック
        for name in new_names:
            # 前回の対応するレコードを探す
            old_record = None
            for old_name in old_names:
                if is_same_player(name, old_name):
                    old_record = old_by_name[old_name]
                    break

            if old_record is None:
                continue  # 新規プレイヤーなのでスキップ

            new_record = new_by_name[name]

            # アラートレベルの変化
            old_alert = old_record.get("alert_level", "")
            new_alert = new_record.get("alert_level", "")

            if old_alert != new_alert and old_alert and new_alert:
                item = DiffItem(
                    player_name=name,
                    diff_type="new_alert" if self._is_escalation(old_alert, new_alert) else "resolved",
                    description=f"アラートレベル変更: {old_alert} → {new_alert}",
                    old_value=old_alert,
                    new_value=new_alert,
                )
                if item.diff_type == "new_alert":
                    report.new_alerts.append(item)
                else:
                    report.resolved_alerts.append(item)

            # 属性マトリクスの変化
            old_attrs = old_record.get("attribute_matrix", {})
            new_attrs = new_record.get("attribute_matrix", {})

            if old_attrs and new_attrs:
                all_keys = set(old_attrs.keys()) | set(new_attrs.keys())
                for key in all_keys:
                    old_val = old_attrs.get(key)
                    new_val = new_attrs.get(key)
                    if old_val != new_val:
                        report.changed_attributes.append(DiffItem(
                            player_name=name,
                            diff_type="changed_attribute",
                            description=f"{key}: {self._format_attr(old_val)} → {self._format_attr(new_val)}",
                            old_value=str(old_val),
                            new_value=str(new_val),
                        ))

        return report

    def _is_escalation(self, old_alert: str, new_alert: str) -> bool:
        """アラートレベルがエスカレーションしたか判定"""
        levels = ["正常", "情報", "警告", "緊急"]
        old_idx = next((i for i, l in enumerate(levels) if l in old_alert), 0)
        new_idx = next((i for i, l in enumerate(levels) if l in new_alert), 0)
        return new_idx > old_idx

    def _format_attr(self, value) -> str:
        """属性値を表示形式に変換"""
        if value is True:
            return "○"
        elif value is False:
            return "×"
        else:
            return "?"

    def list_records(
        self,
        industry: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> list[CheckRecord]:
        """
        チェック記録の一覧を取得

        Args:
            industry: 業界名（フィルタ、Noneで全件）
            phase: フェーズ（フィルタ、Noneで全件）

        Returns:
            CheckRecord のリスト
        """
        index = self._load_index()

        records = []
        for r in index:
            if industry and r.get("industry") != industry:
                continue
            if phase and r.get("phase") != phase:
                continue
            records.append(CheckRecord.from_dict(r))

        return records
