#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3段階チェックワークフロー管理
==============================
実査前 → 確定時 → 発表前の3段階チェック体制を管理。

【3段階の内容】
| フェーズ | タイミング | 実行内容 |
|----------|----------|----------|
| 実査前(pre_survey) | 調査設計時 | 正誤チェック全件 + 新規参入検出 + 属性調査全件 |
| 確定時(ranking_confirmed) | 集計後 | 正誤チェック全件 + 属性調査（変化ありのみ再調査） |
| 発表前(pre_release) | 公開直前 | 正誤チェック（CRITICALのみ再検証） + 最終確認レポート |
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from core.check_history import CheckHistory, CheckRecord, DiffReport


class CheckPhase(Enum):
    """チェックフェーズ"""
    PRE_SURVEY = "pre_survey"                   # 実査前
    RANKING_CONFIRMED = "ranking_confirmed"     # 確定時
    PRE_RELEASE = "pre_release"                 # 発表前


# フェーズ表示ラベル
PHASE_LABELS = {
    CheckPhase.PRE_SURVEY: "実査前チェック",
    CheckPhase.RANKING_CONFIRMED: "確定時チェック",
    CheckPhase.PRE_RELEASE: "発表前チェック",
}

# フェーズの実行内容定義
PHASE_CONFIG = {
    CheckPhase.PRE_SURVEY: {
        "label": "実査前チェック",
        "description": "調査設計段階での包括的チェック",
        "validation_scope": "all",          # 正誤チェック: 全件
        "newcomer_detection": True,         # 新規参入検出: 実施
        "attribute_scope": "all",           # 属性調査: 全件
        "diff_base_phase": None,            # 差分基準: なし（ベースライン）
    },
    CheckPhase.RANKING_CONFIRMED: {
        "label": "確定時チェック",
        "description": "集計後の変動確認チェック",
        "validation_scope": "all",          # 正誤チェック: 全件
        "newcomer_detection": False,        # 新規参入検出: 不要
        "attribute_scope": "changed_only",  # 属性調査: 変化ありのみ再調査
        "diff_base_phase": CheckPhase.PRE_SURVEY,  # 差分基準: 実査前
    },
    CheckPhase.PRE_RELEASE: {
        "label": "発表前チェック",
        "description": "公開直前の最終確認",
        "validation_scope": "critical_only",  # 正誤チェック: CRITICALのみ
        "newcomer_detection": False,          # 新規参入検出: 不要
        "attribute_scope": "none",            # 属性調査: 不要
        "diff_base_phase": CheckPhase.RANKING_CONFIRMED,  # 差分基準: 確定時
    },
}


@dataclass
class WorkflowStatus:
    """ワークフロー全体のステータス"""
    industry: str
    phases: dict = field(default_factory=dict)  # {phase_name: CheckRecord or None}
    current_phase: Optional[str] = None
    diff_reports: dict = field(default_factory=dict)  # {phase_name: DiffReport}

    def get_completed_phases(self) -> list[str]:
        """完了済みフェーズのリスト"""
        return [phase for phase, record in self.phases.items() if record is not None]

    def get_next_phase(self) -> Optional[CheckPhase]:
        """次に実行すべきフェーズ"""
        phase_order = [CheckPhase.PRE_SURVEY, CheckPhase.RANKING_CONFIRMED, CheckPhase.PRE_RELEASE]
        for phase in phase_order:
            if phase.value not in self.phases or self.phases[phase.value] is None:
                return phase
        return None  # 全フェーズ完了


class CheckWorkflow:
    """
    3段階チェックワークフロー管理

    【使用方法】
    ```python
    workflow = CheckWorkflow()
    status = workflow.get_status("クレジットカード")
    config = workflow.get_phase_config(CheckPhase.PRE_SURVEY)
    ```
    """

    def __init__(self, history: Optional[CheckHistory] = None):
        """
        Args:
            history: CheckHistory インスタンス（未指定時は自動作成）
        """
        self.history = history or CheckHistory()

    def get_phase_config(self, phase: CheckPhase) -> dict:
        """
        フェーズの設定を取得

        Args:
            phase: チェックフェーズ

        Returns:
            フェーズ設定辞書
        """
        return PHASE_CONFIG[phase]

    def get_status(self, industry: str) -> WorkflowStatus:
        """
        指定業界のワークフロー状態を取得

        Args:
            industry: 業界名

        Returns:
            WorkflowStatus
        """
        status = WorkflowStatus(industry=industry)

        for phase in CheckPhase:
            record = self.history.load_latest(industry, phase.value)
            status.phases[phase.value] = record

        # 現在のフェーズを判定
        next_phase = status.get_next_phase()
        status.current_phase = next_phase.value if next_phase else "completed"

        return status

    def create_record(
        self,
        phase: CheckPhase,
        industry: str,
        player_count: int,
        summary: dict,
    ) -> CheckRecord:
        """
        新しいチェック記録を作成

        Args:
            phase: チェックフェーズ
            industry: 業界名
            player_count: チェック対象数
            summary: サマリー情報

        Returns:
            CheckRecord（save_record() で保存する前のオブジェクト）
        """
        return CheckRecord(
            phase=phase.value,
            industry=industry,
            executed_at=datetime.now().isoformat(),
            player_count=player_count,
            summary=summary,
        )

    def save_and_diff(
        self,
        record: CheckRecord,
        results: list,
    ) -> tuple[CheckRecord, Optional[DiffReport]]:
        """
        チェック記録を保存し、前回フェーズとの差分を計算

        Args:
            record: チェック記録
            results: 結果リスト

        Returns:
            (保存されたCheckRecord, DiffReport or None)
        """
        # 保存
        self.history.save_record(record, results)

        # 差分計算
        phase = CheckPhase(record.phase)
        config = PHASE_CONFIG[phase]
        diff_base_phase = config.get("diff_base_phase")

        diff_report = None
        if diff_base_phase:
            old_record = self.history.load_latest(record.industry, diff_base_phase.value)
            if old_record:
                old_results = self.history.load_results(old_record)
                new_results_dicts = [
                    r.to_dict() if hasattr(r, "to_dict") else r
                    for r in results
                ]
                diff_report = self.history.compute_diff(
                    old_results,
                    new_results_dicts,
                    old_phase=diff_base_phase.value,
                    new_phase=record.phase,
                )

        return record, diff_report

    def get_validation_players(
        self,
        phase: CheckPhase,
        all_players: list,
        industry: str,
    ) -> list:
        """
        フェーズに応じたチェック対象プレイヤーを絞り込み

        Args:
            phase: チェックフェーズ
            all_players: 全プレイヤーリスト
            industry: 業界名

        Returns:
            チェック対象のプレイヤーリスト
        """
        config = PHASE_CONFIG[phase]
        scope = config["validation_scope"]

        if scope == "all":
            return all_players

        elif scope == "critical_only":
            # 前回のCRITICALプレイヤーのみ
            diff_base = config.get("diff_base_phase")
            if diff_base:
                old_record = self.history.load_latest(industry, diff_base.value)
                if old_record:
                    old_results = self.history.load_results(old_record)
                    critical_names = set()
                    for r in old_results:
                        alert = r.get("alert_level", "")
                        if "緊急" in alert or "CRITICAL" in alert.upper():
                            name = r.get("player_name_original") or r.get("player_name", "")
                            critical_names.add(name)

                    if critical_names:
                        return [
                            p for p in all_players
                            if getattr(p, "player_name", p.get("player_name", "") if isinstance(p, dict) else "")
                            in critical_names
                        ]

            # CRITICALがない場合は全件
            return all_players

        return all_players
