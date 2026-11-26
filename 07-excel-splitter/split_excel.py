#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量拆分 Excel：把一张总表按某列拆成多个文件，或按行数切块。

用法：
    python split_excel.py -i 总表.xlsx -c 客户            # 按“客户”列拆
    python split_excel.py -i 总表.xlsx -c 地区 -o 输出目录  # 指定输出目录
    python split_excel.py -i 总表.xlsx --rows 500         # 每 500 行一个文件
    python split_excel.py -i 总表.xlsx -c 部门 --no-index  # 不带行号

文件名自动按单元格内容命名，非法字符会替换；空值行单独归到「未填写」。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
ILLEGAL = r'[\\/:*?"<>|\r\n\t]'


def safe_name(value: object, maxlen: int = 40) -> str:
    """把单元格内容变成合法文件名。"""
    text = str(value).strip()
    text = re.sub(ILLEGAL, "_", text)
    text = text.strip(". ")
    text = re.sub(r"\s+", " ", text)
    return (text[:maxlen] or "未填写")


def load(path: Path, sheet: str | None) -> pd.DataFrame:
    kwargs = {"sheet_name": sheet} if sheet else {"sheet_name": 0}
    df = pd.read_excel(path, **kwargs)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def split_by_column(df: pd.DataFrame, column: str, out_dir: Path, with_index: bool) -> list[tuple[str, int]]:
    """按列值分组写出，返回 (文件名, 行数) 列表。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, int]] = []

    for value, group in df.groupby(column, dropna=False, sort=True):
        name = safe_name(value)
        target = out_dir / f"{name}.xlsx"

        # 同名冲突加序号
        i = 2
        while target.exists():
            target = out_dir / f"{name}_{i}.xlsx"
            i += 1

        data = group.copy()
        if not with_index:
            data = data.drop(columns=[column], errors="ignore")
        data.to_excel(target, index=False)
        written.append((target.name, len(data)))

    return written


def split_by_rows(df: pd.DataFrame, size: int, out_dir: Path, stem: str) -> list[tuple[str, int]]:
    """按固定行数切块。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, int]] = []
    total = len(df)

    for idx, start in enumerate(range(0, total, size), 1):
        chunk = df.iloc[start:start + size]
        target = out_dir / f"{stem}_{idx:02d}.xlsx"
        chunk.to_excel(target, index=False)
        written.append((target.name, len(chunk)))

    return written


def main() -> None:
    if not sys.stdout.isatty():
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="批量拆分 Excel")
    parser.add_argument("-i", "--input", type=Path, required=True, help="要拆分的工作簿")
    parser.add_argument("-c", "--column", type=str, default=None, help="按哪一列拆分")
    parser.add_argument("--rows", type=int, default=None, help="按行数拆分，例如 500")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出目录，默认 源文件_拆分")
    parser.add_argument("-s", "--sheet", type=str, default=None, help="工作表名，默认第一个")
    parser.add_argument("--no-index", action="store_true", help="拆出来的文件不再保留拆分类")
    args = parser.parse_args()

    src: Path = args.input
    if not src.is_file():
        raise SystemExit(f"文件不存在：{src}")
    if not args.column and not args.rows:
        raise SystemExit("请指定 -c 列名 或 --rows 行数，二选一")

    df = load(src, args.sheet)
    if df.empty:
        raise SystemExit("表格是空的，没有可拆分的内容。")

    out_dir = args.output or src.with_name(f"{src.stem}_拆分")
    print(f"读取 {src.name}（{len(df)} 行 × {len(df.columns)} 列）\n")

    if args.rows:
        print(f"按行数拆分，每 {args.rows} 行一个文件……\n")
        written = split_by_rows(df, args.rows, out_dir, src.stem)
    else:
        if args.column not in df.columns:
            cols = "、".join(map(str, df.columns))
            raise SystemExit(f"列「{args.column}」不存在。可用的列有：{cols}")
        print(f"按「{args.column}」拆分……\n")
        written = split_by_column(df, args.column, out_dir, with_index=not args.no_index)

    for name, rows in written[:30]:
        print(f"  {name:<28} {rows:>6} 行")
    if len(written) > 30:
        print(f"  …… 还有 {len(written) - 30} 个文件")

    print(f"\n拆分完成：{len(written)} 个文件")
    print(f"输出目录：{out_dir.resolve()}")


if __name__ == "__main__":
    main()