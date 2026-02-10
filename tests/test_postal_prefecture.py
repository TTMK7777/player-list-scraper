#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
core/postal_prefecture.py のテスト
"""

import sys
from pathlib import Path

import pytest

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.postal_prefecture import extract_prefecture_from_postal, POSTAL_PREFIX_MAP, PREFECTURES


class TestExtractPrefectureFromPostal:
    """extract_prefecture_from_postal() のテスト"""

    # 全47都道府県の代表的な郵便番号
    @pytest.mark.parametrize("postal,expected", [
        ("060-0000", "北海道"),
        ("030-0000", "青森県"),
        ("020-0000", "岩手県"),
        ("980-0000", "宮城県"),
        ("010-0000", "秋田県"),
        ("990-0000", "山形県"),
        ("960-0000", "福島県"),
        ("300-0000", "茨城県"),
        ("320-0000", "栃木県"),
        ("370-0000", "群馬県"),
        ("330-0000", "埼玉県"),
        ("260-0000", "千葉県"),
        ("100-0001", "東京都"),
        ("210-0000", "神奈川県"),
        ("940-0000", "新潟県"),
        ("930-0000", "富山県"),
        ("920-0000", "石川県"),
        ("910-0000", "福井県"),
        ("400-0000", "山梨県"),
        ("380-0000", "長野県"),
        ("500-0000", "岐阜県"),
        ("410-0000", "静岡県"),
        ("440-0000", "愛知県"),
        ("510-0000", "三重県"),
        ("520-0000", "滋賀県"),
        ("600-0000", "京都府"),
        ("530-0000", "大阪府"),
        ("650-0000", "兵庫県"),
        ("630-0000", "奈良県"),
        ("640-0000", "和歌山県"),
        ("680-0000", "鳥取県"),
        ("690-0000", "島根県"),
        ("700-0000", "岡山県"),
        ("720-0000", "広島県"),
        ("740-0000", "山口県"),
        ("770-0000", "徳島県"),
        ("760-0000", "香川県"),
        ("790-0000", "愛媛県"),
        ("780-0000", "高知県"),
        ("800-0000", "福岡県"),
        ("840-0000", "佐賀県"),
        ("850-0000", "長崎県"),
        ("860-0000", "熊本県"),
        ("870-0000", "大分県"),
        ("880-0000", "宮崎県"),
        ("890-0000", "鹿児島県"),
        ("900-0000", "沖縄県"),
    ])
    def test_all_47_prefectures(self, postal, expected):
        """全47都道府県が正しくマッピングされる"""
        assert extract_prefecture_from_postal(postal) == expected

    def test_with_postal_mark(self):
        """〒付き郵便番号"""
        assert extract_prefecture_from_postal("〒100-0001") == "東京都"

    def test_with_postal_mark_and_space(self):
        """〒 + スペース付き"""
        assert extract_prefecture_from_postal("〒 530-0001") == "大阪府"

    def test_without_hyphen(self):
        """ハイフンなし郵便番号"""
        assert extract_prefecture_from_postal("1000001") == "東京都"

    def test_embedded_in_address(self):
        """住所文字列内の郵便番号"""
        assert extract_prefecture_from_postal("〒150-0001 東京都渋谷区") == "東京都"

    def test_empty_string(self):
        """空文字列"""
        assert extract_prefecture_from_postal("") is None

    def test_none(self):
        """None"""
        assert extract_prefecture_from_postal(None) is None

    def test_no_postal_code(self):
        """郵便番号が含まれない文字列"""
        assert extract_prefecture_from_postal("東京都渋谷区") is None

    def test_invalid_prefix(self):
        """存在しない郵便番号プレフィクス"""
        assert extract_prefecture_from_postal("000-0000") is None


class TestBoundaryValues:
    """境界値テスト"""

    def test_hokkaido_lower_bound(self):
        """北海道の下限（001）"""
        assert extract_prefecture_from_postal("001-0000") == "北海道"

    def test_akita_lower_bound(self):
        """秋田県の下限（010）"""
        assert extract_prefecture_from_postal("010-0000") == "秋田県"

    def test_hokkaido_009(self):
        """北海道（009）= 秋田の前"""
        assert extract_prefecture_from_postal("009-0000") == "北海道"

    def test_tokyo_lower_bound(self):
        """東京都の下限（100）"""
        assert extract_prefecture_from_postal("100-0000") == "東京都"

    def test_tokyo_upper_bound(self):
        """東京都の上限（209）"""
        assert extract_prefecture_from_postal("209-0000") == "東京都"

    def test_kanagawa_lower_bound(self):
        """神奈川県の下限（210）"""
        assert extract_prefecture_from_postal("210-0000") == "神奈川県"

    def test_okinawa_upper_bound(self):
        """沖縄県の上限（909）"""
        assert extract_prefecture_from_postal("909-0000") == "沖縄県"

    def test_yamagata_upper_bound(self):
        """山形県の上限（999）"""
        assert extract_prefecture_from_postal("999-0000") == "山形県"


class TestPrefecturesList:
    """PREFECTURES リストのテスト"""

    def test_47_prefectures(self):
        """全47都道府県が含まれる"""
        assert len(PREFECTURES) == 47

    def test_starts_with_hokkaido(self):
        """北海道から始まる"""
        assert PREFECTURES[0] == "北海道"

    def test_ends_with_okinawa(self):
        """沖縄県で終わる"""
        assert PREFECTURES[-1] == "沖縄県"

    def test_all_prefectures_in_map(self):
        """全都道府県がマッピングに含まれる"""
        mapped_prefs = set(POSTAL_PREFIX_MAP.values())
        for pref in PREFECTURES:
            assert pref in mapped_prefs, f"{pref} がマッピングに含まれていません"


class TestStoreScraperExtractFullAddress:
    """store_scraper_v3.extract_full_address() のテスト"""

    def test_full_address_with_postal(self):
        """郵便番号付き完全住所"""
        from store_scraper_v3 import extract_full_address

        text = "〒150-0001 東京都渋谷区神宮前1-2-3 TEL 03-1234-5678"
        result = extract_full_address(text)
        assert "東京都渋谷区" in result
        assert "150-0001" in result
        assert "TEL" not in result
        assert "03-" not in result

    def test_empty_text(self):
        """空文字列"""
        from store_scraper_v3 import extract_full_address
        assert extract_full_address("") == ""

    def test_address_with_phone_separator(self):
        """電話番号を分離"""
        from store_scraper_v3 import extract_full_address

        text = "〒530-0001 大阪府大阪市北区梅田1-1-1 電話06-6123-4567"
        result = extract_full_address(text)
        assert "大阪府" in result
        assert "06-6123" not in result

    def test_prefecture_without_postal(self):
        """郵便番号なし、都道府県名あり"""
        from store_scraper_v3 import extract_full_address

        text = "東京都渋谷区道玄坂1-2-3 ビル5階 営業時間10:00-20:00"
        result = extract_full_address(text)
        assert "東京都渋谷区" in result
        assert "営業時間" not in result

    def test_no_address_found(self):
        """住所が含まれないテキスト"""
        from store_scraper_v3 import extract_full_address
        assert extract_full_address("本日のニュース") == ""
