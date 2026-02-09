#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
属性調査エンジン (AttributeInvestigator) のテスト
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from investigators.attribute_investigator import AttributeInvestigator
from investigators.base import AttributeInvestigationResult
from core.attribute_presets import (
    ATTRIBUTE_PRESETS,
    get_preset,
    get_preset_names,
    get_preset_labels,
)
from core.excel_handler import AttributeInvestigationExporter


# ====================================
# フィクスチャ
# ====================================
@pytest.fixture
def sample_players():
    """テスト用プレイヤーデータ"""
    return [
        {"player_name": "Netflix", "official_url": "https://www.netflix.com/jp/"},
        {"player_name": "Hulu", "official_url": "https://www.hulu.jp/"},
        {"player_name": "ABEMAプレミアム", "official_url": "https://abema.tv/"},
    ]


@pytest.fixture
def sample_attributes():
    """テスト用属性リスト"""
    return ["邦画", "洋画", "アニメ", "バラエティ", "スポーツ試合・中継"]


@pytest.fixture
def mock_llm_client_attribute():
    """属性調査成功ケース用のモックLLMクライアント"""
    mock = MagicMock()
    mock.call.return_value = '''```json
{
    "results": [
        {
            "player_name": "Netflix",
            "attributes": {"邦画": true, "洋画": true, "アニメ": true, "バラエティ": false, "スポーツ試合・中継": false},
            "confidence": 0.9,
            "sources": ["https://www.netflix.com/jp/browse"]
        },
        {
            "player_name": "Hulu",
            "attributes": {"邦画": true, "洋画": true, "アニメ": true, "バラエティ": true, "スポーツ試合・中継": false},
            "confidence": 0.85,
            "sources": ["https://www.hulu.jp/"]
        },
        {
            "player_name": "ABEMAプレミアム",
            "attributes": {"邦画": false, "洋画": false, "アニメ": true, "バラエティ": true, "スポーツ試合・中継": true},
            "confidence": 0.8,
            "sources": ["https://abema.tv/"]
        }
    ]
}
```'''
    mock.extract_json.return_value = {
        "results": [
            {
                "player_name": "Netflix",
                "attributes": {"邦画": True, "洋画": True, "アニメ": True, "バラエティ": False, "スポーツ試合・中継": False},
                "confidence": 0.9,
                "sources": ["https://www.netflix.com/jp/browse"]
            },
            {
                "player_name": "Hulu",
                "attributes": {"邦画": True, "洋画": True, "アニメ": True, "バラエティ": True, "スポーツ試合・中継": False},
                "confidence": 0.85,
                "sources": ["https://www.hulu.jp/"]
            },
            {
                "player_name": "ABEMAプレミアム",
                "attributes": {"邦画": False, "洋画": False, "アニメ": True, "バラエティ": True, "スポーツ試合・中継": True},
                "confidence": 0.8,
                "sources": ["https://abema.tv/"]
            }
        ]
    }
    return mock


# ====================================
# AttributeInvestigationResult テスト
# ====================================
class TestAttributeInvestigationResult:
    """属性調査結果データクラスのテスト"""

    def test_create_success(self):
        """成功結果の生成"""
        result = AttributeInvestigationResult.create_success(
            player_name="Netflix",
            attribute_matrix={"邦画": True, "洋画": True, "アニメ": False},
            confidence=0.9,
            source_urls=["https://example.com"],
        )
        assert result.player_name == "Netflix"
        assert result.attribute_matrix["邦画"] is True
        assert result.attribute_matrix["アニメ"] is False
        assert result.confidence == 0.9
        assert not result.needs_verification

    def test_create_uncertain(self):
        """要確認結果の生成"""
        result = AttributeInvestigationResult.create_uncertain(
            player_name="不明サービス",
            reason="情報不足",
        )
        assert result.needs_verification is True
        assert result.confidence == 0.3
        assert result.attribute_matrix == {}

    def test_create_error(self):
        """エラー結果の生成"""
        result = AttributeInvestigationResult.create_error(
            player_name="Netflix",
            error_message="API timeout",
        )
        assert result.confidence == 0.0
        assert result.needs_verification is True
        assert "エラー" in result.raw_response

    def test_to_dict(self):
        """辞書変換"""
        result = AttributeInvestigationResult.create_success(
            player_name="Netflix",
            attribute_matrix={"邦画": True},
            confidence=0.9,
        )
        d = result.to_dict()
        assert d["player_name"] == "Netflix"
        assert d["attribute_matrix"] == {"邦画": True}
        assert d["confidence"] == 0.9


