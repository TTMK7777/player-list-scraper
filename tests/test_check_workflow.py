#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3段階チェックワークフロー (CheckWorkflow) のテスト
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.check_workflow import (
    CheckWorkflow,
    CheckPhase,
    PHASE_CONFIG,
    PHASE_LABELS,
    WorkflowStatus,
)
from core.check_history import CheckHistory, CheckRecord


# ====================================
# CheckPhase テスト
# ====================================
class TestCheckPhase:
    """チェックフェーズ列挙型のテスト"""

    def test_phase_values(self):
        """フェーズ値"""
        assert CheckPhase.PRE_SURVEY.value == "pre_survey"
        assert CheckPhase.RANKING_CONFIRMED.value == "ranking_confirmed"
        assert CheckPhase.PRE_RELEASE.value == "pre_release"

    def test_phase_labels(self):
        """表示ラベル"""
        assert PHASE_LABELS[CheckPhase.PRE_SURVEY] == "実査前チェック"
        assert PHASE_LABELS[CheckPhase.RANKING_CONFIRMED] == "確定時チェック"
        assert PHASE_LABELS[CheckPhase.PRE_RELEASE] == "発表前チェック"


# ====================================
# PHASE_CONFIG テスト
# ====================================
class TestPhaseConfig:
    """フェーズ設定のテスト"""

    def test_pre_survey_config(self):
        """実査前フェーズの設定"""
        config = PHASE_CONFIG[CheckPhase.PRE_SURVEY]
        assert config["validation_scope"] == "all"
        assert config["newcomer_detection"] is True
        assert config["attribute_scope"] == "all"
        assert config["diff_base_phase"] is None

    def test_ranking_confirmed_config(self):
        """確定時フェーズの設定"""
        config = PHASE_CONFIG[CheckPhase.RANKING_CONFIRMED]
        assert config["validation_scope"] == "all"
        assert config["newcomer_detection"] is False
        assert config["attribute_scope"] == "changed_only"
        assert config["diff_base_phase"] == CheckPhase.PRE_SURVEY

    def test_pre_release_config(self):
        """発表前フェーズの設定"""
        config = PHASE_CONFIG[CheckPhase.PRE_RELEASE]
        assert config["validation_scope"] == "critical_only"
        assert config["newcomer_detection"] is False
        assert config["attribute_scope"] == "none"
        assert config["diff_base_phase"] == CheckPhase.RANKING_CONFIRMED


# ====================================
# WorkflowStatus テスト
# ====================================
class TestWorkflowStatus:
    """ワークフローステータスのテスト"""

    def test_get_completed_phases_empty(self):
        """完了フェーズなし"""
        status = WorkflowStatus(industry="テスト")
        assert status.get_completed_phases() == []

    def test_get_completed_phases_partial(self):
        """一部完了"""
        status = WorkflowStatus(
            industry="テスト",
            phases={
                "pre_survey": CheckRecord(record_id="a", phase="pre_survey"),
                "ranking_confirmed": None,
                "pre_release": None,
            },
        )
        assert "pre_survey" in status.get_completed_phases()
        assert len(status.get_completed_phases()) == 1

    def test_get_next_phase_initial(self):
        """初期状態 → pre_survey"""
        status = WorkflowStatus(industry="テスト")
        assert status.get_next_phase() == CheckPhase.PRE_SURVEY

    def test_get_next_phase_after_first(self):
        """実査前完了後 → ranking_confirmed"""
        status = WorkflowStatus(
            industry="テスト",
            phases={
                "pre_survey": CheckRecord(record_id="a"),
            },
        )
        assert status.get_next_phase() == CheckPhase.RANKING_CONFIRMED

    def test_get_next_phase_all_done(self):
        """全完了 → None"""
        status = WorkflowStatus(
            industry="テスト",
            phases={
                "pre_survey": CheckRecord(record_id="a"),
                "ranking_confirmed": CheckRecord(record_id="b"),
                "pre_release": CheckRecord(record_id="c"),
            },
        )
        assert status.get_next_phase() is None


