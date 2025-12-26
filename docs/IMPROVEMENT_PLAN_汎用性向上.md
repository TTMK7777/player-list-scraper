# 店舗スクレイパー 汎用性向上計画

> **作成日**: 2025-12-26
> **対象**: `store_scraper_v3.py`
> **目的**: どんな企業サイトでも正確に店舗情報を抽出できる汎用性を実現

---

## 1. 現状の問題点

### 1.1 アップルネット（applenet.co.jp）での問題

| 問題 | 現象 | 原因 |
|------|------|------|
| **住所が不完全** | `〒260-0833` のみ（郵便番号だけ） | HTML構造の解析ミス |
| **都道府県が空白** | 住所から抽出できない | 住所が不完全なため |
| **一部店舗は住所欄に店舗名** | `八戸45号店` が住所欄に | 抽出ロジックエラー |

### 1.2 根本原因：住所抽出ロジックのバグ

**アップルネットのHTML構造**:
```html
<p class="p-shop-result-summary-text -addr">
  <span>〒260-0833</span> 千葉県千葉市中央区稲荷町2-1-3
</p>
```

**現在のコード（問題箇所）**:
```python
# _parse_store_card メソッド（688-698行目）
address_elem = card.find(string=re.compile(r'〒'))
if address_elem:
    parent = address_elem.parent  # ← <span> タグを取得
    if parent:
        data["address"] = parent.get_text(strip=True)[:100]  # ← <span>のテキストのみ
```

**問題**:
- `find(string=...)` で見つかるのは `〒260-0833` というテキストノード
- その `parent` は `<span>` タグ
- `<span>.get_text()` は `〒260-0833` のみ
- 本来取りたい `千葉県千葉市中央区稲荷町2-1-3` は `<p>` タグ直下

---

## 2. 修正案

### 2.1 住所抽出ロジックの改善

**修正後のコード**:
```python
def _extract_full_address(self, element) -> str:
    """住所を完全に抽出（複数階層対応）"""

    # 方法1: 〒を含む要素の親の親まで辿る
    postal_elem = element.find(string=re.compile(r'〒[\d\-]+'))
    if postal_elem:
        # 親を2階層まで辿って、住所全体を含む要素を探す
        for _ in range(3):
            parent = postal_elem.parent if hasattr(postal_elem, 'parent') else None
            if parent:
                text = parent.get_text(separator=' ', strip=True)
                # 住所として妥当なパターンか確認
                if re.search(r'〒[\d\-]+\s*[^\s]+[都道府県]', text):
                    return self._clean_address(text)
                postal_elem = parent

    # 方法2: 住所クラスを持つ要素を探す
    addr_classes = ['address', 'addr', 'shop-addr', 'store-address', '-addr']
    for cls in addr_classes:
        addr_elem = element.find(class_=re.compile(cls, re.IGNORECASE))
        if addr_elem:
            return self._clean_address(addr_elem.get_text(separator=' ', strip=True))

    return ""

def _clean_address(self, text: str) -> str:
    """住所文字列をクリーニング"""
    # 不要な空白を正規化
    text = re.sub(r'\s+', ' ', text)
    # 住所の終端を検出（電話番号や営業時間の前まで）
    match = re.match(r'(〒[\d\-]+\s*[^\d]{5,50})', text)
    if match:
        return match.group(1).strip()
    return text[:100].strip()
```

### 2.2 都道府県抽出の改善

**現在の問題**:
- 住所が不完全だと都道府県が抽出できない
- 郵便番号から都道府県を推測する機能がない

**改善案**:
```python
# 郵便番号 → 都道府県マッピング（先頭2桁）
POSTAL_PREF_MAP = {
    "01": "北海道", "02": "北海道", "03": "岩手県", "04": "宮城県",
    "10": "群馬県", "11": "埼玉県", "12": "千葉県", "13": "東京都",
    "14": "神奈川県", "15": "新潟県", "16": "富山県", "17": "石川県",
    # ... 省略
    "89": "鹿児島県", "90": "鹿児島県", "91": "沖縄県",
}

def extract_prefecture_from_postal(postal: str) -> str:
    """郵便番号から都道府県を推測"""
    match = re.search(r'(\d{3})-?(\d{4})', postal)
    if match:
        prefix = match.group(1)[:2]
        return POSTAL_PREF_MAP.get(prefix, "")
    return ""
```

### 2.3 個別店舗ページへの巡回強化

**現状**: 店舗一覧ページのみから抽出
**改善案**: 住所が不完全な場合、個別ページを巡回

