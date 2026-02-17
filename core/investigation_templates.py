#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
調査テンプレート管理
====================
属性調査のテンプレートを管理するモジュール。
組み込み（builtin）テンプレートとユーザー定義テンプレートをJSON形式で永続化。

【使用方法】
```python
from core.investigation_templates import TemplateManager

manager = TemplateManager()
templates = manager.list_templates(category="属性系")
template = manager.get_template("動画配信_ジャンル")
```
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# プロジェクトルートとテンプレートディレクトリの絶対パス解決
PROJECT_ROOT = Path(__file__).parent.parent
BUILTIN_DIR = PROJECT_ROOT / "templates" / "builtin"
USER_DIR = PROJECT_ROOT / "templates" / "user"

# 有効なカテゴリ
VALID_CATEGORIES = ("属性系", "地理系", "分類系", "カスタム")


@dataclass
class InvestigationTemplate:
    """調査テンプレートのデータクラス。

    Attributes:
        id: スラッグ (例: "動画配信_ジャンル")
        label: 表示名
        description: 説明
        category: カテゴリ ("属性系" | "地理系" | "分類系" | "カスタム")
        attributes: 調査属性リスト
        context: 判定基準の説明 (LLMプロンプトに挿入)
        batch_size: バッチサイズ上書き (None=自動)
        is_builtin: 組み込みフラグ
        created_at: ISO datetime 文字列
        updated_at: ISO datetime 文字列
    """

    id: str
    label: str
    description: str = ""
    category: str = ""
    attributes: list[str] = field(default_factory=list)
    context: str = ""
    batch_size: Optional[int] = None
    is_builtin: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        """バリデーション。"""
        if not self.id:
            raise ValueError("テンプレートIDは必須です")
        if not self.label:
            raise ValueError("テンプレートラベルは必須です")
        if self.category not in VALID_CATEGORIES:
            raise ValueError(
                f"無効なカテゴリ: '{self.category}' "
                f"(有効: {', '.join(VALID_CATEGORIES)})"
            )
        if not self.attributes:
            raise ValueError("属性リストは1つ以上必要です")

    def to_dict(self) -> dict:
        """テンプレートを辞書に変換する。

        Returns:
            JSON シリアライズ可能な辞書。
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "InvestigationTemplate":
        """辞書からテンプレートを生成する。

        Args:
            data: テンプレートデータの辞書。

        Returns:
            InvestigationTemplate インスタンス。

        Raises:
            ValueError: 必須フィールドが不足している場合。
        """
        required_fields = ("id", "label", "category", "attributes")
        for f in required_fields:
            if f not in data:
                raise ValueError(f"必須フィールド '{f}' がありません")

        return cls(
            id=data["id"],
            label=data["label"],
            description=data.get("description", ""),
            category=data["category"],
            attributes=data["attributes"],
            context=data.get("context", ""),
            batch_size=data.get("batch_size"),
            is_builtin=data.get("is_builtin", False),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


class TemplateManager:
    """テンプレートの CRUD 操作を提供するマネージャークラス。

    builtin ディレクトリと user ディレクトリの両方からテンプレートを読み込み、
    ユーザーテンプレートの保存・削除を行う。

    Attributes:
        builtin_dir: 組み込みテンプレートディレクトリ。
        user_dir: ユーザーテンプレートディレクトリ。
    """

    def __init__(self, project_root: Optional[Path] = None):
        """TemplateManager を初期化する。

        Args:
            project_root: プロジェクトルートパス。None の場合はデフォルトを使用。
        """
        if project_root is not None:
            self.builtin_dir = project_root / "templates" / "builtin"
            self.user_dir = project_root / "templates" / "user"
        else:
            self.builtin_dir = BUILTIN_DIR
            self.user_dir = USER_DIR

        # ユーザーディレクトリを自動作成
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def _load_from_dir(self, directory: Path) -> list[InvestigationTemplate]:
        """指定ディレクトリ内の全 JSON ファイルを読み込む。

        Args:
            directory: 読み込み対象ディレクトリ。

        Returns:
            テンプレートのリスト。読み込みエラーのファイルはスキップ。
        """
        templates = []
        if not directory.exists():
            return templates

        for json_file in sorted(directory.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                templates.append(InvestigationTemplate.from_dict(data))
            except (json.JSONDecodeError, ValueError, KeyError):
                # 壊れたファイルはスキップ
                continue

        return templates

    def list_templates(
        self, category: Optional[str] = None
    ) -> list[InvestigationTemplate]:
        """全テンプレートを取得する。

        builtin と user の両方を返す。category を指定するとフィルタリング。

        Args:
            category: フィルタするカテゴリ。None の場合は全件返却。

        Returns:
            テンプレートのリスト。
        """
        templates = self._load_from_dir(self.builtin_dir)
        templates.extend(self._load_from_dir(self.user_dir))

        if category is not None:
            templates = [t for t in templates if t.category == category]

        return templates

    def get_template(self, template_id: str) -> InvestigationTemplate:
        """ID でテンプレートを検索する。

        builtin -> user の順で検索し、最初に見つかったものを返す。

        Args:
            template_id: テンプレートID。

        Returns:
            テンプレートインスタンス。

        Raises:
            KeyError: テンプレートが見つからない場合。
        """
        # builtin を先に検索
        for directory in (self.builtin_dir, self.user_dir):
            json_path = directory / f"{template_id}.json"
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return InvestigationTemplate.from_dict(data)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

        raise KeyError(f"テンプレート '{template_id}' が見つかりません")

    def save_template(self, template: InvestigationTemplate) -> Path:
        """ユーザーテンプレートを保存する。

        Args:
            template: 保存するテンプレート。

        Returns:
            保存先のファイルパス。

        Raises:
            PermissionError: 組み込みテンプレートを保存しようとした場合。
        """
        if template.is_builtin:
            raise PermissionError(
                "組み込みテンプレートは保存できません。"
                "is_builtin=False に変更してください。"
            )

        template.updated_at = datetime.now().isoformat()
        save_path = self.user_dir / f"{template.id}.json"

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(template.to_dict(), f, ensure_ascii=False, indent=4)

        return save_path

    def delete_template(self, template_id: str) -> bool:
        """ユーザーテンプレートを削除する。

        Args:
            template_id: 削除するテンプレートのID。

        Returns:
            削除成功なら True。

        Raises:
            PermissionError: 組み込みテンプレートを削除しようとした場合。
            KeyError: テンプレートが見つからない場合。
        """
        # 組み込みテンプレートの削除を拒否
        builtin_path = self.builtin_dir / f"{template_id}.json"
        if builtin_path.exists():
            raise PermissionError(
                f"組み込みテンプレート '{template_id}' は削除できません"
            )

        user_path = self.user_dir / f"{template_id}.json"
        if not user_path.exists():
            raise KeyError(f"テンプレート '{template_id}' が見つかりません")

        user_path.unlink()
        return True

    def import_from_text(
        self, text: str, separator: str = ","
    ) -> list[str]:
        """テキストから属性リストを抽出する。

        カンマ・改行・指定セパレータで分割し、空白をトリミング。

        Args:
            text: 属性が含まれたテキスト。
            separator: 区切り文字（デフォルト: カンマ）。

        Returns:
            属性文字列のリスト（空文字列は除外）。
        """
        # 改行で分割してからセパレータで分割
        items = []
        for line in text.splitlines():
            for item in line.split(separator):
                stripped = item.strip()
                if stripped:
                    items.append(stripped)
        return items

    def import_from_excel(
        self, file_path: Path, column: int = 0
    ) -> list[str]:
        """Excel ファイルから属性リストを読み取る。

        Args:
            file_path: Excel ファイルのパス。
            column: 読み取る列のインデックス（0始まり）。

        Returns:
            属性文字列のリスト（空セルは除外）。

        Raises:
            FileNotFoundError: ファイルが存在しない場合。
            ImportError: openpyxl がインストールされていない場合。
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        try:
            import openpyxl
        except ImportError:
            raise ImportError(
                "Excel読み込みには openpyxl が必要です。"
                "pip install openpyxl でインストールしてください。"
            )

        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active

        items = []
        for row in ws.iter_rows(min_col=column + 1, max_col=column + 1):
            cell = row[0]
            if cell.value is not None:
                value = str(cell.value).strip()
                if value:
                    items.append(value)

        wb.close()
        return items

    def export_template(self, template_id: str) -> dict:
        """テンプレートを辞書として返す。

        Args:
            template_id: エクスポートするテンプレートのID。

        Returns:
            JSON シリアライズ可能な辞書。

        Raises:
            KeyError: テンプレートが見つからない場合。
        """
        template = self.get_template(template_id)
        return template.to_dict()
