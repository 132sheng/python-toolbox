#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Excel 自动清理：洗表头、去空行空列、去重复、统一文本 / 数字 / 日期格式。

用法：
    python excel_clean.py                            # 按下面「配置区」的设置批量清理
    python excel_clean.py -i ./订单表 -o ./干净数据   # 指定输入文件夹和输出文件夹
    python excel_clean.py -i 明细.xlsx               # 也可以直接处理单个文件
    python excel_clean.py -i ./订单表 --sheet 销售明细

原始文件不会被修改，清洗后的结果统一输出到 OUTPUT_DIR。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# ======================= 配置区：改这里就行 =======================
INPUT_PATH = Path("./待清理")          # 待清理的文件或文件夹
OUTPUT_DIR = Path("./清理结果")        # 清洗结果输出到这里
OUTPUT_SUFFIX = "_清理后"              # 输出文件名后缀：订单表_清理后.xlsx
RECURSIVE = False                      # True 时连子文件夹一起处理

SHEET = "all"                          # "all"=全部工作表，"first"=只处理第一个，也可直接写表名
HEADER_ROW = 1                         # 表头在第几行（从 1 开始）

STRIP_TEXT = True                      # 去掉单元格首尾的空格、换行、全角空格
NORMALIZE_HEADERS = True               # 表头去空格换行，无名列改「列N」，重名列自动加序号
DROP_EMPTY_ROWS = True                 # 删掉整行为空的行
DROP_EMPTY_COLS = True                 # 删掉整列为空的列
DROP_DUPLICATES = True                 # 删掉完全重复的行
TO_NUMBER = True                       # 能转数字的列转成数字（顺手去掉千分位逗号）
TO_DATE = True                         # 列名含「日期 / 时间」的列统一成日期
FILL_NA = None                         # 空值统一填成什么；None 表示保持为空
NULL_TOKENS = {"", "-", "--", "—", "N/A", "NA", "null", "None", "无", "空"}
DATE_KEYWORDS = ("日期", "时间", "date", "time")
# =================================================================

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
INVALID_SHEET_CHARS = set('[]:*?/\\')


def collect_files(path: Path) -> list[Path]:
    """输入是文件就直接用；是文件夹则收集其中的表格。"""
    if path.is_file():
        return [path] if path.suffix.lower() in EXCEL_SUFFIXES else []

    pattern = "**/*" if RECURSIVE else "*"
    return sorted(
        p
        for p in path.glob(pattern)
        if p.is_file()
        and p.suffix.lower() in EXCEL_SUFFIXES
        and not p.name.startswith("~$")
        and OUTPUT_SUFFIX not in p.stem
        and OUTPUT_DIR.resolve() not in p.resolve().parents
    )


def pick_sheets(sheets: dict[str, pd.DataFrame], sheet: str, path: Path) -> dict[str, pd.DataFrame]:
    """按 SHEET / --sheet 选择要处理的工作表。"""
    if sheet == "all":
        return sheets
    if sheet == "first":
        return {next(iter(sheets)): next(iter(sheets.values()))}
    if sheet not in sheets:
        raise SystemExit(f"{path.name} 里没有工作表「{sheet}」，现有：{'、'.join(sheets)}")
    return {sheet: sheets[sheet]}


def normalize_headers(columns) -> list[str]:
    """表头规范化：去空白、补无名列、重名加序号。"""
    names: list[str] = []
    for index, col in enumerate(columns):
        name = "" if pd.isna(col) else str(col)
        name = name.replace("\u3000", " ").replace("\n", " ").strip()
        if not name or name.startswith("Unnamed:"):
            name = f"列{index + 1}"
        names.append(name)

    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        if name in seen:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            result.append(name)
    return result


def strip_text(df: pd.DataFrame) -> pd.DataFrame:
    """清理文本单元格里的首尾空白、换行和全角空格。"""
    for col in df.columns:
        if not pd.api.types.is_object_dtype(df[col]):
            continue
        df[col] = df[col].map(
            lambda v: v.replace("\u3000", " ").replace("\r", "").replace("\n", " ").strip()
            if isinstance(v, str)
            else v
        )
    return df


def replace_null_tokens(df: pd.DataFrame) -> pd.DataFrame:
    """把 “-”“无”“N/A” 这类占位符统一当成空值。"""
    tokens = {t.strip().lower() for t in NULL_TOKENS}
    for col in df.columns:
        if not pd.api.types.is_object_dtype(df[col]):
            continue
        df[col] = df[col].map(
            lambda v: pd.NA if isinstance(v, str) and v.strip().lower() in tokens else v
        )
    return df


def to_number(df: pd.DataFrame, stats: dict[str, int]) -> pd.DataFrame:
    """八成以上单元格能解析成数字的列，直接转成数字类型。"""
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            continue
        cleaned = series.map(lambda v: v.replace(",", "").replace("，", "") if isinstance(v, str) else v)
        valid = cleaned.dropna()
        if valid.empty or pd.to_numeric(valid, errors="coerce").notna().mean() < 0.8:
            continue
        df[col] = pd.to_numeric(cleaned, errors="coerce")
        stats["数字列"] += 1
    return df


