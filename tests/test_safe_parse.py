#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
core/safe_parse.py のテスト
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.safe_parse import safe_float, safe_int


class TestSafeFloat:
    """safe_float() のテスト"""

    def test_normal_float(self):
        """正常なfloat値"""
        assert safe_float(0.9) == 0.9

    def test_string_float(self):
        """文字列のfloat変換"""
        assert safe_float("0.85") == 0.85

    def test_none_returns_default(self):
        """None はデフォルト値を返す"""
        assert safe_float(None) == 0.5
        assert safe_float(None, default=0.7) == 0.7

    def test_non_numeric_string_returns_default(self):
        """非数値文字列はデフォルト値を返す"""
        assert safe_float("高い") == 0.5
        assert safe_float("unknown") == 0.5
        assert safe_float("") == 0.5

    def test_clamp_max(self):
        """最大値でクランプ"""
        assert safe_float(1.5, max_val=1.0) == 1.0

    def test_clamp_min(self):
        """最小値でクランプ"""
        assert safe_float(-0.1, min_val=0.0) == 0.0

    def test_nan_returns_default(self):
        """NaN はデフォルト値を返す"""
        assert safe_float(float("nan")) == 0.5

    def test_inf_returns_default(self):
        """Inf はデフォルト値を返す"""
        assert safe_float(float("inf")) == 0.5
        assert safe_float(float("-inf")) == 0.5

    def test_integer_input(self):
        """int入力もfloatに変換"""
        assert safe_float(1) == 1.0


class TestSafeInt:
    """safe_int() のテスト"""

    def test_normal_int(self):
        """正常なint値"""
        assert safe_int(42) == 42

    def test_string_int(self):
        """文字列のint変換"""
        assert safe_int("100") == 100

    def test_float_string(self):
        """float文字列もintに変換（切り捨て）"""
        assert safe_int("3.7") == 3

    def test_none_returns_default(self):
        """None はデフォルト値を返す"""
        assert safe_int(None) == 0
        assert safe_int(None, default=10) == 10

    def test_non_numeric_string_returns_default(self):
        """非数値文字列はデフォルト値を返す"""
        assert safe_int("abc") == 0

    def test_clamp(self):
        """min/max クランプ"""
        assert safe_int(150, min_val=0, max_val=100) == 100
        assert safe_int(-5, min_val=0) == 0