# ====================================
# バッチサイズ自動決定テスト
# ====================================
class TestBatchSizeDetermination:
    """バッチサイズ自動決定のテスト"""

    def test_small_attribute_count(self):
        """属性数7以下 → バッチサイズ10"""
        investigator = AttributeInvestigator()
        assert investigator._optimal_batch_size(7) == 10

    def test_medium_attribute_count(self):
        """属性数8-15 → バッチサイズ5"""
        investigator = AttributeInvestigator()
        assert investigator._optimal_batch_size(15) == 5

    def test_large_attribute_count(self):
        """属性数16以上 → バッチサイズ3"""
        investigator = AttributeInvestigator()
        assert investigator._optimal_batch_size(20) == 3


# ====================================
# コスト概算テスト
# ====================================
class TestCostEstimation:
    """コスト概算ロジックのテスト"""

    def test_estimate_small_batch(self):
        """少数バッチのコスト概算"""
        investigator = AttributeInvestigator()
        cost = investigator.estimate_cost(player_count=10, attribute_count=7)
        assert cost["batch_size"] == 10
        assert cost["batch_count"] == 1
        assert cost["estimated_cost"] == pytest.approx(0.03)

    def test_estimate_video_streaming(self):
        """動画配信 36件のコスト概算"""
        investigator = AttributeInvestigator()
        cost = investigator.estimate_cost(player_count=36, attribute_count=15)
        assert cost["batch_size"] == 5
        assert cost["batch_count"] == 8  # ceil(36/5)
        assert cost["estimated_cost"] == pytest.approx(0.24)

    def test_estimate_credit_card(self):
        """クレカ 539件のコスト概算"""
        investigator = AttributeInvestigator()
        cost = investigator.estimate_cost(player_count=539, attribute_count=7)
        assert cost["batch_size"] == 10
        assert cost["batch_count"] == 54  # ceil(539/10)
        assert cost["estimated_cost"] == pytest.approx(1.62)

    def test_estimate_with_custom_batch_size(self):
        """カスタムバッチサイズでのコスト概算"""
        investigator = AttributeInvestigator()
        cost = investigator.estimate_cost(player_count=100, attribute_count=7, batch_size=5)
        assert cost["batch_size"] == 5
        assert cost["batch_count"] == 20


# ====================================
# バッチプロンプト生成テスト
# ====================================
class TestBatchPromptGeneration:
    """バッチプロンプト生成のテスト"""

    def test_prompt_contains_player_names(self, sample_players, sample_attributes):
        """プロンプトにプレイヤー名が含まれること"""
        investigator = AttributeInvestigator()
        prompt = investigator._build_batch_prompt(
            sample_players, sample_attributes, "動画配信サービス"
        )
        assert "Netflix" in prompt
        assert "Hulu" in prompt
        assert "ABEMAプレミアム" in prompt

    def test_prompt_contains_attributes(self, sample_players, sample_attributes):
        """プロンプトに属性名が含まれること"""
        investigator = AttributeInvestigator()
        prompt = investigator._build_batch_prompt(
            sample_players, sample_attributes, "動画配信サービス"
        )
        for attr in sample_attributes:
            assert attr in prompt

    def test_prompt_contains_industry(self, sample_players, sample_attributes):
        """プロンプトに業界名が含まれること"""
        investigator = AttributeInvestigator()
        prompt = investigator._build_batch_prompt(
            sample_players, sample_attributes, "動画配信サービス"
        )
        assert "動画配信サービス" in prompt

    def test_prompt_contains_json_format(self, sample_players, sample_attributes):
        """プロンプトにJSON出力形式が含まれること"""
        investigator = AttributeInvestigator()
        prompt = investigator._build_batch_prompt(
            sample_players, sample_attributes, ""
        )
        assert "JSON" in prompt
        assert "results" in prompt


