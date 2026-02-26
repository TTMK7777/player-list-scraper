#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗情報スクレイピングエンジン v3.0 - マルチ戦略対応
=====================================================
どんな事業者でも店舗情報を抽出できる3段階アプローチ

【戦略1】静的HTML解析（高速・低コスト）
【戦略2】ブラウザ自動操作（JavaScript対応）
【戦略3】AI推論 + 複合アプローチ（最終手段）

使用方法:
    from store_scraper_v3 import MultiStrategyScraper
    scraper = MultiStrategyScraper()
    stores = await scraper.scrape("アップルネット", "https://www.applenet.co.jp")
"""

import asyncio
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from core.llm_client import LLMClient

from core.postal_prefecture import POSTAL_PREFIX_MAP, extract_prefecture_from_postal

logger = logging.getLogger(__name__)

# 環境変数読み込み（override=True で .env.local を優先）
load_dotenv(Path.home() / ".env.local", override=True)


# ====================================
# データクラス
# ====================================
@dataclass
class StoreInfo:
    """店舗情報"""
    company_name: str
    store_name: str
    address: str
    phone: str = ""
    url: str = ""
    prefecture: str = ""
    business_hours: str = ""
    fax: str = ""
    email: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def is_valid(self) -> bool:
        """有効な店舗情報かチェック"""
        return bool(self.store_name.strip() and (self.address.strip() or self.phone.strip()))


@dataclass
class ScrapingResult:
    """スクレイピング結果"""
    company_name: str
    url: str
    stores: list[StoreInfo]
    strategy_used: str  # どの戦略で成功したか
    pages_visited: int
    elapsed_time: float
    errors: list[str] = field(default_factory=list)


# ====================================
# 定数
# ====================================
REQUEST_TIMEOUT = 30          # requests タイムアウト（秒）
PLAYWRIGHT_TIMEOUT_MS = 30000  # Playwright タイムアウト（ミリ秒）
CRAWL_SLEEP_INTERVAL = 0.5    # クロール間スリープ（秒）
PREF_SLEEP_INTERVAL = 0.3     # 都道府県間スリープ（秒）
MAX_PAGES_TO_SCRAPE = 10      # 最大スクレイピングページ数
MAX_BROWSER_PAGES = 15         # ブラウザ最大ページ数
MAX_PREFECTURES = 47           # 都道府県数
MAX_HTML_LENGTH = 50000        # HTML最大長


# ====================================
# 共通ユーティリティ
# ====================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}

# 都道府県リスト
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
]


# 郵便番号上位3桁 → 都道府県マッピング（core.postal_prefecture から参照）
POSTAL_PREF_MAP = POSTAL_PREFIX_MAP


def extract_full_address(text: str) -> str:
    """テキストから完全な住所を抽出する

    住所パターン: 〒XXX-XXXX + 都道府県 + 市区町村 + 番地
    複数行にまたがる場合や、電話番号等が混在する場合に分離する。

    Args:
        text: 住所を含むテキスト

    Returns:
        抽出された住所文字列。見つからない場合は空文字列
    """
    if not text:
        return ""

    # パターン1: 〒付き完全住所（最も正確）
    # 郵便番号 + 都道府県 + 市区町村 + 番地（電話番号/営業時間の前まで）
    m = re.search(
        r'(〒[\d\-]+\s*'           # 郵便番号
        r'[^\d]{2,80}?)'           # 都道府県+住所（非数字で始まる）
        r'(?:\s*(?:TEL|tel|電話|営業|定休|FAX|fax|[0-9]{2,4}[\-\(])|$)',
        text,
    )
    if m:
        return m.group(1).strip()

    # パターン2: 都道府県名から始まる住所
    for pref in PREFECTURES:
        idx = text.find(pref)
        if idx >= 0:
            # 都道府県名の前に郵便番号があるかチェック
            prefix_text = text[max(0, idx - 15):idx]
            postal_match = re.search(r'〒[\d\-]+\s*$', prefix_text)

            start = idx
            if postal_match:
                start = max(0, idx - 15) + postal_match.start()

            # 住所の終端を探す（電話番号やTEL等の前）
            rest = text[idx:]
            end_match = re.search(
                r'(?:TEL|tel|電話|営業|定休|FAX|fax|\n|\r)',
                rest,
            )
            if end_match:
                addr = text[start:idx + end_match.start()].strip()
            else:
                addr = text[start:start + 100].strip()

            if len(addr) > 8:
                return addr

    # パターン3: 郵便番号のみ
    m = re.search(r'(〒[\d\-]+\s*.{5,80})', text)
    if m:
        return m.group(1).strip()[:100]

    return ""


def extract_prefecture(text: str) -> str:
    """テキストから都道府県を抽出（郵便番号からの推測付き）"""
    if not text:
        return ""

    # 方法1: 都道府県名から直接抽出
    for pref in PREFECTURES:
        if pref in text:
            return pref

    # 方法2: 「都」「道」「府」「県」なしの場合
    short_names = [p.rstrip("都道府県") for p in PREFECTURES]
    for i, short in enumerate(short_names):
        if short in text and len(short) >= 2:
            return PREFECTURES[i]

    # 方法3: 郵便番号から推測（core.postal_prefecture モジュール使用）
    postal_match = re.search(r"〒?\d{3}-?\d{4}", text)
    if postal_match:
        pref = extract_prefecture_from_postal(postal_match.group())
        if pref:
            return pref

    return ""


def normalize_phone(phone: str) -> str:
    """電話番号を正規化"""
    if not phone:
        return ""
    # 数字とハイフンのみ抽出
    cleaned = re.sub(r'[^\d\-()]', '', phone)
    # 括弧をハイフンに変換
    cleaned = re.sub(r'[()]', '-', cleaned)
    cleaned = re.sub(r'-+', '-', cleaned).strip('-')
    return cleaned


def clean_html(html: str, max_length: int = MAX_HTML_LENGTH) -> str:
    """HTMLをクリーンアップ"""
    soup = BeautifulSoup(html, "html.parser")

    # 不要な要素を削除
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "noscript", "iframe", "svg"]):
        tag.decompose()

    # メインコンテンツを探す
    main = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|main|store|shop|list"))

    if main:
        text = str(main)
    else:
        text = str(soup.body) if soup.body else html

    if len(text) > max_length:
        text = text[:max_length]

    return text


# ====================================
# 戦略インターフェース
# ====================================
class ScrapingStrategy(ABC):
    """スクレイピング戦略の基底クラス"""

    name: str = "base"

    def __init__(self) -> None:
        self._pages_visited: int = 0

    def _count_page_visit(self) -> None:
        """ページアクセスをカウント"""
        self._pages_visited += 1

    def reset_page_count(self) -> None:
        """ページカウンターをリセット"""
        self._pages_visited = 0

    @property
    def pages_visited(self) -> int:
        """訪問ページ数を返す"""
        return self._pages_visited

    @abstractmethod
    async def scrape(
        self,
        company_name: str,
        url: str,
        llm: LLMClient,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> list[StoreInfo]:
        """店舗情報をスクレイピング"""
        pass


# ====================================
# 戦略1: 静的HTML解析
# ====================================
class StaticHTMLStrategy(ScrapingStrategy):
    """
    戦略1: 静的HTML解析（高速・低コスト）
    - BeautifulSoupでページを取得・解析
    - 店舗一覧ページを探索
    - 都道府県別ページを自動巡回
    - LLMでHTMLから店舗情報を抽出
    """

    name = "static_html"

    # 店舗/教室ページのパターン
    STORE_PAGE_PATTERNS = [
        r"/shops?(/|$)", r"/stores?(/|$)", r"/studios?(/|$)",
        r"/locations?(/|$)", r"/branches?(/|$)", r"/outlets?(/|$)",
        r"/tenpo(/|$)", r"/店舗(/|$)", r"/access(/|$)", r"/find(/|$)",
        r"/search(/|$)", r"/area(/|$)", r"/list(/|$)",
        # 教室・塾向け
        r"/schools?(/|$)", r"/classrooms?(/|$)", r"/教室(/|$)",
        r"/kyoshitsu(/|$)", r"/campus(/|$)"
    ]

    # 店舗/教室リンクのテキストパターン
    STORE_TEXT_PATTERNS = [
        "店舗", "アクセス", "支店", "営業所", "拠点", "スタジオ", "サロン",
        "店舗一覧", "店舗紹介", "店舗情報", "店舗検索", "店舗を探す",
        "shops", "stores", "locations", "find",
        # 教室・塾向け
        "教室", "教室一覧", "教室検索", "教室を探す", "近くの教室",
        "school", "classroom", "campus"
    ]

    # 都道府県コード（JIS X 0401準拠）
    PREF_CODES = {
        "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
        "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
        "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
        "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
        "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
        "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
        "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
        "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
        "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
        "46": "鹿児島県", "47": "沖縄県"
    }

    async def scrape(
        self,
        company_name: str,
        url: str,
        llm: LLMClient,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> list[StoreInfo]:

        def log(msg: str):
            if on_progress:
                on_progress(f"[静的解析] {msg}")

        stores = []
        visited = set()

        try:
            # Step 1: トップページを取得
            log(f"トップページを取得中: {url}")
            html, soup = await self._fetch_page(url)
            visited.add(url)

            # Step 2: 店舗一覧ページの候補を探索
            log("店舗一覧ページを探索中...")
            store_page_urls = self._find_store_page_links(soup, url)

            # Step 2.5: 都道府県別ページを探索
            pref_page_urls = self._find_prefecture_page_links(soup, url)
            if pref_page_urls:
                log(f"都道府県別ページ: {len(pref_page_urls)}件検出")

            # トップページも候補に追加
            if url not in store_page_urls:
                store_page_urls.insert(0, url)

            log(f"候補ページ: {len(store_page_urls)}件")

            # Step 3: 各ページから店舗情報を抽出
            for page_url in store_page_urls[:MAX_PAGES_TO_SCRAPE]:  # 最大ページ数
                if page_url in visited and page_url != url:
                    continue
                visited.add(page_url)

                try:
                    log(f"解析中: {page_url[:60]}...")

                    if page_url != url:
                        html, soup = await self._fetch_page(page_url)
                        await asyncio.sleep(CRAWL_SLEEP_INTERVAL)

                    # このページに都道府県別リンクがあれば巡回
                    sub_pref_urls = self._find_prefecture_page_links(soup, page_url)
                    if sub_pref_urls and len(sub_pref_urls) > 5:
                        log(f"都道府県別ページを巡回: {len(sub_pref_urls)}件")
                        pref_stores = await self._crawl_prefecture_pages(
                            sub_pref_urls, visited, company_name, llm, log
                        )
                        stores.extend(pref_stores)
                    else:
                        # LLMで店舗情報を抽出
                        extracted = await self._extract_stores_with_llm(
                            html, company_name, page_url, llm
                        )

                        if extracted:
                            log(f"→ {len(extracted)}件抽出")
                            stores.extend(extracted)

                except (requests.RequestException, ValueError, RuntimeError) as e:
                    log(f"ページエラー: {e}")
                    continue

            # Step 4: 都道府県別ページを直接巡回（まだ店舗が少ない場合）
            if len(stores) < MAX_PAGES_TO_SCRAPE and pref_page_urls:
                log(f"追加巡回: 都道府県別ページ {len(pref_page_urls)}件")
                additional_stores = await self._crawl_prefecture_pages(
                    pref_page_urls, visited, company_name, llm, log
                )
                stores.extend(additional_stores)

            # 重複除去
            stores = self._deduplicate(stores)
            log(f"完了: 合計{len(stores)}件（重複除去後）")

        except Exception as e:
            logger.error("静的HTML解析で予期しないエラー: %s", e, exc_info=True)
            log(f"エラー: {e}")

        return stores

    async def _crawl_prefecture_pages(
        self,
        pref_urls: list[str],
        visited: set[str],
        company_name: str,
        llm: LLMClient,
        log: Callable[[str], None],
    ) -> list[StoreInfo]:
        """都道府県別ページを巡回して店舗情報を抽出する共通ヘルパー"""
        stores: list[StoreInfo] = []
        for pref_url in pref_urls:
            if pref_url in visited:
                continue
            visited.add(pref_url)

            try:
                pref_html, _ = await self._fetch_page(pref_url)
                await asyncio.sleep(PREF_SLEEP_INTERVAL)

                extracted = await self._extract_stores_with_llm(
                    pref_html, company_name, pref_url, llm
                )
                if extracted:
                    log(f"  → {len(extracted)}件抽出")
                    stores.extend(extracted)
            except (requests.RequestException, ValueError, RuntimeError) as e:
                logger.warning("都道府県ページ巡回エラー: %s - %s", pref_url, e)
                continue
        return stores

    async def _fetch_page(self, url: str) -> tuple[str, BeautifulSoup]:
        """ページを取得"""
        response = await asyncio.to_thread(
            requests.get, url, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        self._count_page_visit()
        response.encoding = response.apparent_encoding
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        return html, soup

    def _find_store_page_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """店舗一覧ページへのリンクを探す"""
        candidates = set()

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True).lower()

            # URLパターンでマッチ
            for pattern in self.STORE_PAGE_PATTERNS:
                if re.search(pattern, href.lower()):
                    full_url = urljoin(base_url, href)
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        candidates.add(full_url)
                    break

            # テキストパターンでマッチ
            for kw in self.STORE_TEXT_PATTERNS:
                if kw in text:
                    full_url = urljoin(base_url, href)
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        candidates.add(full_url)
                    break

        return list(candidates)

    # 都道府県名のローマ字マッピング
    PREF_ROMAJI = {
        "hokkaido": "北海道", "aomori": "青森県", "iwate": "岩手県", "miyagi": "宮城県",
        "akita": "秋田県", "yamagata": "山形県", "fukushima": "福島県", "ibaraki": "茨城県",
        "tochigi": "栃木県", "gunma": "群馬県", "saitama": "埼玉県", "chiba": "千葉県",
        "tokyo": "東京都", "kanagawa": "神奈川県", "niigata": "新潟県", "toyama": "富山県",
        "ishikawa": "石川県", "fukui": "福井県", "yamanashi": "山梨県", "nagano": "長野県",
        "gifu": "岐阜県", "shizuoka": "静岡県", "aichi": "愛知県", "mie": "三重県",
        "shiga": "滋賀県", "kyoto": "京都府", "osaka": "大阪府", "hyogo": "兵庫県",
        "nara": "奈良県", "wakayama": "和歌山県", "tottori": "鳥取県", "shimane": "島根県",
        "okayama": "岡山県", "hiroshima": "広島県", "yamaguchi": "山口県", "tokushima": "徳島県",
        "kagawa": "香川県", "ehime": "愛媛県", "kochi": "高知県", "fukuoka": "福岡県",
        "saga": "佐賀県", "nagasaki": "長崎県", "kumamoto": "熊本県", "oita": "大分県",
        "miyazaki": "宮崎県", "kagoshima": "鹿児島県", "okinawa": "沖縄県"
    }

    def _find_prefecture_page_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """都道府県別ページへのリンクを探す"""
        candidates = []
        base_domain = urlparse(base_url).netloc

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            full_url = urljoin(base_url, href)

            # 同一ドメインのみ
            if urlparse(full_url).netloc != base_domain:
                continue

            # 都道府県コード形式を検出（/shop/01/, /store/13/ など）
            pref_code_match = re.search(r'/(?:shop|store|area|pref|school)/(\d{2})/?$', href)
            if pref_code_match:
                code = pref_code_match.group(1)
                if code in self.PREF_CODES:
                    candidates.append(full_url)
                    continue

            # 都道府県ローマ字形式を検出（/school/tokyo/, /store/osaka/ など）
            href_lower = href.lower()
            for romaji, pref_name in self.PREF_ROMAJI.items():
                if f"/{romaji}/" in href_lower or href_lower.endswith(f"/{romaji}"):
                    candidates.append(full_url)
                    break

            # 都道府県名が含まれているリンク
            for pref in PREFECTURES:
                short = pref.rstrip("都道府県")
                # テキストに都道府県名が含まれる
                if short in text or pref in text:
                    # かつ、店舗/教室ページっぽいURL構造
                    if any(p in href.lower() for p in ["/shop", "/store", "/area", "/pref", "/school", "/classroom", "/branch"]):
                        candidates.append(full_url)
                        break

        return list(set(candidates))

    async def _extract_stores_with_llm(
        self,
        html: str,
        company_name: str,
        page_url: str,
        llm: LLMClient
    ) -> list[StoreInfo]:
        """LLMを使用して店舗情報を抽出（パターンマッチングフォールバック付き）"""

        # Step 1: まずHTMLパターンマッチングを試す（高速）
        pattern_stores = self._extract_stores_by_pattern(html, company_name, page_url)
        if pattern_stores:
            return pattern_stores

        # Step 2: LLMで抽出（低速だが柔軟）
        clean = clean_html(html)

        prompt = f"""
