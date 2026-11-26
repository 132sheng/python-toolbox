#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ZOL 中关村在线 · 手机数据爬虫
============================================================
【需求】
    目标站点：https://detail.zol.com.cn/cell_phone_index/subcate57_list_1.html
    抓取字段：手机图片、手机名称、参考价格、目前评分、点评数、
              京东价格、天猫价格、京东购买链接、天猫购买链接（共 9 项）
    数据量  ：不少于 150 条
    图片存放：phoneImage/ 文件夹（文件名用商品 ID，可重跑续传）
    数据存放：zol_phone.xlsx（图片以真实图片形式写入第 2 列）

【网站类型分析】
    1. 列表页是服务端渲染的静态 HTML，数据直接写在源码里，不需要执行 JS，
       用 requests + lxml 解析即可，不用 Selenium。
    2. 页面字符集是 GBK，必须手动指定编码，否则中文会乱码。
    3. 站点对无 UA / 无 Referer 的请求会拦截或返回空列表，
       所以统一带上浏览器 UA 和 Referer，并控制请求间隔。
    4. 图片放在 pro-fd.zol-img.com.cn / 2x.zol-img.com.cn 等图床，
       要注意列表页里的图片地址写在非标准的 ".src" 属性上（懒加载写法），
       需要依次尝试 .src / src / data-original 三种属性。

【页面结构分析】
    每个商品是一个 <li data-follow-id="p商品ID">，内部结构：
        <a class="pic"><img .src="图片地址" alt="手机名称"></a>
        <h3><a title="名称+卖点">手机名称 <span>卖点</span></a></h3>
        <b class="price-type">6999</b>                 → 参考价格
        <span class="score">9.8</span>                  → 目前评分
        <a class="comment-num">46人点评</a>             → 点评数
        <div class="item-b2cprice">
            <a href="https://union-click.jd.com/...">¥6999</a>   → 京东价格 + 京东链接
            <a href="https://s.click.taobao.com/...">¥5999</a>   → 天猫价格 + 天猫链接
        </div>
    注意：不是每台手机都有评分 / 点评 / 电商价格，缺失时按“保留为空”处理。

【分页规律】
    第 1 页：/cell_phone_index/subcate57_list_1.html
    第 N 页：/cell_phone_index/subcate57_0_list_1_0_1_2_0_N.html
    每页约 48~50 条，要凑够 150 条至少抓 4 页。

【代码实现步骤】
    1. 按分页模板构造 URL，循环请求列表页（带重试、限速）。
    2. 用 lxml 提取每个 <li> 里的 9 个字段，电商链接按域名区分京东 / 天猫。
    3. 用商品 ID 跨页去重，累计到 TARGET_COUNT 条后停止翻页。
    4. 下载图片，统一压缩成统一尺寸存到 phoneImage/（已存在则跳过，支持续跑）。
    5. 用 openpyxl 写 Excel：图片真实插入第 2 列，调整行高列宽，链接可点击。
