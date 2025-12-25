#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
店舗情報スクレイピングツール v1.0
=====================================
企業公式サイトから店舗情報（店舗名・住所・電話番号・URL）を自動抽出

【使い方】
1. 環境準備:
   pip install -r requirements.txt
   playwright install chromium

2. 企業URL一覧を準備:
   - company_urls.txt に1行1URLで記載
   - または company_urls.csv を作成（企業名,URL の形式）

3. 実行:
   python store_scraper.py

4. 結果:
   - output/店舗一覧_YYYYMMDD_HHMMSS.csv
   - output/店舗一覧_YYYYMMDD_HHMMSS.xlsx

【必要なAPIキー】
- GOOGLE_API_KEY: Gemini API用（~/.env.local に設定）

【注意事項】
- スクレイピング対象サイトの利用規約を遵守してください
- robots.txt を確認し、許可されているページのみ取得してください
- 過度なアクセスを避けるため、適切な間隔を空けてください
"""

import asyncio
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import google.generativeai as genai
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

# ====================================
# 設定
# ====================================
console = Console()

# 環境変数読み込み
load_dotenv(Path.home() / ".env.local")

# Gemini API設定
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    console.print("[bold red]エラー: GOOGLE_API_KEY が設定されていません[/]")
    console.print("~/.env.local に GOOGLE_API_KEY=your_api_key を追加してください")
    sys.exit(1)

genai.configure(api_key=GOOGLE_API_KEY)

# Geminiモデル設定
MODEL_NAME = "gemini-2.0-flash"  # 高速・低コスト
model = genai.GenerativeModel(MODEL_NAME)

# スクレイピング設定
REQUEST_DELAY = 2.0  # リクエスト間隔（秒）
MAX_STORES_PER_COMPANY = 500  # 1企業あたりの最大店舗数
TIMEOUT = 30000  # ページ読み込みタイムアウト（ミリ秒）


# ====================================
# データクラス
# ====================================
@dataclass
class StoreInfo:
    """店舗情報"""
    company_name: str  # 企業名
    store_name: str  # 店舗名
    address: str  # 住所
    phone: str  # 電話番号
    url: str  # 店舗ページURL
    prefecture: str = ""  # 都道府県
    business_hours: str = ""  # 営業時間（おまけ）
    note: str = ""  # 備考


@dataclass
class CompanyConfig:
    """企業設定"""
    name: str
    url: str
    store_list_pattern: str = ""  # 店舗一覧ページのパターン（オプション）


# ====================================
# LLM解析
# ====================================
async def find_store_list_page(page: Page, company_name: str) -> list[str]:
    """
    ページ内のリンクを解析し、店舗一覧ページの候補URLを返す
    """
    # ページのリンク一覧を取得
    links = await page.evaluate("""
        () => {
            const anchors = document.querySelectorAll('a[href]');
            return Array.from(anchors).map(a => ({
                href: a.href,
                text: a.textContent.trim().substring(0, 100)
            })).filter(l => l.href && l.text);
        }
    """)

    if not links:
        return []

    # リンク一覧をテキスト化（最大100件）
    links_text = "\n".join([
        f"- {l['text']}: {l['href']}"
        for l in links[:100]
    ])

    prompt = f"""
以下は企業「{company_name}」のWebページにあるリンク一覧です。
店舗一覧・店舗検索ページへのリンクを特定してください。

【リンク一覧】
{links_text}

【出力形式】
店舗一覧ページのURLのみをJSON配列で出力してください。
候補が複数ある場合は最も適切なものを最大3つ選んでください。
見つからない場合は空の配列 [] を返してください。

例: ["https://example.com/shops", "https://example.com/store-list"]
"""

    try:
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={"temperature": 0.1}
        )

        # JSONを抽出
        text = response.text.strip()
        # ```json ブロックを処理
        if "```" in text:
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                text = match.group()

        urls = json.loads(text)
        return urls if isinstance(urls, list) else []

    except Exception as e:
        console.print(f"[yellow]警告: 店舗一覧ページ探索エラー: {e}[/]")
        return []


async def extract_store_info_from_html(
    html: str,
    company_name: str,
    base_url: str
) -> list[StoreInfo]:
    """
    HTMLから店舗情報を抽出
    """
    # HTMLが大きすぎる場合は切り詰め
    max_chars = 50000
    if len(html) > max_chars:
        html = html[:max_chars] + "\n... (以下省略)"

    prompt = f"""