以下のHTMLから店舗情報を抽出してください。

【企業名】{company_name}
【ページURL】{page_url}

【抽出項目】
- store_name: 店舗名（「○○店」のような形式、必須）
- address: 住所（郵便番号〒XXX-XXXX + 都道府県 + 市区町村 + 番地）
- phone: 電話番号（ハイフン付き、フリーダイヤル0120含む）
- prefecture: 都道府県名（北海道、東京都、大阪府など）
- business_hours: 営業時間（例: 10:00-19:00）
- url: 店舗詳細ページURL（/shop/XXXX/ のような相対パス）

【抽出のヒント】
- 店舗名は「h2」「h3」タグや「店舗名」の近くにあることが多い
- 住所は「〒」記号の後に続くことが多い
- 電話番号は「tel:」リンクや「0120-」「03-」で始まる
- 店舗一覧ページでは複数店舗がリスト表示されている

【出力形式】JSON配列のみ（説明文不要）
```json
[
  {{"store_name": "渋谷店", "address": "〒150-0001 東京都渋谷区道玄坂1-2-3", "phone": "03-1234-5678", "prefecture": "東京都", "business_hours": "10:00-21:00", "url": "/shop/shibuya"}}
]
```

店舗情報が見つからない場合は空配列 [] を返してください。

