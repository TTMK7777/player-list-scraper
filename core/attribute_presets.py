#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
属性調査プリセット定義
======================
カテゴリ調査・ブランド調査の属性リストと推奨バッチサイズを定義。
"""

ATTRIBUTE_PRESETS = {
    "動画配信_ジャンル": {
        "label": "動画配信サービス カテゴリ調査",
        "description": "定額制動画配信サービスの各ジャンルの取り扱い有無を調査",
        "batch_size": 5,  # 推奨バッチサイズ（属性15項目 → 5社/バッチ）
        "attributes": [
            "邦画",
            "洋画",
            "国内ドラマ",
            "海外ドラマ",
            "韓国ドラマ",
            "アニメ",
            "バラエティ",
            "ドキュメンタリー",
            "音楽",
            "お笑い",
            "スポーツ試合・中継",
            "オリジナルコンテンツ",
            "ギャンブル動画",
            "アダルト動画",
            "演劇・ミュージカル",
        ],
    },
    "クレカ_ブランド": {
        "label": "クレジットカード ブランド調査",
        "description": "クレジットカードの取り扱い国際ブランドを調査",
        "batch_size": 10,  # 属性が少ないのでバッチ大きめ
        "attributes": [
            "VISA",
            "Mastercard",
            "JCB",
            "American Express",
            "Diners Club",
            "銀聯(UnionPay)",
            "Discover",
        ],
    },
}


def get_preset_names() -> list[str]:
    """利用可能なプリセット名の一覧を取得"""
    return list(ATTRIBUTE_PRESETS.keys())


def get_preset(name: str) -> dict:
    """指定されたプリセットを取得

    Args:
        name: プリセット名

    Returns:
        プリセット辞書

    Raises:
        KeyError: プリセットが見つからない場合
    """
    if name not in ATTRIBUTE_PRESETS:
        raise KeyError(f"プリセット '{name}' が見つかりません。利用可能: {get_preset_names()}")
    return ATTRIBUTE_PRESETS[name]


def get_preset_labels() -> dict[str, str]:
    """プリセット名 → 表示ラベルの辞書を取得"""
    return {name: preset["label"] for name, preset in ATTRIBUTE_PRESETS.items()}


def get_builtin_templates():
    """既存プリセットを InvestigationTemplate 形式で返す（後方互換ブリッジ）。

    Returns:
        list[InvestigationTemplate]: プリセットから変換されたテンプレートのリスト。
    """
    from core.investigation_templates import InvestigationTemplate

    templates = []
    for name, preset in ATTRIBUTE_PRESETS.items():
        templates.append(InvestigationTemplate(
            id=name,
            label=preset["label"],
            description=preset["description"],
            category="属性系",
            attributes=preset["attributes"],
            context="",
            batch_size=preset.get("batch_size"),
            is_builtin=True,
            created_at="2026-02-17T00:00:00",
            updated_at="2026-02-17T00:00:00",
        ))
    return templates
