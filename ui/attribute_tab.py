#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
汎用調査（テンプレートベース属性調査）UIタブ
=============================================
旧・属性調査タブを汎用調査に進化。
TemplateManager によるテンプレート管理UIを提供。
"""

import asyncio
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.async_helpers import run_async
from core.excel_handler import ExcelHandler, AttributeInvestigationExporter
from core.investigation_templates import (
    InvestigationTemplate,
    TemplateManager,
    VALID_CATEGORIES,
)
from core.llm_client import LLMClient
from core.sanitizer import sanitize_input
from investigators.attribute_investigator import AttributeInvestigator
from ui.common import display_cost_warning, export_to_excel_bytes


# ---------------------------------------------------------------------------
# カスタム選択肢の定数
# ---------------------------------------------------------------------------
_CUSTOM_OPTION = "__custom__"


def _build_template_options(
    templates: list[InvestigationTemplate],
) -> list[InvestigationTemplate | str]:
    """selectbox 用の選択肢リストを構築する。

    テンプレート一覧の末尾にカスタムオプションを追加。

    Args:
        templates: テンプレート一覧。

    Returns:
        テンプレートオブジェクト + カスタム文字列のリスト。
    """
    options: list[InvestigationTemplate | str] = list(templates)
    options.append(_CUSTOM_OPTION)
    return options


def _format_template_option(option: InvestigationTemplate | str) -> str:
    """selectbox の表示ラベルを生成する。

    Args:
        option: テンプレートまたはカスタム定数。

    Returns:
        表示用ラベル文字列。
    """
    if option == _CUSTOM_OPTION:
        return "カスタム（保存なしで調査）"
    # InvestigationTemplate オブジェクト
    return f"【{option.category}】{option.label}"


def _sanitize_template_id(text: str) -> str:
    """テンプレートIDに使用できる安全な文字列に変換する。

    Args:
        text: 入力テキスト。

    Returns:
        アンダースコア区切りのスラッグ文字列。
    """
    # 全角スペースを半角に統一し、記号を除去
    slug = re.sub(r"[^\w\u3000-\u9FFF\uF900-\uFAFF]", "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "custom_template"


# ---------------------------------------------------------------------------
# メインレンダー関数
# ---------------------------------------------------------------------------
def render_investigation_tab(provider: str, industry: str) -> None:
    """汎用調査タブのUIをレンダリング。

    テンプレート選択/管理 + プレイヤー入力 + 調査実行 + 結果表示の
    4セクション構成。

    Args:
        provider: 使用する LLM プロバイダー名。
        industry: 対象業界名。
    """
    st.subheader("📊 汎用調査")

    # ------------------------------------------------------------------
    # セクション1: テンプレート選択・管理
    # ------------------------------------------------------------------
    tm = TemplateManager()
    templates = tm.list_templates()

    options = _build_template_options(templates)

    selected = st.selectbox(
        "調査テンプレート",
        options,
        format_func=_format_template_option,
        key="inv_template_select",
    )

    # テンプレート情報 or カスタム入力
    attributes: list[str] = []
    batch_size: Optional[int] = None
    context: str = ""

    if selected != _CUSTOM_OPTION:
        # テンプレート詳細表示
        tpl: InvestigationTemplate = selected
        attributes = tpl.attributes
        batch_size = tpl.batch_size
        context = tpl.context

        st.info(
            f"属性数: {len(attributes)}項目 / "
            f"推奨バッチ: {batch_size or '自動'}社/回"
        )
        if tpl.description:
            st.caption(tpl.description)

        with st.expander("調査対象属性"):
            st.write(", ".join(attributes))

        if context:
            with st.expander("判定基準（context）"):
                st.write(context)
    else:
        # カスタム入力
        custom_input = st.text_area(
            "属性をカンマまたは改行区切りで入力",
            placeholder="例: 邦画, 洋画, アニメ, ドキュメンタリー",
            height=80,
            key="inv_custom_attrs",
        )
        attributes = tm.import_from_text(custom_input) if custom_input else []

        context = st.text_area(
            "判定基準（context）",
            placeholder="例: 各サービスが提供するコンテンツのジャンル別取り扱い有無を調査。",
            height=60,
            key="inv_custom_context",
        )

        if attributes:
            st.info(f"属性数: {len(attributes)}項目")

    # ------------------------------------------------------------------
    # テンプレート作成 expander
    # ------------------------------------------------------------------
    with st.expander("新しいテンプレートを作成"):
        new_label = st.text_input(
            "テンプレート名",
            placeholder="例: フィットネス 設備調査",
            key="inv_new_label",
        )
        new_category = st.selectbox(
            "カテゴリ",
            list(VALID_CATEGORIES),
            key="inv_new_category",
        )

        # 属性定義: 2タブ
        attr_tab1, attr_tab2 = st.tabs(
            ["テキスト入力", "Excelインポート"]
        )

        new_attrs_text: str = ""
        new_attrs_from_excel: list[str] = []

        with attr_tab1:
            new_attrs_text = st.text_area(
                "属性をカンマまたは改行区切りで入力",
                placeholder="属性A, 属性B, 属性C",
                height=100,
                key="inv_new_attrs_text",
            )

        with attr_tab2:
            excel_file = st.file_uploader(
                "Excelファイル（第1列を属性として読取）",
                type=["xlsx", "xls"],
                key="inv_new_attrs_excel",
            )
            if excel_file:
                try:
                    temp_dir = Path(tempfile.gettempdir()) / "template_import"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = temp_dir / excel_file.name
                    temp_path.write_bytes(excel_file.getvalue())
                    new_attrs_from_excel = tm.import_from_excel(temp_path)
                    st.success(f"{len(new_attrs_from_excel)}件の属性を読み込みました")
                    st.write(", ".join(new_attrs_from_excel))
                except Exception as e:
                    st.error(f"Excel読み込みエラー: {e}")

        new_context = st.text_area(
            "判定基準（context）",
            placeholder="LLMに渡す判定指針を記述",
            height=60,
            key="inv_new_context",
        )

        new_batch_size = st.number_input(
            "バッチサイズ（0 = 自動）",
            min_value=0,
            max_value=50,
            value=0,
            key="inv_new_batch_size",
        )

        if st.button("テンプレートを保存", key="inv_save_template"):
            # 属性はテキスト入力を優先、なければ Excel
            final_attrs = (
                tm.import_from_text(new_attrs_text) if new_attrs_text.strip()
                else new_attrs_from_excel
            )

            if not new_label:
                st.error("テンプレート名を入力してください。")
            elif not final_attrs:
                st.error("属性を1つ以上入力してください。")
            else:
                try:
                    new_id = _sanitize_template_id(new_label)
                    new_template = InvestigationTemplate(
                        id=new_id,
                        label=new_label,
                        description="",
                        category=new_category,
                        attributes=final_attrs,
                        context=new_context,
                        batch_size=new_batch_size if new_batch_size > 0 else None,
                        is_builtin=False,
                    )
                    saved_path = tm.save_template(new_template)
                    st.success(
                        f"テンプレート「{new_label}」を保存しました。"
                    )
                    st.rerun()
                except (ValueError, PermissionError) as e:
                    st.error(f"保存エラー: {e}")

    # ------------------------------------------------------------------
    # テンプレート削除（ユーザー作成テンプレートのみ）
    # ------------------------------------------------------------------
    user_templates = [t for t in templates if not t.is_builtin]
    if user_templates:
        with st.expander("テンプレートを削除"):
            del_target = st.selectbox(
                "削除するテンプレート",
                user_templates,
                format_func=lambda t: t.label,
                key="inv_delete_select",
            )
            if st.button("削除", key="inv_delete_button"):
                try:
                    tm.delete_template(del_target.id)
                    st.success(f"テンプレート「{del_target.label}」を削除しました。")
                    st.rerun()
                except (PermissionError, KeyError) as e:
                    st.error(f"削除エラー: {e}")

    st.divider()

    # ------------------------------------------------------------------
    # セクション2: プレイヤー情報入力
    # ------------------------------------------------------------------
    st.subheader("📂 プレイヤー情報入力")

    input_tab1, input_tab2 = st.tabs(["📤 Excelアップロード", "✏️ 直接入力"])

    with input_tab1:
        uploaded_file = st.file_uploader(
            "プレイヤーリストExcelをアップロード",
            type=["xlsx", "xls"],
            help="サービス名/プレイヤー名、公式URL を含むExcelファイル",
            key="attr_excel_upload",
        )

        if uploaded_file:
            try:
                temp_dir = Path(tempfile.gettempdir()) / "attribute_investigator"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = temp_dir / uploaded_file.name
                temp_path.write_bytes(uploaded_file.getvalue())

                handler = ExcelHandler()
                players_data = handler.load(temp_path)

                players = [
                    {
                        "player_name": p.player_name,
                        "official_url": p.official_url,
                    }
                    for p in players_data
                ]

                st.session_state.attr_players = players
                st.success(f"{len(players)}件のプレイヤーを読み込みました")

            except Exception as e:
                st.error(f"Excelの読み込みに失敗: {e}")
                st.session_state.attr_players = []

    with input_tab2:
        input_text = st.text_area(
            "サービス名,公式URL の形式で入力（1行1サービス）",
            placeholder="Netflix,https://www.netflix.com/jp/\nHulu,https://www.hulu.jp/",
            height=120,
            key="attr_direct_input",
        )

        if st.button("入力内容を反映", key="attr_apply_input"):
            players = []
            for line in input_text.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(",")
                player_name = sanitize_input(parts[0].strip())
                official_url = parts[1].strip() if len(parts) > 1 else ""
                players.append({
                    "player_name": player_name,
                    "official_url": official_url,
                })

            if players:
                st.session_state.attr_players = players
                st.success(f"{len(players)}件のプレイヤーを登録しました")

    st.divider()

    # ------------------------------------------------------------------
    # セッション状態初期化
    # ------------------------------------------------------------------
    if "attr_players" not in st.session_state:
        st.session_state.attr_players = []
    if "attr_results" not in st.session_state:
        st.session_state.attr_results = []

    # ------------------------------------------------------------------
    # セクション3: コスト概算 & 調査実行
    # ------------------------------------------------------------------
    players = st.session_state.attr_players

    if players and attributes:
        investigator = AttributeInvestigator()
        cost_info = investigator.estimate_cost(
            player_count=len(players),
            attribute_count=len(attributes),
            batch_size=batch_size,
        )

        display_cost_warning(
            cost_info["estimated_cost"],
            cost_info["batch_count"],
            len(players),
        )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        check_limit = st.number_input(
            "調査件数",
            min_value=1,
            max_value=len(players) if players else 100,
            value=min(10, len(players)) if players else 10,
            help="初回は少数でテスト推奨",
            key="attr_check_limit",
        )

    with col2:
        # バッチサイズ上書きオプション
        default_batch = batch_size if batch_size and batch_size > 0 else 0
        batch_override = st.number_input(
            "バッチサイズ（0 = 自動）",
            min_value=0,
            max_value=50,
            value=default_batch,
            help="テンプレートの推奨値を上書きできます",
            key="inv_batch_override",
        )
        effective_batch: Optional[int] = batch_override if batch_override > 0 else batch_size

    with col3:
        run_button = st.button(
            "調査開始",
            type="primary",
            disabled=not players or not attributes or st.session_state.get("is_running", False),
            use_container_width=True,
            key="attr_run_button",
        )

    st.divider()

    if run_button:
        st.session_state.is_running = True
        progress_container = st.empty()
        status_container = st.empty()

        players_to_check = players[:check_limit]

        logs: list[str] = []

        def on_progress(current: int, total: int, name: str) -> None:
            log_msg = f"[{current}/{total}] 調査中: {name}"
            logs.append(log_msg)
            log_text = "\n".join(logs[-15:])
            progress_container.markdown(
                f'<div class="progress-log">{log_text}</div>',
                unsafe_allow_html=True,
            )

        status_container.info(f"{len(players_to_check)}件のプレイヤーを調査中...")

        try:
            llm = LLMClient(provider=provider)
            inv = AttributeInvestigator(llm_client=llm)

            results = run_async(inv.investigate_batch(
                players_to_check,
                attributes,
                industry=industry,
                batch_size=effective_batch,
                on_progress=on_progress,
                context=context,
            ))

            st.session_state.attr_results = results
            status_container.success(f"調査完了: {len(results)}件")

        except Exception as e:
            status_container.error(f"エラー: {type(e).__name__}: {str(e)}")
            st.session_state.attr_results = []

        st.session_state.is_running = False

    # ------------------------------------------------------------------
    # セクション4: 結果表示 + エクスポート
    # ------------------------------------------------------------------
    if st.session_state.attr_results:
        results = st.session_state.attr_results

        # マトリクステーブル表示
        st.subheader("結果: 属性マトリクス")

        matrix_data = []
        for r in results:
            row = {"プレイヤー名": r.player_name}
            for attr in attributes:
                val = (r.attribute_matrix or {}).get(attr)
                if val is True:
                    row[attr] = "○"
                elif val is False:
                    row[attr] = "×"
                else:
                    row[attr] = "?"
            row["信頼度"] = f"{r.confidence * 100:.0f}%"
            row["要確認"] = "!" if r.needs_verification else ""
            matrix_data.append(row)

        df = pd.DataFrame(matrix_data)
        st.dataframe(df, use_container_width=True, height=400)

        st.divider()

        # エクスポート
        st.subheader("結果エクスポート")

        col1, col2 = st.columns(2)

        with col1:
            exporter = AttributeInvestigationExporter(attributes=attributes)
            excel_data = export_to_excel_bytes(exporter, results)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "Excel ダウンロード（調査結果）",
                excel_data,
                f"investigation_{timestamp}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="inv_excel_download",
            )

        with col2:
            csv_data = []
            for r in results:
                csv_data.append(r.to_dict())
            df_csv = pd.DataFrame(csv_data)
            csv_bytes = df_csv.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                "CSV ダウンロード",
                csv_bytes,
                f"investigation_{timestamp}.csv",
                "text/csv",
                use_container_width=True,
                key="inv_csv_download",
            )


# ---------------------------------------------------------------------------
# 後方互換ラッパー
# ---------------------------------------------------------------------------
def render_attribute_tab(provider: str, industry: str) -> None:
    """後方互換ラッパー。render_investigation_tab を呼び出す。

    Args:
        provider: LLM プロバイダー名。
        industry: 対象業界名。
    """
    render_investigation_tab(provider=provider, industry=industry)