【HTML】
{clean}
"""

        try:
            text = llm.call(prompt)
            if not text:
                return []

            # JSON抽出
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                text = json_match.group()

            data = json.loads(text)

            stores = []
            for item in data:
                store_name = item.get("store_name", "").strip()
                address = item.get("address", "").strip()

                if not store_name:
                    continue

                # URL正規化
                store_url = item.get("url", "")
                if store_url and not store_url.startswith("http"):
                    store_url = urljoin(page_url, store_url)

                store = StoreInfo(
                    company_name=company_name,
                    store_name=store_name,
                    address=address,
                    phone=normalize_phone(item.get("phone", "")),
                    prefecture=item.get("prefecture", "") or extract_prefecture(address),
                    business_hours=item.get("business_hours", "").strip(),
                    url=store_url
                )

                if store.is_valid():
                    stores.append(store)

            return stores

        except json.JSONDecodeError:
            return []
        except (RuntimeError, KeyError, TypeError) as e:
            logger.warning("LLM店舗情報抽出エラー: %s", e)
            return []

    def _extract_stores_by_pattern(
        self,
        html: str,
        company_name: str,
        page_url: str
    ) -> list[StoreInfo]:
        """HTMLパターンマッチングで店舗情報を抽出（高速フォールバック）"""

        soup = BeautifulSoup(html, "html.parser")
        stores = []

        # パターン1: 店舗カード形式（divやarticleで囲まれた店舗情報）
        store_cards = soup.find_all(["div", "article", "li"], class_=re.compile(
            r"shop|store|result|item|card", re.IGNORECASE
        ))

        for card in store_cards:
            store_data = self._parse_store_card(card, page_url)
            if store_data:
                store_data["company_name"] = company_name
                store = StoreInfo(**store_data)
                if store.is_valid():
                    stores.append(store)

        # パターン2: 店舗詳細ページ（単一店舗）
        if not stores:
            # タイトルから店舗名を抽出
            title = soup.find("title")
            if title:
                title_text = title.get_text()
                # 「○○店」パターンを探す
                store_name_match = re.search(r'([^|｜\s]+店)', title_text)
                if store_name_match:
                    store_name = store_name_match.group(1)

                    # 住所を探す
                    address = ""
                    address_match = re.search(r'〒[\d\-]+\s*([^\n<]+)', html)
                    if address_match:
                        address = address_match.group(0).strip()

                    # 電話番号を探す
                    phone = ""
                    tel_links = soup.find_all("a", href=re.compile(r"tel:"))
                    if tel_links:
                        phone = tel_links[0].get("href", "").replace("tel:", "")

                    if store_name and (address or phone):
                        store = StoreInfo(
                            company_name=company_name,
                            store_name=store_name,
                            address=address,
                            phone=normalize_phone(phone),
                            prefecture=extract_prefecture(address),
                            url=page_url
                        )
                        if store.is_valid():
                            stores.append(store)

        # パターン3: 店舗/教室一覧リンクから店舗名を抽出
        if not stores:
            # 店舗・教室リンクのパターン
            link_patterns = [
                r"/shop/\d{4}/",      # /shop/0041/
                r"/store/\d+/",       # /store/123/
                r"/school/[a-z]+/[a-z\-]+/",  # /school/tokyo/shibuya/
                r"/classroom/\d+",    # /classroom/123
            ]
            combined_pattern = "|".join(link_patterns)
            store_links = soup.find_all("a", href=re.compile(combined_pattern))

            seen_urls = set()
            for link in store_links:
                href = link.get("href", "")
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # リンクテキストまたは子要素から店舗名を取得
                store_name = ""
                h_tag = link.find(["h2", "h3", "h4"])
                if h_tag:
                    store_name = h_tag.get_text(strip=True)
                else:
                    store_name = link.get_text(strip=True)

                # 「○○店」「○○教室」形式かチェック
                if store_name and ("店" in store_name or "教室" in store_name or len(store_name) < 25):
                    store_name = re.sub(r'\s+', '', store_name)
                    # ノイズ除外
                    if store_name and store_name not in ["店舗を探す", "教室を探す", "教室検索"]:
                        store = StoreInfo(
                            company_name=company_name,
                            store_name=store_name,
                            address="",
                            phone="",
                            url=urljoin(page_url, href)
                        )
                        stores.append(store)

        return stores

    def _parse_store_card(self, card, page_url: str) -> Optional[dict]:
        """店舗カード要素から情報を抽出"""
        data = {
            "store_name": "",
            "address": "",
            "phone": "",
            "prefecture": "",
            "business_hours": "",
            "url": ""
        }

        # 店舗名（h2, h3, または特定クラス）
        name_elem = card.find(["h2", "h3", "h4"]) or card.find(
            class_=re.compile(r"name|title|storename", re.IGNORECASE)
        )
        if name_elem:
            data["store_name"] = name_elem.get_text(strip=True)

        # 住所（複数階層対応で完全な住所を取得）
        address_elem = card.find(string=re.compile(r'〒'))
        if address_elem:
            # 親を複数階層辿って、完全な住所を取得
            current = address_elem.parent
            full_address = ""
            for _ in range(4):  # 最大4階層まで辿る（v6.1: 3→4に拡大）
                if current:
                    text = current.get_text(separator=' ', strip=True)
                    # 住所として妥当か判定（郵便番号 + 都道府県名を含む）
                    if re.search(r'〒[\d\-]+\s*.+[都道府県]', text):
                        full_address = text
                        break
                    # 郵便番号と住所テキストが一定以上の長さ
                    if '〒' in text and len(text) > 15:
                        full_address = text
                        break
                    current = current.parent if hasattr(current, 'parent') else None

            if full_address:
                # extract_full_address で住所部分だけを抽出
                extracted = extract_full_address(full_address)
                if extracted:
                    data["address"] = extracted
                else:
                    # フォールバック: 正規表現で分離
                    addr_match = re.search(
                        r'(〒[\d\-]+\s*[^\d]{5,80}?)'
                        r'(?:\s*(?:TEL|tel|電話|営業|定休|FAX|fax|[0-9]{2,4}[\-\(]))',
                        full_address,
                    )
                    if addr_match:
                        data["address"] = addr_match.group(1).strip()
                    else:
                        data["address"] = full_address[:100].strip()
            else:
                # フォールバック: 直接の親要素を使用
                parent = address_elem.parent
                if parent:
                    raw_text = parent.get_text(separator=' ', strip=True)[:200]
                    extracted = extract_full_address(raw_text)
                    data["address"] = extracted if extracted else raw_text[:100]
        else:
            # 住所クラスを探す
            addr_classes = [r'address', r'addr', r'-addr', r'shop.*addr']
            for cls_pattern in addr_classes:
                addr_elem = card.find(class_=re.compile(cls_pattern, re.IGNORECASE))
                if addr_elem:
                    raw_text = addr_elem.get_text(separator=' ', strip=True)[:200]
                    extracted = extract_full_address(raw_text)
                    data["address"] = extracted if extracted else raw_text[:100]
                    break

        # 電話番号
        tel_link = card.find("a", href=re.compile(r"tel:"))
        if tel_link:
            data["phone"] = tel_link.get("href", "").replace("tel:", "")
        else:
            tel_elem = card.find(class_=re.compile(r"tel|phone", re.IGNORECASE))
            if tel_elem:
                data["phone"] = tel_elem.get_text(strip=True)

        # URL
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if any(p in href for p in ["/shop", "/store", "/school", "/classroom"]):
                data["url"] = urljoin(page_url, href)

        # 都道府県
        data["prefecture"] = extract_prefecture(data["address"])

        # 有効なデータかチェック
        if data["store_name"] and (data["address"] or data["phone"]):
            return data

        return None

    def _deduplicate(self, stores: list[StoreInfo]) -> list[StoreInfo]:
        """重複除去とノイズフィルタリング"""
        # ノイズワード（店舗名/教室名として不適切なパターン）
        noise_patterns = [
            r"^市区町村",
            r"^店舗を探す",
            r"^教室を探す",
            r"^近くの教室",
            r"^検索",
            r"^エリア",
            r"県の中古車",
            r"店舗一覧",
            r"教室一覧",
            r"^(北海道|東北|関東|中部|関西|中国|四国|九州|甲信越)$",
            r"^\d+件$",  # "123件" のような結果数
            # 宣伝文句・キャッチコピー
            r"魔法",
            r"恐るべし",
            r"おトク",
            r"キャンペーン",
            r"フェア",
            r"セール",
            r"お知らせ",
            r"ニュース",
            r"新着",
            r"^お問い?合わせ",
            r"^アクセス$",
            r"^詳細$",
            r"^もっと見る",
        ]

        seen = set()
        unique = []
        for store in stores:
            # ノイズチェック
            is_noise = False
            for pattern in noise_patterns:
                if re.search(pattern, store.store_name):
                    is_noise = True
                    break

            if is_noise:
                continue

            # 店舗名が短すぎる or 長すぎる
            if len(store.store_name) < 2 or len(store.store_name) > 50:
                continue

            # 住所の妥当性チェック
            # - 住所が店舗名と同じ場合は不正（住所取得失敗）
            # - 住所に「〒」または都道府県名が含まれていない場合は不正
            if store.address:
                # 店舗名と住所が同じ = 住所取得失敗
                if store.address == store.store_name:
                    continue
                # 住所として妥当か（〒 または 都道府県名を含む）
                has_postal = "〒" in store.address
                has_pref = any(p in store.address for p in PREFECTURES)
                if not has_postal and not has_pref and len(store.address) < 10:
                    continue

            # 重複チェック（店舗名のみでも重複判定）
            key = store.store_name
            if key not in seen:
                seen.add(key)
                unique.append(store)
        return unique


# ====================================
# 戦略2: ブラウザ自動操作
# ====================================
class BrowserAutomationStrategy(ScrapingStrategy):
    """
    戦略2: ブラウザ自動操作（JavaScript対応）
    - Playwrightでページをレンダリング
    - 都道府県リンクを自動巡回
    - 検索フォームを操作
    """

    name = "browser_automation"

    async def scrape(
        self,
        company_name: str,
        url: str,
        llm: LLMClient,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> list[StoreInfo]:

        def log(msg: str):
            if on_progress:
                on_progress(f"[ブラウザ] {msg}")

        stores = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log("Playwrightがインストールされていません")
            return []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            try:
                # Step 1: トップページにアクセス
                log(f"ページを読み込み中: {url}")
                await page.goto(url, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="networkidle")
                self._count_page_visit()
                await asyncio.sleep(2)

                # Step 2: 店舗ページへのリンクを探す
                log("店舗一覧ページを探索中...")
                store_links = await self._find_store_links(page, url)

                if not store_links:
                    # トップページ自体を解析
                    store_links = [url]

                log(f"探索対象: {len(store_links)}ページ")

                # Step 3: 各ページを巡回
                visited = set()
                for link in store_links[:MAX_BROWSER_PAGES]:
                    if link in visited:
                        continue
                    visited.add(link)

                    try:
                        log(f"巡回中: {link[:60]}...")

                        if link != url:
                            await page.goto(link, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="networkidle")
                            self._count_page_visit()
                            await asyncio.sleep(1)

                        # 都道府県リンクがあれば巡回
                        pref_links = await self._find_prefecture_links(page, link)

                        if pref_links:
                            log(f"都道府県別ページ: {len(pref_links)}件")
                            for pref_link in pref_links[:MAX_PREFECTURES]:
                                if pref_link in visited:
                                    continue
                                visited.add(pref_link)

                                try:
                                    await page.goto(pref_link, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="networkidle")
                                    self._count_page_visit()
                                    await asyncio.sleep(CRAWL_SLEEP_INTERVAL)

                                    html = await page.content()
                                    extracted = await self._extract_stores(html, company_name, pref_link, llm)
                                    if extracted:
                                        stores.extend(extracted)
                                        log(f"  → {len(extracted)}件抽出")
                                except (TimeoutError, ValueError, RuntimeError, TypeError, AttributeError) as e:
                                    logger.warning("ブラウザ都道府県巡回エラー: %s - %s", pref_link, e)
                                    continue
                        else:
                            # 直接抽出
                            html = await page.content()
                            extracted = await self._extract_stores(html, company_name, link, llm)
                            if extracted:
                                stores.extend(extracted)
                                log(f"→ {len(extracted)}件抽出")

                    except (TimeoutError, ValueError, RuntimeError, TypeError, AttributeError) as e:
                        log(f"ページエラー: {e}")
                        continue

            finally:
                await context.close()
                await browser.close()

        # 重複除去
        stores = self._deduplicate(stores)
        log(f"完了: 合計{len(stores)}件（重複除去後）")

        return stores

    async def _find_store_links(self, page, base_url: str) -> list[str]:
        """店舗一覧ページへのリンクを探す"""
        links = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href]');
                return Array.from(anchors).map(a => ({
                    href: a.href,
                    text: a.textContent.trim().toLowerCase()
                })).filter(l => l.href);
            }
        """)

        patterns = [
            r"/shops?(/|$|\?)", r"/stores?(/|$|\?)", r"/studios?(/|$|\?)",
            r"/locations?(/|$|\?)", r"/branches?(/|$|\?)", r"/tenpo(/|$|\?)",
            r"/search(/|$|\?)", r"/find(/|$|\?)", r"/area(/|$|\?)"
        ]

        keywords = ["店舗", "支店", "営業所", "アクセス", "店舗一覧", "店舗を探す"]

        candidates = set()
        base_domain = urlparse(base_url).netloc

        for link in links:
            href = link["href"]
            text = link["text"]

            # 同一ドメインのみ
            if urlparse(href).netloc != base_domain:
                continue

            # パターンマッチ
            for pattern in patterns:
                if re.search(pattern, href.lower()):
                    candidates.add(href)
                    break

            # キーワードマッチ
            for kw in keywords:
                if kw in text:
                    candidates.add(href)
                    break

        return list(candidates)

    async def _find_prefecture_links(self, page, base_url: str) -> list[str]:
        """都道府県別ページへのリンクを探す"""
        links = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href]');
                return Array.from(anchors).map(a => ({
                    href: a.href,
                    text: a.textContent.trim()
                })).filter(l => l.href);
            }
        """)

        candidates = []
        base_domain = urlparse(base_url).netloc

        for link in links:
            href = link["href"]
            text = link["text"]

            if urlparse(href).netloc != base_domain:
                continue

            # 都道府県名が含まれているリンク
            for pref in PREFECTURES:
                short = pref.rstrip("都道府県")
                if short in text or pref in text:
                    candidates.append(href)
                    break

        return list(set(candidates))

    async def _extract_stores(
        self,
        html: str,
        company_name: str,
        page_url: str,
        llm: LLMClient
    ) -> list[StoreInfo]:
        """静的解析と同じLLM抽出を使用"""
        static = StaticHTMLStrategy()
        return await static._extract_stores_with_llm(html, company_name, page_url, llm)

    def _deduplicate(self, stores: list[StoreInfo]) -> list[StoreInfo]:
        """重複除去"""
        seen = set()
        unique = []
        for store in stores:
            key = f"{store.store_name}_{store.address}"
            if key not in seen:
                seen.add(key)
                unique.append(store)
        return unique


# ====================================
# 戦略3: AI推論 + 複合アプローチ
# ====================================
class AIInferenceStrategy(ScrapingStrategy):
    """
    戦略3: AI推論 + 複合アプローチ（最終手段）
    - サイト構造をLLMで分析
    - 内部APIを推測・直接呼び出し
    - 外部検索を活用
    """

    name = "ai_inference"

    async def scrape(
        self,
        company_name: str,
        url: str,
        llm: LLMClient,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> list[StoreInfo]:

        def log(msg: str):
            if on_progress:
                on_progress(f"[AI推論] {msg}")

        stores = []

        try:
            # Step 1: サイト構造を分析
            log("サイト構造を分析中...")
            analysis = await self._analyze_site_structure(url, company_name, llm)

            if analysis.get("api_endpoint"):
                # APIエンドポイントが見つかった場合
                log(f"APIエンドポイント発見: {analysis['api_endpoint']}")
                api_stores = await self._fetch_from_api(
                    analysis["api_endpoint"],
                    company_name,
                    llm
                )
                stores.extend(api_stores)

            if analysis.get("prefecture_urls"):
                # 都道府県別URLが推測された場合
                log(f"都道府県別URL: {len(analysis['prefecture_urls'])}件")
                for pref_url in analysis["prefecture_urls"][:MAX_PREFECTURES]:
                    try:
                        pref_stores = await self._scrape_page(pref_url, company_name, llm)
                        stores.extend(pref_stores)
                    except (requests.RequestException, ValueError, RuntimeError) as e:
                        logger.warning("AI推論 都道府県ページエラー: %s - %s", pref_url, e)
                        continue

            # Step 2: 外部検索で補完（店舗数が少ない場合）
            if len(stores) < MAX_PAGES_TO_SCRAPE:
                log("外部検索で補完中...")
                search_stores = await self._search_stores_external(company_name, url, llm)
                stores.extend(search_stores)

            # 重複除去
            stores = self._deduplicate(stores)
            log(f"完了: 合計{len(stores)}件")

        except Exception as e:
            logger.error("AI推論で予期しないエラー: %s", e, exc_info=True)
            log(f"エラー: {e}")

        return stores

    async def _analyze_site_structure(
        self,
        url: str,
        company_name: str,
        llm: LLMClient
    ) -> dict:
        """サイト構造をLLMで分析"""

        # ページを取得
        response = await asyncio.to_thread(
            requests.get, url, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        self._count_page_visit()
        response.encoding = response.apparent_encoding
        html = response.text

        # ネットワークリクエストのパターンを探す
        api_patterns = re.findall(r'(?:fetch|axios|ajax|XMLHttpRequest)[^;]*["\']([^"\']+api[^"\']*)["\']', html, re.IGNORECASE)
        data_urls = re.findall(r'["\']([^"\']+(?:\.json|/api/|/data/)[^"\']*)["\']', html)

        prompt = f"""
