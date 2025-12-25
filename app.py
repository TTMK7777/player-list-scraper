#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗情報スクレイピングツール GUI v2.0
改善版 - 多段階ページ巡回対応
"""

import csv
import json
import os
import re
import io
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="店舗情報スクレイパー v2",
    page_icon="🏪",
    layout="wide"
)

# リクエストヘッダー
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}


# ====================================
# データクラス
# ====================================
@dataclass
class StoreInfo:
    company_name: str
    store_name: str
    address: str
    phone: str
    url: str
    prefecture: str = ""
    business_hours: str = ""


# ====================================
# 初期化
# ====================================
def init_apis():
    """Perplexity API初期化"""
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".env.local", override=True)

    api_key = os.getenv("PERPLEXITY_API_KEY")

    if api_key:
        st.sidebar.caption(f"🔑 Key: {api_key[:15]}...")

    return api_key


def call_llm(api_key: str, prompt: str) -> str:
    """Perplexity API呼び出し"""
    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 8000
            },
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"API呼び出しエラー: {e}")
        return ""


def fetch_page(url: str) -> tuple[str, BeautifulSoup]:
    """ページ取得"""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.encoding = response.apparent_encoding
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    return html, soup


# ====================================
# 店舗一覧ページ探索（改善版）
# ====================================
def find_store_pages(soup: BeautifulSoup, base_url: str, company_name: str, api_key: str) -> list[str]:
    """店舗一覧ページの候補を探索"""

    # まず、よくあるパターンを直接チェック
    common_patterns = [
        "/store", "/stores", "/shop", "/shops", "/studio", "/studios",
        "/location", "/locations", "/branch", "/branches", "/outlet",
        "/tenpo", "/店舗", "/access"
    ]

    candidate_urls = set()

    # パターンマッチング
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True).lower()

        # 店舗関連のリンクを検出
        if any(p in href.lower() for p in common_patterns):
            full_url = urljoin(base_url, href)
            candidate_urls.add(full_url)

        # テキストで検出
        if any(kw in text for kw in ["店舗", "アクセス", "店舗一覧", "店舗紹介", "店舗情報"]):
            full_url = urljoin(base_url, href)
            candidate_urls.add(full_url)

    # 候補が多すぎる場合はLLMで絞り込み
    if len(candidate_urls) > 5:
        links_text = "\n".join([f"- {url}" for url in list(candidate_urls)[:30]])
        prompt = f"""
以下は「{company_name}」のサイトにある店舗関連のURL候補です。
店舗一覧ページとして最も適切なURLを最大3つ選んでください。

【URL候補】
{links_text}

【出力形式】
URLのみを改行区切りで出力。余計な説明は不要。
"""
        result = call_llm(api_key, prompt)
        if result:
            candidate_urls = set()
            for line in result.strip().split("\n"):
                line = line.strip()
                if line.startswith("http"):
                    candidate_urls.add(line.split()[0])

    return list(candidate_urls)[:5]


# ====================================
# 店舗情報抽出（改善版）
# ====================================
def extract_stores_from_page(html: str, company_name: str, page_url: str, api_key: str) -> list[StoreInfo]:
    """1ページから店舗情報を抽出"""

    # HTMLが大きすぎる場合は重要部分のみ抽出
    soup = BeautifulSoup(html, "html.parser")

    # 不要な要素を削除
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    # 店舗情報が含まれそうな部分を抽出
    main_content = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|main|store|shop"))

    if main_content:
        clean_html = str(main_content)
    else:
        clean_html = str(soup.body) if soup.body else html

    # HTMLサイズ制限
    if len(clean_html) > 40000:
        clean_html = clean_html[:40000]

    prompt = f"""
以下のHTMLから店舗情報を抽出してください。

【企業名】{company_name}
【ページURL】{page_url}

【抽出項目】
- store_name: 店舗名（必須）
- address: 住所（郵便番号含む）
- phone: 電話番号（ハイフン付き）
- prefecture: 都道府県
- business_hours: 営業時間
- url: 店舗詳細ページURL（相対パスの場合はそのまま）

【重要な指示】
1. すべての店舗を漏れなく抽出してください
2. 店舗名と住所の両方がある場合のみ抽出
3. 重複は除外
4. JSON配列のみ出力（説明文不要）

【出力形式】
```json
[
  {{"store_name": "渋谷店", "address": "〒150-0001 東京都渋谷区...", "phone": "03-1234-5678", "prefecture": "東京都", "business_hours": "10:00-21:00", "url": "/shop/shibuya"}}
]
```