以下のHTMLから店舗情報を抽出してください。

【企業名】{company_name}
【ページURL】{base_url}

【抽出項目】
- store_name: 店舗名
- address: 住所（都道府県から番地まで）
- phone: 電話番号（ハイフン付き形式）
- prefecture: 都道府県
- business_hours: 営業時間（あれば）
- url: 店舗詳細ページURL（あれば、なければ空文字）

【出力形式】
JSON配列で出力してください。店舗が見つからない場合は空配列 [] を返してください。

例:
[
  {{
    "store_name": "渋谷店",
    "address": "東京都渋谷区道玄坂1-2-3",
    "phone": "03-1234-5678",
    "prefecture": "東京都",
    "business_hours": "10:00-21:00",
    "url": "https://example.com/shops/shibuya"
  }}
]

【HTML】
{html}
"""

    try:
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={"temperature": 0.1}
        )

        text = response.text.strip()

        # ```json ブロックを処理
        if "```" in text:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                text = match.group()

        stores_data = json.loads(text)

        if not isinstance(stores_data, list):
            return []

        stores = []
        for data in stores_data[:MAX_STORES_PER_COMPANY]:
            store = StoreInfo(
                company_name=company_name,
                store_name=data.get("store_name", ""),
                address=data.get("address", ""),
                phone=data.get("phone", ""),
                prefecture=data.get("prefecture", ""),
                business_hours=data.get("business_hours", ""),
                url=data.get("url", ""),
            )
            if store.store_name or store.address:  # 最低限の情報があれば追加
                stores.append(store)

        return stores

    except json.JSONDecodeError as e:
        console.print(f"[yellow]警告: JSON解析エラー: {e}[/]")
        return []
    except Exception as e:
        console.print(f"[yellow]警告: 店舗情報抽出エラー: {e}[/]")
        return []


# ====================================
# スクレイピング
# ====================================
async def scrape_company(
    browser: Browser,
    company: CompanyConfig,
    progress: Progress,
    task_id
) -> list[StoreInfo]:
    """
    1企業の店舗情報をスクレイピング
    """
    stores: list[StoreInfo] = []

    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # トップページにアクセス
        progress.update(task_id, description=f"[cyan]{company.name}[/] - ページ読み込み中...")
        await page.goto(company.url, timeout=TIMEOUT, wait_until="networkidle")
        await asyncio.sleep(REQUEST_DELAY)

        # 店舗一覧ページを探索
        progress.update(task_id, description=f"[cyan]{company.name}[/] - 店舗一覧を探索中...")

        # パターンが指定されている場合はそれを使用
        if company.store_list_pattern:
            store_list_urls = [urljoin(company.url, company.store_list_pattern)]
        else:
            store_list_urls = await find_store_list_page(page, company.name)

        if not store_list_urls:
            # トップページ自体が店舗一覧の可能性もある
            console.print(f"[yellow]{company.name}: 店舗一覧ページが見つかりません。トップページを解析します。[/]")
            store_list_urls = [company.url]

        # 店舗一覧ページを処理
        for store_url in store_list_urls[:3]:  # 最大3ページ
            try:
                progress.update(task_id, description=f"[cyan]{company.name}[/] - {urlparse(store_url).path}")

                if store_url != company.url:
                    await page.goto(store_url, timeout=TIMEOUT, wait_until="networkidle")
                    await asyncio.sleep(REQUEST_DELAY)

                # ページのHTMLを取得
                html = await page.content()

                # 店舗情報を抽出
                progress.update(task_id, description=f"[cyan]{company.name}[/] - 店舗情報を抽出中...")
                extracted = await extract_store_info_from_html(html, company.name, store_url)

                if extracted:
                    console.print(f"[green]{company.name}: {len(extracted)}件の店舗を抽出[/]")
                    stores.extend(extracted)
                    break  # 成功したら終了

            except Exception as e:
                console.print(f"[yellow]{company.name}: ページ処理エラー ({store_url}): {e}[/]")
                continue

        await context.close()

    except Exception as e:
        console.print(f"[red]{company.name}: スクレイピングエラー: {e}[/]")

    return stores


async def main():
    """メイン処理"""
    console.print("\n[bold blue]🏪 店舗情報スクレイピングツール v1.0[/]\n")

    # 作業ディレクトリ
    work_dir = Path(__file__).parent
    output_dir = work_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # 企業URL一覧を読み込み
    companies: list[CompanyConfig] = []

    # CSVファイルを優先
    csv_file = work_dir / "company_urls.csv"
    txt_file = work_dir / "company_urls.txt"

    if csv_file.exists():
        console.print(f"[dim]入力ファイル: {csv_file}[/]")
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                companies.append(CompanyConfig(
                    name=row.get("企業名", row.get("name", "")),
                    url=row.get("URL", row.get("url", "")),
                    store_list_pattern=row.get("店舗一覧パス", row.get("pattern", ""))
                ))
    elif txt_file.exists():
        console.print(f"[dim]入力ファイル: {txt_file}[/]")
        with open(txt_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # URLから企業名を推測
                    parsed = urlparse(line)
                    name = parsed.netloc.replace("www.", "")
                    companies.append(CompanyConfig(name=name, url=line))
    else:
        # サンプルファイルを作成
        console.print("[yellow]企業URL一覧ファイルが見つかりません。サンプルを作成します。[/]")

        sample_csv = """企業名,URL,店舗一覧パス