以下の企業サイトの店舗情報取得方法を分析してください。

【企業名】{company_name}
【URL】{url}
【発見されたAPIパターン】
{json.dumps(api_patterns[:10], ensure_ascii=False, indent=2)}
【発見されたデータURL】
{json.dumps(data_urls[:10], ensure_ascii=False, indent=2)}

【分析項目】
1. 店舗情報APIのエンドポイントURL（推測）
2. 都道府県別ページのURLパターン（推測）
3. 店舗情報取得のための最適なアプローチ

【出力形式】JSON
```json
{{
  "api_endpoint": "https://example.com/api/stores (見つからない場合はnull)",
  "prefecture_urls": ["https://example.com/shop/tokyo", ...] (推測できない場合は空配列),
  "recommended_approach": "api|crawl|search",
  "notes": "分析結果のメモ"
}}
```
"""

        try:
            text = llm.call(prompt, model="gemini-2.5-flash")
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, RuntimeError, KeyError, TypeError) as e:
            logger.warning("サイト構造分析エラー: %s", e)

        return {"api_endpoint": None, "prefecture_urls": [], "recommended_approach": "crawl"}

    async def _fetch_from_api(
        self,
        api_url: str,
        company_name: str,
        llm: LLMClient
    ) -> list[StoreInfo]:
        """APIから店舗情報を取得"""
        try:
            response = await asyncio.to_thread(
                requests.get, api_url, headers=HEADERS, timeout=REQUEST_TIMEOUT
            )
            self._count_page_visit()
            data = response.json()

            # LLMでデータを解析
            prompt = f"""
