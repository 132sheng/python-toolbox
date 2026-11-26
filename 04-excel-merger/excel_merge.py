#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量合并 Excel：把一个文件夹下所有表格合成一张总表。

用法：
    python excel_merge.py -i ./订单表                    # 合并并输出 合并结果.xlsx
    python excel_merge.py -i ./订单表 -o 汇总.xlsx        # 指定输出文件
    python excel_merge.py -i ./订单表 -s Sheet1          # 只合并指定工作表
    python excel_merge.py -i ./订单表 -r --no-source     # 递归子目录、不加来源列

默认会跳过 ~$ 开头的临时文件和空表；表头不一致时自动取并集，缺的格子留空。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
DEFAULT_OUTPUT_NAME = "合并结果.xlsx"


def collect_files(folder: Path, recursive: bool) -> list[Path]:
    """收集待合并的表格，跳过 Excel 打开时产生的临时文件。"""
    pattern = "**/*" if recursive else "*"
    files = [
        p
        for p in folder.glob(pattern)
        if p.is_file()
        and p.suffix.lower() in EXCEL_SUFFIXES
        and not p.name.startswith("~$")
    ]
    return sorted(files)


def read_table(path: Path, sheet: str | None) -> pd.DataFrame:
    """读取单个表格，统一列名为字符串并去掉首尾空格。"""
    kwargs = {"sheet_name": sheet} if sheet else {"sheet_name": 0}
    df = pd.read_excel(path, **kwargs)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def merge_files(files: list[Path], sheet: str | None, add_source: bool) -> tuple[pd.DataFrame, list[str]]:
    """逐个读取、拼接；返回合并结果和被跳过的文件说明。"""
    frames: list[pd.DataFrame] = []
    skipped: list[str] = []

    for path in files:
        try:
            df = read_table(path, sheet)
        except Exception as exc:  # 单个文件坏了不中断整批
            skipped.append(f"{path.name}（读取失败：{type(exc).__name__}）")
            continue

        if df.empty:
            skipped.append(f"{path.name}（空表）")
            continue

        if add_source:
            df.insert(0, "来源文件", path.name)

        frames.append(df)
        print(f"  已读取 {path.name:<40} {len(df):>6} 行 × {len(df.columns)} 列")

    if not frames:
        return pd.DataFrame(), skipped

    merged = pd.concat(frames, ignore_index=True, sort=False)
    return merged, skipped


def main() -> None:
    if not sys.stdout.isatty():
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="批量合并 Excel 表格")
    parser.add_argument("-i", "--input", type=Path, required=True, help="表格所在文件夹")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出文件名，默认 合并结果.xlsx")
    parser.add_argument("-s", "--sheet", type=str, default=None, help="工作表名，默认取第一个")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归处理子文件夹")
    parser.add_argument("--no-source", action="store_true", help="不添加“来源文件”列")
    args = parser.parse_args()

    folder: Path = args.input
    if not folder.is_dir():
        raise SystemExit(f"文件夹不存在：{folder}")

    output = args.output or folder / DEFAULT_OUTPUT_NAME
    if output.suffix.lower() not in EXCEL_SUFFIXES:
        output = output.with_suffix(".xlsx")

    files = collect_files(folder, args.recursive)
    # 排除输出文件本身，以及上次生成的结果，避免把结果又合并一遍
    files = [
        p for p in files if p.resolve() != output.resolve() and p.name != DEFAULT_OUTPUT_NAME
    ]
    if not files:
        raise SystemExit(f"没有找到 .xlsx 文件：{folder}")

    print(f"找到 {len(files)} 个表格，开始合并……\n")
    merged, skipped = merge_files(files, args.sheet, add_source=not args.no_source)

    if merged.empty:
        raise SystemExit("所有表格都是空的，没有可合并的内容。")

    merged.to_excel(output, index=False)

    print(f"\n合并完成：{len(merged)} 行 × {len(merged.columns)} 列")
    print(f"输出文件：{output.resolve()}")
    if skipped:
        print(f"\n跳过了 {len(skipped)} 个文件：")
        for item in skipped:
            print(f"  - {item}")


if __name__ == "__main__":
    main()