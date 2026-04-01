#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
定数定義モジュール
==================
バージョン情報とUser-Agent文字列を一元管理する。
"""

__version__ = "7.3"

TOOL_USER_AGENT = (
    f"OriconPlayerListScraper/{__version__} (+https://www.oricon.co.jp/)"
)

BROWSER_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    f"AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Chrome/120.0.0.0 Safari/537.36 "
    f"OriconPlayerListScraper/{__version__}"
)