以下のAPIレスポンスから店舗情報を抽出してください。

【企業名】{company_name}
【データ】
{json.dumps(data, ensure_ascii=False, indent=2)[:30000]}

【出力形式】
```json
[
  {{"store_name": "店舗名", "address": "住所", "phone": "電話番号", "prefecture": "都道府県"}}
]
```
"""
            text = llm.call(prompt)
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                items = json.loads(json_match.group())
                return [
                    StoreInfo(
                        company_name=company_name,
                        store_name=item.get("store_name", ""),
                        address=item.get("address", ""),
                        phone=normalize_phone(item.get("phone", "")),
                        prefecture=item.get("prefecture", "")
                    )
                    for item in items
                    if item.get("store_name")
                ]
        except (requests.RequestException, json.JSONDecodeError, RuntimeError, KeyError, TypeError) as e:
            logger.warning("API店舗情報取得エラー: %s - %s", api_url, e)

        return []

    async def _scrape_page(
        self,
        url: str,
        company_name: str,
        llm: LLMClient
    ) -> list[StoreInfo]:
        """静的解析でページをスクレイピング"""
        static = StaticHTMLStrategy()
        html_resp = await asyncio.to_thread(
            requests.get, url, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        self._count_page_visit()
        html_resp.encoding = html_resp.apparent_encoding
        return await static._extract_stores_with_llm(html_resp.text, company_name, url, llm)

    async def _search_stores_external(
        self,
        company_name: str,
        url: str,
        llm: LLMClient
    ) -> list[StoreInfo]:
        """外部検索で店舗情報を取得"""
        domain = urlparse(url).netloc

        prompt = f"""