```python
async def _enrich_store_details(self, store: StoreInfo, llm: LLMClient) -> StoreInfo:
    """店舗詳細が不完全な場合、個別ページにアクセスして補完"""

    # 住所が郵便番号のみの場合、詳細ページを取得
    if store.url and (not store.address or len(store.address) < 15):
        try:
            html, soup = await self._fetch_page(store.url)
            # 詳細ページから住所を再抽出
            full_address = self._extract_address_from_detail_page(soup)
            if full_address:
                store.address = full_address
                store.prefecture = extract_prefecture(full_address)
        except Exception:
            pass

    return store
```

---

## 3. 汎用性向上のための追加改善

### 3.1 サイト構造パターンの拡充

| パターン | 例 | 対応状況 |
|----------|-----|----------|
| 都道府県コード型 | `/shop/12/` | ✅ 対応済 |
| ローマ字都道府県型 | `/school/tokyo/` | ✅ 対応済 |
| 店舗ID型 | `/shop/0134/` | ✅ 対応済 |
| 検索API型 | `/api/stores?pref=12` | ❌ 未対応 |
| JavaScript動的生成 | React/Vue SPA | ⚠️ 部分対応 |

### 3.2 住所パターンの拡充

```python
# 対応すべき住所パターン
ADDRESS_PATTERNS = [
    # パターン1: 〒XXX-XXXX + 都道府県名
    r'〒[\d\-]+\s*([^\d]+[都道府県][^\d]+)',

    # パターン2: 都道府県名から始まる（郵便番号なし）
    r'(北海道|青森県|...)[^\d]{5,50}',

    # パターン3: 郵便番号と住所が別要素
    # <span>〒XXX-XXXX</span><span>東京都...</span>
    r'〒([\d\-]+)',  # + 次の兄弟要素を取得
]
```

### 3.3 エラーハンドリング強化

```python
# 抽出結果の品質スコアリング
def score_extraction_quality(store: StoreInfo) -> float:
    score = 0.0

    # 店舗名があれば +0.2
    if store.store_name and len(store.store_name) > 2:
        score += 0.2

    # 住所が完全なら +0.4
    if store.address:
        if "都" in store.address or "道" in store.address or "府" in store.address or "県" in store.address:
            score += 0.4
        elif "〒" in store.address:
            score += 0.1  # 郵便番号のみは低スコア

    # 電話番号があれば +0.2
    if store.phone and len(store.phone) >= 10:
        score += 0.2

    # 都道府県が判定できていれば +0.2
    if store.prefecture:
        score += 0.2

    return score
```

---

## 4. テストケース

### 4.1 追加すべきテスト対象サイト

| 企業 | URL | 特徴 |
|------|-----|------|
| アップルネット | applenet.co.jp | 都道府県別一覧 + 個別ページ |
| 明光義塾 | meikogijuku.jp | ローマ字URL + 詳細ページ |
| スターバックス | starbucks.co.jp | 検索API型 |
| ドトール | doutor.co.jp | 検索フォーム型 |
| ガスト | skylark.co.jp | iframe埋め込み型 |

### 4.2 期待される出力品質

| 項目 | 目標 | 現状 |
|------|------|------|
| 店舗名抽出率 | 100% | 95%+ |
| 住所完全抽出率 | 95%+ | **60%** ← 問題 |
| 都道府県判定率 | 95%+ | **60%** ← 問題 |
| 電話番号抽出率 | 90%+ | 85%+ |

---

## 5. 優先度と実装順序

### Phase 1: 緊急修正（住所抽出バグ）
- [ ] `_parse_store_card` の住所抽出ロジック修正
- [ ] 親要素を複数階層辿る処理追加
- [ ] 動作確認（アップルネット）

### Phase 2: 都道府県推測強化
- [ ] 郵便番号→都道府県マッピング追加
- [ ] フォールバック処理

### Phase 3: 詳細ページ巡回
- [ ] 住所不完全時の個別ページアクセス
- [ ] 詳細ページからの情報補完

### Phase 4: 汎用性テスト
- [ ] 複数サイトでのテスト
- [ ] エラーケース対応

---

## 6. 参考：明光義塾との比較

**明光義塾（成功例）**:
```
企業名: 明光義塾
店舗名: 札幌駅前本部教室
住所: 北海道札幌市北区北7条西4丁目4-3 札幌クレストビル 2F
電話番号: 011-736-3600
都道府県: 北海道  ← ✅ 正しく抽出
```

**アップルネット（失敗例）**:
```
企業名: アップル
店舗名: 鹿児島新栄店
住所: 〒890-0072  ← ❌ 郵便番号のみ
電話番号: 0992131107
都道府県:  ← ❌ 空白
```

**差異の原因**:
- 明光義塾: `<p>北海道札幌市...</p>` のようにシンプルな構造
- アップルネット: `<p><span>〒XXX</span> 住所...</p>` のようにネストした構造

---

**次のアクション**: Phase 1 の緊急修正を実施