【HTML】
{clean_html}
"""

    try:
        text = call_llm(api_key, prompt)

        if not text:
            return []

        # JSON抽出
        json_match = re.search(r'\[[\s\S]*\]', text)
        if json_match:
            text = json_match.group()

        data = json.loads(text)

        stores = []
        seen = set()

        for item in data:
            store_name = item.get("store_name", "").strip()
            address = item.get("address", "").strip()

            # 重複チェック
            key = f"{store_name}_{address}"
            if key in seen or not store_name:
                continue
            seen.add(key)

            # URL正規化
            store_url = item.get("url", "")
            if store_url and not store_url.startswith("http"):
                store_url = urljoin(page_url, store_url)

            store = StoreInfo(
                company_name=company_name,
                store_name=store_name,
                address=address,
                phone=item.get("phone", "").strip(),
                prefecture=item.get("prefecture", "").strip(),
                business_hours=item.get("business_hours", "").strip(),
                url=store_url
            )
            stores.append(store)

        return stores

    except json.JSONDecodeError as e:
        st.warning(f"JSON解析エラー: {e}")
        return []
    except Exception as e:
        st.error(f"抽出エラー: {e}")
        return []


# ====================================
# メインスクレイピング処理
# ====================================
def scrape_stores(url: str, company_name: str, api_key: str, status_container) -> list[StoreInfo]:
    """店舗情報をスクレイピング（多段階対応）"""
    all_stores = []
    visited_urls = set()

    try:
        # Step 1: トップページ取得
        status_container.info(f"🌐 ページを読み込み中: {url}")
        html, soup = fetch_page(url)
        visited_urls.add(url)

        # Step 2: 店舗一覧ページを探索
        status_container.info("🔍 店舗一覧ページを探索中...")
        store_pages = find_store_pages(soup, url, company_name, api_key)

        # トップページ自体も候補に追加
        if url not in store_pages:
            store_pages.insert(0, url)

        st.sidebar.write(f"📄 探索ページ数: {len(store_pages)}")

        # Step 3: 各ページから店舗情報を抽出
        for i, page_url in enumerate(store_pages):
            if page_url in visited_urls and page_url != url:
                continue
            visited_urls.add(page_url)

            status_container.info(f"📍 ページ {i+1}/{len(store_pages)}: {page_url[:60]}...")

            try:
                if page_url != url:
                    html, soup = fetch_page(page_url)
                    time.sleep(1)  # レート制限対策

                status_container.info(f"🧠 店舗情報を抽出中...")
                stores = extract_stores_from_page(html, company_name, page_url, api_key)

                if stores:
                    st.sidebar.write(f"  → {len(stores)}件")
                    all_stores.extend(stores)

            except Exception as e:
                st.warning(f"ページ処理エラー: {page_url} - {e}")
                continue

        # 重複除去
        seen = set()
        unique_stores = []
        for store in all_stores:
            key = f"{store.store_name}_{store.address}"
            if key not in seen:
                seen.add(key)
                unique_stores.append(store)

        status_container.success(f"✅ 完了: {len(unique_stores)}件の店舗を抽出")
        return unique_stores

    except requests.exceptions.Timeout:
        status_container.error("❌ タイムアウト: サイトの応答が遅いです")
    except requests.exceptions.RequestException as e:
        status_container.error(f"❌ 通信エラー: {str(e)}")
    except Exception as e:
        status_container.error(f"❌ エラー: {str(e)}")

    return all_stores


# ====================================
# UI
# ====================================
def main():
    st.title("🏪 店舗情報スクレイパー v2.0")
    st.caption("企業公式サイトから店舗情報を自動抽出（多段階ページ巡回対応）")

    # サイドバー
    with st.sidebar:
        st.header("⚙️ 設定")

        api_key = init_apis()
        if api_key:
            st.success("✅ Perplexity API 接続OK")
        else:
            st.error("❌ PERPLEXITY_API_KEY が未設定")
            st.info("~/.env.local に設定してください")
            return

        st.divider()
        st.caption("💡 v2.0 新機能")
        st.caption("- 多段階ページ巡回")
        st.caption("- 店舗一覧ページ自動探索")
        st.caption("- 重複自動除去")

    # メインエリア
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📝 入力")

        input_method = st.radio(
            "入力方法",
            ["URL直接入力", "CSVアップロード"],
            horizontal=True
        )

        companies = []

        if input_method == "URL直接入力":
            company_name = st.text_input("企業名", placeholder="例: ライフスタジオ")
            company_url = st.text_input("公式サイトURL", placeholder="https://www.lifestudio.jp/")

            if company_name and company_url:
                companies = [(company_name, company_url)]

        else:
            uploaded = st.file_uploader("CSVファイル", type=["csv"])
            if uploaded:
                content = uploaded.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    name = row.get("企業名", row.get("name", ""))
                    url = row.get("URL", row.get("url", ""))
                    if name and url:
                        companies.append((name, url))
                st.info(f"{len(companies)}社を読み込み")

        run_button = st.button("🚀 スクレイピング開始", type="primary", disabled=not companies)

    with col2:
        st.subheader("📊 結果")
        result_area = st.container()

    # 実行処理
    if run_button and companies:
        all_stores = []

        with result_area:
            for i, (name, url) in enumerate(companies):
                st.markdown(f"**{i+1}/{len(companies)}: {name}**")
                status_container = st.empty()
                stores = scrape_stores(url, name, api_key, status_container)
                all_stores.extend(stores)

            if all_stores:
                st.divider()
                st.success(f"🎉 合計 {len(all_stores)} 件の店舗を抽出")

                import pandas as pd
                df = pd.DataFrame([asdict(s) for s in all_stores])
                df.columns = ["企業名", "店舗名", "住所", "電話番号", "URL", "都道府県", "営業時間"]

                st.dataframe(df, use_container_width=True, height=400)

                csv_data = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 CSVダウンロード",
                    csv_data,
                    f"店舗一覧_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
            else:
                st.warning("店舗情報が取得できませんでした")


if __name__ == "__main__":
    main()