「{company_name}」（{domain}）の店舗一覧を検索してください。

【求める情報】
- 店舗名
- 住所
- 電話番号
- 都道府県

公式サイトおよび信頼できる情報源から、できるだけ多くの店舗情報を収集してください。

【出力形式】JSON配列のみ
```json
[
  {{"store_name": "渋谷店", "address": "東京都渋谷区...", "phone": "03-xxxx-xxxx", "prefecture": "東京都"}}
]
```
"""

        try:
            # Gemini の検索機能を活用
            text = llm.call(prompt, model="gemini-2.5-flash")
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                items = json.loads(json_match.group())
                return [
                    StoreInfo(
                        company_name=company_name,
                        store_name=item.get("store_name", ""),
                        address=item.get("address", ""),
                        phone=normalize_phone(item.get("phone", "")),
                        prefecture=item.get("prefecture", "")
                    )
                    for item in items
                    if item.get("store_name")
                ]
        except (json.JSONDecodeError, RuntimeError, KeyError, TypeError) as e:
            logger.warning("外部検索による店舗情報取得エラー: %s", e)

        return []

    def _deduplicate(self, stores: list[StoreInfo]) -> list[StoreInfo]:
        """重複除去"""
        seen = set()
        unique = []
        for store in stores:
            key = f"{store.store_name}_{store.address}"
            if key not in seen:
                seen.add(key)
                unique.append(store)
        return unique


# ====================================
# メインスクレイパー
# ====================================
class MultiStrategyScraper:
    """
    マルチ戦略スクレイパー
    3つの戦略を順番に試行し、成功するまで続ける
    """

    def __init__(
        self,
        api_key: str = None,
        min_stores: int = 3
    ):
        """
        Args:
            api_key: Google API キー（未指定時は環境変数から取得）
            min_stores: 成功と判断する最小店舗数
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.min_stores = min_stores

        if not self.api_key:
            raise ValueError("API key is required. Set GOOGLE_API_KEY")

        self.llm = LLMClient(api_key=self.api_key)

        # 戦略の順序
        self.strategies: list[ScrapingStrategy] = [
            StaticHTMLStrategy(),
            BrowserAutomationStrategy(),
            AIInferenceStrategy(),
        ]

    async def scrape(
        self,
        company_name: str,
        url: str,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> ScrapingResult:
        """
        店舗情報をスクレイピング

        Args:
            company_name: 企業名
            url: 企業の公式サイトURL
            on_progress: 進捗コールバック

        Returns:
            ScrapingResult: スクレイピング結果
        """
        start_time = time.time()
        all_stores = []
        strategy_used = ""
        errors = []

        # 前回の scrape() のカウントをリセット
        for strategy in self.strategies:
            strategy.reset_page_count()

        def log(msg: str):
            if on_progress:
                on_progress(msg)

        for strategy in self.strategies:
            log(f"\n{'='*50}")
            log(f"戦略 '{strategy.name}' を試行中...")
            log(f"{'='*50}")

            try:
                stores = await strategy.scrape(
                    company_name,
                    url,
                    self.llm,
                    on_progress
                )

                if stores and len(stores) >= self.min_stores:
                    all_stores = stores
                    strategy_used = strategy.name
                    log(f"\n✅ 戦略 '{strategy.name}' で成功: {len(stores)}件")
                    break
                elif stores:
                    log(f"⚠️ {len(stores)}件のみ取得（最小{self.min_stores}件未満）")
                    all_stores.extend(stores)
                else:
                    log(f"❌ 店舗情報なし")

            except Exception as e:
                error_msg = f"戦略 '{strategy.name}' エラー: {str(e)}"
                logger.error("戦略 '%s' で予期しないエラー: %s", strategy.name, e, exc_info=True)
                errors.append(error_msg)
                log(f"❌ {error_msg}")
                continue

        # 最終結果を統合
        if not strategy_used and all_stores:
            strategy_used = "combined"

        # 重複除去
        seen = set()
        unique_stores = []
        for store in all_stores:
            key = f"{store.store_name}_{store.address}"
            if key not in seen:
                seen.add(key)
                unique_stores.append(store)

        elapsed = time.time() - start_time

        # 全戦略の訪問ページ数を合算
        total_pages_visited = sum(s.pages_visited for s in self.strategies)

        return ScrapingResult(
            company_name=company_name,
            url=url,
            stores=unique_stores,
            strategy_used=strategy_used,
            pages_visited=total_pages_visited,
            elapsed_time=elapsed,
            errors=errors
        )


# ====================================
# CLI
# ====================================
async def main():
    """CLI エントリーポイント"""
    import argparse

    parser = argparse.ArgumentParser(description="店舗情報スクレイパー v3.0")
    parser.add_argument("company_name", help="企業名")
    parser.add_argument("url", help="企業公式サイトURL")
    parser.add_argument("--output", help="出力CSVファイル")

    args = parser.parse_args()

    print(f"\n🏪 店舗情報スクレイパー v3.0")
    print(f"企業: {args.company_name}")
    print(f"URL: {args.url}")
    print()

    scraper = MultiStrategyScraper()

    result = await scraper.scrape(
        args.company_name,
        args.url,
        on_progress=lambda msg: print(msg)
    )

    print(f"\n{'='*50}")
    print(f"📊 結果サマリー")
    print(f"{'='*50}")
    print(f"企業名: {result.company_name}")
    print(f"使用戦略: {result.strategy_used}")
    print(f"店舗数: {len(result.stores)}")
    print(f"処理時間: {result.elapsed_time:.1f}秒")

    if result.errors:
        print(f"エラー: {len(result.errors)}件")

    if result.stores:
        print(f"\n📋 店舗一覧（先頭10件）:")
        for i, store in enumerate(result.stores[:10], 1):
            print(f"  {i}. {store.store_name} - {store.address[:30]}...")

        if args.output:
            import csv
            with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "company_name", "store_name", "address", "phone",
                    "prefecture", "business_hours", "url"
                ])
                writer.writeheader()
                for store in result.stores:
                    writer.writerow(store.to_dict())
            print(f"\n💾 CSV出力: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