スターバックス,https://www.starbucks.co.jp,/store/search/
マクドナルド,https://www.mcdonalds.co.jp,/shop/search/
セブンイレブン,https://www.sej.co.jp,/shop/
"""
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write(sample_csv)

        console.print(f"[green]サンプルファイルを作成しました: {csv_file}[/]")
        console.print("企業URLを編集して再実行してください。")
        return

    if not companies:
        console.print("[red]処理対象の企業がありません。[/]")
        return

    console.print(f"[bold]処理対象: {len(companies)}社[/]\n")

    # スクレイピング実行
    all_stores: list[StoreInfo] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:

            task = progress.add_task("処理中...", total=len(companies))

            for company in companies:
                stores = await scrape_company(browser, company, progress, task)
                all_stores.extend(stores)
                progress.advance(task)

        await browser.close()

    # 結果出力
    if not all_stores:
        console.print("\n[yellow]店舗情報が取得できませんでした。[/]")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # CSV出力
    csv_output = output_dir / f"店舗一覧_{timestamp}.csv"
    with open(csv_output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "company_name", "store_name", "address", "prefecture",
            "phone", "business_hours", "url", "note"
        ])
        writer.writeheader()
        for store in all_stores:
            writer.writerow(asdict(store))

    console.print(f"\n[green]✅ CSV出力: {csv_output}[/]")

    # Excel出力（openpyxlがあれば）
    try:
        import openpyxl
        from openpyxl.utils.dataframe import dataframe_to_rows

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "店舗一覧"

        # ヘッダー
        headers = ["企業名", "店舗名", "住所", "都道府県", "電話番号", "営業時間", "URL", "備考"]
        ws.append(headers)

        # データ
        for store in all_stores:
            ws.append([
                store.company_name,
                store.store_name,
                store.address,
                store.prefecture,
                store.phone,
                store.business_hours,
                store.url,
                store.note,
            ])

        xlsx_output = output_dir / f"店舗一覧_{timestamp}.xlsx"
        wb.save(xlsx_output)
        console.print(f"[green]✅ Excel出力: {xlsx_output}[/]")

    except ImportError:
        console.print("[dim]（openpyxlがないためExcel出力はスキップ）[/]")

    # サマリー表示
    console.print("\n[bold]📊 抽出結果サマリー[/]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("企業名", style="cyan")
    table.add_column("店舗数", justify="right")

    # 企業別集計
    company_counts = {}
    for store in all_stores:
        company_counts[store.company_name] = company_counts.get(store.company_name, 0) + 1

    for company, count in sorted(company_counts.items()):
        table.add_row(company, str(count))

    table.add_row("[bold]合計[/]", f"[bold]{len(all_stores)}[/]")

    console.print(table)


if __name__ == "__main__":
    asyncio.run(main())