"""

from __future__ import annotations

import re
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from lxml import html
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image

# ======================= 配置区：改这里就行 =======================
BASE_DIR = Path(__file__).parent                  # 脚本所在目录
START_URL = "https://detail.zol.com.cn/cell_phone_index/subcate57_list_1.html"
PAGE_URL = "https://detail.zol.com.cn/cell_phone_index/subcate57_0_list_1_0_1_2_0_{page}.html"

TARGET_COUNT = 160                # 目标条数（需求 ≥150，多抓一点留余量）
MAX_PAGES = 10                    # 最多翻多少页
REQUEST_DELAY = 1.0               # 翻页间隔（秒）
IMAGE_DELAY = 0.15                # 图片下载间隔（秒）
TIMEOUT = 20                      # 单次请求超时（秒）
RETRY = 3                         # 请求失败重试次数

IMAGE_DIR = BASE_DIR / "phoneImage"
EXCEL_PATH = BASE_DIR / "zol_phone.xlsx"
IMAGE_SIZE = (96, 72)             # 写入 Excel 的缩略图尺寸（像素）

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://detail.zol.com.cn/",
}
COLUMNS = ["序号", "手机图片", "手机名称", "参考价格", "目前评分", "点评数",
           "京东价格", "天猫价格", "京东购买链接", "天猫购买链接"]
# =================================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch(url: str) -> str | None:
    """带重试的 GET，返回解码后的 HTML 文本。"""
    for attempt in range(1, RETRY + 1):
        try:
            resp = SESSION.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            # 站点是 GBK，apparent_encoding 能自动识别；兜底用 gbk
            resp.encoding = resp.apparent_encoding or "gbk"
            return resp.text
        except requests.RequestException as exc:
            print(f"    请求失败（{attempt}/{RETRY}）：{type(exc).__name__}")
            time.sleep(attempt * 2)
    return None


def to_number(text: str, as_int: bool = True):
    """从 “￥6999”“46人点评” 这类文本里取出数字，取不到返回空字符串。"""
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    if not match:
        return ""
    value = float(match.group())
    return int(value) if as_int and value.is_integer() else value


def parse_page(html_text: str, page: int) -> list[dict]:
    """解析一页列表，返回商品字典列表。"""
    doc = html.fromstring(html_text, parser=html.HTMLParser(encoding="gbk"))
    products: list[dict] = []

    for li in doc.xpath('//*[@id="J_PicMode"]/li'):
        img = li.xpath('.//a[contains(@class,"pic")]/img')
        if not img:
            continue  # 广告位 / 空占位，跳过
        img_url = img[0].get(".src") or img[0].get("src") or img[0].get("data-original") or ""
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        if not img_url:
            continue

        name = "".join(li.xpath('./h3/a/text()')).strip() or img[0].get("alt", "").strip()
        if not name:
            continue

        detail_href = (li.xpath('./h3/a/@href') or [""])[0]
        match = re.search(r"index(\d+)", detail_href)
        pid = li.get("data-follow-id", "").lstrip("p") or (match.group(1) if match else "")

        # 电商价格 / 链接：按域名区分京东和天猫，取第一条
        jd_price = tmall_price = ""
        jd_url = tmall_url = ""
        for a in li.xpath('.//div[contains(@class,"item-b2cprice")]/a'):
            href = a.get("href", "")
            price = to_number(a.text_content())
            if "jd.com" in href and not jd_url:
                jd_url, jd_price = href, price
            elif "taobao.com" in href and not tmall_url:
                tmall_url, tmall_price = href, price

        products.append({
            "pid": pid,
            "name": name,
            "img_url": img_url,
            "ref_price": to_number((li.xpath('.//*[contains(@class,"price-type")]/text()') or [""])[0]),
            "score": to_number((li.xpath('.//span[@class="score"]/text()') or [""])[0], as_int=False),
            "comments": to_number((li.xpath('.//a[contains(@class,"comment-num")]/text()') or [""])[0]),
            "jd_price": jd_price,
            "tmall_price": tmall_price,
            "jd_url": jd_url,
            "tmall_url": tmall_url,
            "page": page,
        })
    return products


def download_image(url: str, pid: str) -> Path | None:
    """下载并压缩图片到 phoneImage/<pid>.jpg，已存在则直接复用。"""
    target = IMAGE_DIR / f"{pid}.jpg"
    if target.exists() and target.stat().st_size > 0:
        return target
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content)).convert("RGB")
        image = image.resize(IMAGE_SIZE, Image.LANCZOS)
        image.save(target, "JPEG", quality=88)
        return target
    except Exception as exc:
        print(f"    图片下载失败 {pid}：{type(exc).__name__}")
        return None


def crawl() -> list[dict]:
    """按分页抓取，跨页去重，达到目标条数后停止。"""
    records: list[dict] = []
    seen: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        url = START_URL if page == 1 else PAGE_URL.format(page=page)
        print(f"[第 {page} 页] {url}")
        html_text = fetch(url)
        if not html_text:
            break

        products = parse_page(html_text, page)
        new_count = 0
        for product in products:
            key = product["pid"] or product["name"]
            if key in seen:
                continue
            seen.add(key)
            product["image_path"] = download_image(product["img_url"], product["pid"] or str(len(records)))
            records.append(product)
            new_count += 1
            if len(records) % 20 == 0:
                print(f"    已采集 {len(records)} 条……")
            if len(records) >= TARGET_COUNT:
                break  # 本页内够数就直接停，避免多下载无用图片
        print(f"    本页 {len(products)} 条，新增 {new_count} 条，累计 {len(records)} 条")

        if len(records) >= TARGET_COUNT:
            print(f"已达到目标 {TARGET_COUNT} 条，停止翻页。")
            break
        time.sleep(REQUEST_DELAY)

    return records[:TARGET_COUNT] if len(records) > TARGET_COUNT else records


def write_excel(records: list[dict]) -> None:
    """写 Excel：图片真实插入第 2 列，附带表头样式、行高、可点击链接。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "ZOL手机数据"

    header_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F81BD")
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.append(COLUMNS)
    ws.row_dimensions[1].height = 26
    for col, _ in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    widths = {"A": 6, "B": 15, "C": 34, "D": 11, "E": 10, "F": 9,
              "G": 11, "H": 11, "I": 42, "J": 42}
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width

    for index, item in enumerate(records, start=1):
        row = index + 1
        ws.row_dimensions[row].height = 54  # 54 磅 ≈ 72 像素，正好容纳缩略图

        ws.cell(row=row, column=1, value=index)
        ws.cell(row=row, column=3, value=item["name"])
        ws.cell(row=row, column=4, value=item["ref_price"])
        ws.cell(row=row, column=5, value=item["score"])
        ws.cell(row=row, column=6, value=item["comments"])
        ws.cell(row=row, column=7, value=item["jd_price"])
        ws.cell(row=row, column=8, value=item["tmall_price"])

        for col, key in ((9, "jd_url"), (10, "tmall_url")):
            cell = ws.cell(row=row, column=col, value=item[key])
            if item[key]:
                cell.hyperlink = item[key]
                cell.font = Font(name="微软雅黑", size=9, color="0563C1", underline="single")

        for col in (1, 4, 5, 6, 7, 8):
            ws.cell(row=row, column=col).alignment = center
        ws.cell(row=row, column=3).alignment = Alignment(vertical="center", wrap_text=True)
        for col in range(1, len(COLUMNS) + 1):
            ws.cell(row=row, column=col).border = border

        image_path: Path | None = item.get("image_path")
        if image_path and image_path.exists():
            picture = XLImage(str(image_path))
            picture.width, picture.height = IMAGE_SIZE
            ws.add_image(picture, f"B{row}")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(records) + 1}"
    wb.save(EXCEL_PATH)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"开始抓取，目标 {TARGET_COUNT} 条……")

    records = crawl()
    if len(records) < 150:
        print(f"警告：只抓到 {len(records)} 条，不足 150 条，可调大 MAX_PAGES / TARGET_COUNT 后重跑。")

    write_excel(records)
    with_image = sum(1 for r in records if r.get("image_path"))
    print(f"\n完成：共 {len(records)} 条数据，其中 {with_image} 张图片已保存")
    print(f"图片目录：{IMAGE_DIR}")
    print(f"数据文件：{EXCEL_PATH}")


if __name__ == "__main__":
    main()