# ====================================
# レスポンス解析テスト
# ====================================
class TestBatchResponseParsing:
    """バッチレスポンス解析のテスト"""

    def test_parse_valid_response(
        self, mock_llm_client_attribute, sample_players, sample_attributes
    ):
        """正常なJSONレスポンスの解析"""
        investigator = AttributeInvestigator(llm_client=mock_llm_client_attribute)
        results = investigator._parse_batch_response(
            mock_llm_client_attribute.call.return_value,
            sample_players,
            sample_attributes,
        )
        assert len(results) == 3
        assert results[0].player_name == "Netflix"
        assert results[0].attribute_matrix["邦画"] is True
        assert results[0].attribute_matrix["バラエティ"] is False
        assert results[0].confidence == 0.9

    def test_parse_invalid_json(self, sample_players, sample_attributes):
        """JSON解析失敗時は全プレイヤーが要確認"""
        mock = MagicMock()
        mock.extract_json.return_value = None
        investigator = AttributeInvestigator(llm_client=mock)

        results = investigator._parse_batch_response(
            "これはJSONではありません",
            sample_players,
            sample_attributes,
        )
        assert len(results) == 3
        assert all(r.needs_verification for r in results)

    def test_parse_missing_player(self, sample_attributes):
        """レスポンスに含まれないプレイヤーは要確認"""
        mock = MagicMock()
        mock.extract_json.return_value = {
            "results": [
                {
                    "player_name": "Netflix",
                    "attributes": {"邦画": True, "洋画": True, "アニメ": True, "バラエティ": False, "スポーツ試合・中継": False},
                    "confidence": 0.9,
                    "sources": [],
                }
            ]
        }
        investigator = AttributeInvestigator(llm_client=mock)
        players = [
            {"player_name": "Netflix"},
            {"player_name": "存在しないサービス"},
        ]
        results = investigator._parse_batch_response("...", players, sample_attributes)
        assert len(results) == 2
        assert not results[0].needs_verification  # Netflix はOK
        assert results[1].needs_verification  # 存在しない → 要確認


# ====================================
# 属性マトリクス正規化テスト
# ====================================
class TestAttributeMatrixNormalization:
    """属性マトリクス正規化のテスト"""

    def test_normalize_true_false_null(self, sample_attributes):
        """true/false/null の正規化"""
        mock = MagicMock()
        mock.extract_json.return_value = {
            "results": [{
                "player_name": "TestService",
                "attributes": {
                    "邦画": True,
                    "洋画": False,
                    "アニメ": None,
                    "バラエティ": "yes",  # 文字列 → null (不正な値)
                    "スポーツ試合・中継": 1,  # 数値 → null (不正な値)
                },
                "confidence": 0.8,
                "sources": [],
            }]
        }
        investigator = AttributeInvestigator(llm_client=mock)
        results = investigator._parse_batch_response(
            "...",
            [{"player_name": "TestService"}],
            sample_attributes,
        )
        matrix = results[0].attribute_matrix
        assert matrix["邦画"] is True
        assert matrix["洋画"] is False
        assert matrix["アニメ"] is None
        assert matrix["バラエティ"] is None  # "yes" は不正 → None
        assert matrix["スポーツ試合・中継"] is None  # 1 は不正 → None