# ====================================
# CheckWorkflow テスト
# ====================================
class TestCheckWorkflow:
    """CheckWorkflow のテスト"""

    def test_get_phase_config(self):
        """フェーズ設定取得"""
        workflow = CheckWorkflow()
        config = workflow.get_phase_config(CheckPhase.PRE_SURVEY)
        assert "validation_scope" in config
        assert config["newcomer_detection"] is True

    def test_get_status_empty(self, tmp_path):
        """履歴なしのステータス取得"""
        history = CheckHistory(history_dir=tmp_path / "history")
        workflow = CheckWorkflow(history=history)

        status = workflow.get_status("クレジットカード")
        assert status.industry == "クレジットカード"
        assert status.current_phase == "pre_survey"

    def test_get_status_with_records(self, tmp_path):
        """履歴ありのステータス取得"""
        history = CheckHistory(history_dir=tmp_path / "history")
        workflow = CheckWorkflow(history=history)

        # 実査前の記録を保存
        record = CheckRecord(
            phase="pre_survey",
            industry="クレジットカード",
            player_count=10,
        )
        history.save_record(record, [{"player_name": "テスト"}])

        status = workflow.get_status("クレジットカード")
        assert status.current_phase == "ranking_confirmed"

    def test_create_record(self):
        """チェック記録の作成"""
        workflow = CheckWorkflow()
        record = workflow.create_record(
            phase=CheckPhase.PRE_SURVEY,
            industry="動画配信",
            player_count=36,
            summary={"critical": 0, "warning": 3},
        )
        assert record.phase == "pre_survey"
        assert record.industry == "動画配信"
        assert record.player_count == 36

    def test_save_and_diff_no_base(self, tmp_path):
        """差分基準なし（実査前）"""
        history = CheckHistory(history_dir=tmp_path / "history")
        workflow = CheckWorkflow(history=history)

        record = workflow.create_record(
            phase=CheckPhase.PRE_SURVEY,
            industry="テスト",
            player_count=5,
            summary={},
        )
        results = [{"player_name": "サービスA", "alert_level": "正常"}]

        saved_record, diff = workflow.save_and_diff(record, results)
        assert saved_record.record_id != ""
        assert diff is None  # 実査前は差分基準なし

    def test_save_and_diff_with_base(self, tmp_path):
        """差分基準あり（確定時 vs 実査前）"""
        history = CheckHistory(history_dir=tmp_path / "history")
        workflow = CheckWorkflow(history=history)

        # Step 1: 実査前を保存
        pre_record = workflow.create_record(
            phase=CheckPhase.PRE_SURVEY,
            industry="テスト",
            player_count=2,
            summary={},
        )
        pre_results = [
            {"player_name": "サービスA", "alert_level": "✅ 正常"},
            {"player_name": "サービスB", "alert_level": "✅ 正常"},
        ]
        workflow.save_and_diff(pre_record, pre_results)

        # Step 2: 確定時を保存（サービスAに警告発生）
        conf_record = workflow.create_record(
            phase=CheckPhase.RANKING_CONFIRMED,
            industry="テスト",
            player_count=2,
            summary={},
        )
        conf_results = [
            {"player_name": "サービスA", "alert_level": "🟡 警告"},
            {"player_name": "サービスB", "alert_level": "✅ 正常"},
        ]
        saved, diff = workflow.save_and_diff(conf_record, conf_results)

        assert diff is not None
        assert diff.total_changes >= 1

    def test_get_validation_players_all(self, tmp_path):
        """全件スコープ"""
        history = CheckHistory(history_dir=tmp_path / "history")
        workflow = CheckWorkflow(history=history)

        players = [{"player_name": "A"}, {"player_name": "B"}]
        result = workflow.get_validation_players(
            CheckPhase.PRE_SURVEY, players, "テスト"
        )
        assert len(result) == 2

    def test_get_validation_players_critical_only_no_history(self, tmp_path):
        """CRITICALのみスコープ（履歴なし→全件フォールバック）"""
        history = CheckHistory(history_dir=tmp_path / "history")
        workflow = CheckWorkflow(history=history)

        players = [{"player_name": "A"}, {"player_name": "B"}]
        result = workflow.get_validation_players(
            CheckPhase.PRE_RELEASE, players, "テスト"
        )
        assert len(result) == 2  # 履歴なし → 全件