def to_date(df: pd.DataFrame, stats: dict[str, int]) -> pd.DataFrame:
    """列名带日期关键词、且八成以上能解析的列，转成日期类型。"""
    for col in df.columns:
        if not any(key in str(col).lower() for key in DATE_KEYWORDS):
            continue
        series = df[col]
        # 纯数字列（如 20240105）容易误判，交给使用者自己处理
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            continue
        valid = series.dropna()
        if valid.empty or pd.to_datetime(valid, errors="coerce", format="mixed").notna().mean() < 0.8:
            continue
        df[col] = pd.to_datetime(series, errors="coerce", format="mixed")
        stats["日期列"] += 1
    return df


def clean_sheet(df: pd.DataFrame, stats: dict[str, int]) -> pd.DataFrame:
    """单张表的完整清洗流程。"""
    df = df.copy()

    if NORMALIZE_HEADERS:
        df.columns = normalize_headers(df.columns)

    if STRIP_TEXT:
        df = strip_text(df)

    df = replace_null_tokens(df)

    if DROP_EMPTY_ROWS:
        before = len(df)
        df = df.dropna(how="all")
        stats["空行"] += before - len(df)

    if DROP_EMPTY_COLS:
        before = len(df.columns)
        df = df.dropna(axis=1, how="all")
        stats["空列"] += before - len(df.columns)

    if DROP_DUPLICATES:
        before = len(df)
        df = df.drop_duplicates(keep="first")
        stats["重复行"] += before - len(df)

    if TO_NUMBER:
        df = to_number(df, stats)

    if TO_DATE:
        df = to_date(df, stats)

    if FILL_NA is not None and not df.empty:
        df = df.fillna(FILL_NA)

    return df


def safe_sheet_name(name: str, used: set[str]) -> str:
    """工作表名去掉非法字符、截断到 31 字符并保证不重名。"""
    cleaned = "".join(ch for ch in str(name) if ch not in INVALID_SHEET_CHARS)[:31] or "Sheet"
    candidate = cleaned
    index = 1
    while candidate in used:
        suffix = f"_{index}"
        candidate = cleaned[: 31 - len(suffix)] + suffix
        index += 1
    used.add(candidate)
    return candidate


def clean_workbook(path: Path, sheet: str) -> tuple[int, int]:
    """清洗一个工作簿，返回（处理表数，输出行数）。"""
    sheets = pd.read_excel(path, sheet_name=None, header=HEADER_ROW - 1, dtype=object)
    selected = pick_sheets(sheets, sheet, path)

    output = OUTPUT_DIR / f"{path.stem}{OUTPUT_SUFFIX}.xlsx"
    used_names: set[str] = set()
    processed = 0
    total_rows = 0

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, raw in selected.items():
            stats = {"空行": 0, "空列": 0, "重复行": 0, "数字列": 0, "日期列": 0}
            cleaned = clean_sheet(raw, stats)

            if cleaned.empty or cleaned.shape[1] == 0:
                print(f"  [{name}] 清洗后没有内容，跳过")
                continue

            cleaned.to_excel(writer, sheet_name=safe_sheet_name(name, used_names), index=False)
            processed += 1
            total_rows += len(cleaned)
            print(
                f"  [{name}] {len(raw):>5} 行 → {len(cleaned):>5} 行 × {cleaned.shape[1]:>2} 列"
                f" ｜ 空行 {stats['空行']}、空列 {stats['空列']}、重复 {stats['重复行']}、"
                f"转数字 {stats['数字列']} 列、转日期 {stats['日期列']} 列"
            )

    if processed == 0:
        output.unlink(missing_ok=True)
    return processed, total_rows


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Excel 自动清理")
    parser.add_argument("-i", "--input", type=Path, default=None, help=f"文件或文件夹，默认 {INPUT_PATH}")
    parser.add_argument("-o", "--output", type=Path, default=None, help=f"输出文件夹，默认 {OUTPUT_DIR}")
    parser.add_argument("--sheet", type=str, default=None, help=f"工作表：all / first / 表名，默认 {SHEET}")
    args = parser.parse_args()

    input_path: Path = args.input or INPUT_PATH
    output_dir: Path = args.output or OUTPUT_DIR
    sheet: str = args.sheet or SHEET

    if not input_path.exists():
        raise SystemExit(f"路径不存在：{input_path.resolve()}")

    files = collect_files(input_path)
    if not files:
        raise SystemExit(f"没有找到 .xlsx / .xlsm 文件：{input_path.resolve()}")

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"待处理 {len(files)} 个文件 → 输出到 {output_dir.resolve()}")

    done = 0
    total_rows = 0
    for path in files:
        print(f"\n{path.name}")
        try:
            processed, rows = clean_workbook(path, sheet)
        except Exception as exc:  # 单个文件损坏不影响整批
            print(f"  处理失败：{type(exc).__name__}: {exc}")
            continue
        if processed:
            done += 1
            total_rows += rows

    print(f"\n完成：{done} 个文件、{total_rows} 行数据")


if __name__ == "__main__":
    main()