# ====================================
# バッチ調査テスト（非同期）
# ====================================
class TestInvestigateBatch:
    """バッチ調査の統合テスト"""

    @pytest.mark.asyncio
    async def test_investigate_batch_success(
        self, mock_llm_client_attribute, sample_players, sample_attributes
    ):
        """バッチ調査の正常完了"""
        investigator = AttributeInvestigator(
            llm_client=mock_llm_client_attribute,
        )
        results = await investigator.investigate_batch(
            sample_players,
            sample_attributes,
            industry="動画配信サービス",
            batch_size=5,  # 全3件なので1バッチ
        )
        assert len(results) == 3
        assert results[0].player_name == "Netflix"

    @pytest.mark.asyncio
    async def test_investigate_batch_with_progress(
        self, mock_llm_client_attribute, sample_players, sample_attributes
    ):
        """進捗コールバック呼び出し確認"""
        progress_calls = []

        def on_progress(current, total, name):
            progress_calls.append((current, total, name))

        investigator = AttributeInvestigator(
            llm_client=mock_llm_client_attribute,
        )
        await investigator.investigate_batch(
            sample_players,
            sample_attributes,
            batch_size=5,
            on_progress=on_progress,
        )
        assert len(progress_calls) >= 1

    @pytest.mark.asyncio
    async def test_investigate_batch_api_error(self, sample_players, sample_attributes):
        """API呼び出しエラー時のエラーハンドリング"""
        mock = MagicMock()
        mock.call.side_effect = RuntimeError("API timeout")

        investigator = AttributeInvestigator(llm_client=mock)
        results = await investigator.investigate_batch(
            sample_players,
            sample_attributes,
            batch_size=5,
        )
        assert len(results) == 3
        assert all(r.needs_verification for r in results)
        assert all(r.confidence == 0.0 for r in results)


# ====================================
# プリセットテスト
# ====================================
class TestAttributePresets:
    """属性プリセットのテスト"""

    def test_get_preset_names(self):
        """プリセット名一覧"""
        names = get_preset_names()
        assert "動画配信_ジャンル" in names
        assert "クレカ_ブランド" in names

    def test_get_preset_video(self):
        """動画配信プリセットの内容"""
        preset = get_preset("動画配信_ジャンル")
        assert "邦画" in preset["attributes"]
        assert "アニメ" in preset["attributes"]
        assert preset["batch_size"] == 5

    def test_get_preset_credit_card(self):
        """クレカプリセットの内容"""
        preset = get_preset("クレカ_ブランド")
        assert "VISA" in preset["attributes"]
        assert "JCB" in preset["attributes"]
        assert preset["batch_size"] == 10

    def test_get_preset_invalid(self):
        """存在しないプリセットでKeyError"""
        with pytest.raises(KeyError):
            get_preset("存在しない_プリセット")

    def test_get_preset_labels(self):
        """表示ラベル取得"""
        labels = get_preset_labels()
        assert "動画配信_ジャンル" in labels
        assert "カテゴリ" in labels["動画配信_ジャンル"]


# ====================================
# Excelエクスポートテスト
# ====================================
class TestAttributeInvestigationExporter:
    """属性調査Excel出力のテスト"""

    def test_export_creates_file(self, tmp_path, sample_attributes):
        """Excelファイルが作成されること"""
        results = [
            AttributeInvestigationResult.create_success(
                player_name="Netflix",
                attribute_matrix={a: True for a in sample_attributes},
                confidence=0.9,
                source_urls=["https://example.com"],
            ),
            AttributeInvestigationResult.create_success(
                player_name="Hulu",
                attribute_matrix={a: False for a in sample_attributes},
                confidence=0.8,
            ),
        ]

        output_path = tmp_path / "test_attribute_results.xlsx"
        exporter = AttributeInvestigationExporter(attributes=sample_attributes)
        result_path = exporter.export(results, output_path)

        assert result_path.exists()
        assert result_path.suffix == ".xlsx"

    def test_export_columns(self, sample_attributes):
        """出力列が正しいこと"""
        exporter = AttributeInvestigationExporter(attributes=sample_attributes)
        columns = exporter.get_columns()

        assert columns[0] == "プレイヤー名"
        for attr in sample_attributes:
            assert attr in columns
        assert "信頼度" in columns
        assert "ソースURL" in columns

    def test_export_with_mixed_values(self, tmp_path, sample_attributes):
        """○/×/?混在のエクスポート"""
        matrix = {}
        for i, attr in enumerate(sample_attributes):
            if i % 3 == 0:
                matrix[attr] = True
            elif i % 3 == 1:
                matrix[attr] = False
            else:
                matrix[attr] = None

        results = [
            AttributeInvestigationResult.create_success(
                player_name="テストサービス",
                attribute_matrix=matrix,
                confidence=0.7,
            ),
        ]

        output_path = tmp_path / "test_mixed.xlsx"
        exporter = AttributeInvestigationExporter(attributes=sample_attributes)
        result_path = exporter.export(results, output_path)
        assert result_path.exists()
