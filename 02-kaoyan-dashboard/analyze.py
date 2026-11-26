#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""考研院校复试分数线分析：数据清洗 → 统计 → 可视化看板。

用法：
    python analyze.py                        # 生成 dashboard.html
    python analyze.py --top 15               # 只看前 15 所
    python analyze.py --year 2024            # 只分析某一年
    python analyze.py --school 清华大学       # 查单个学校

数据字段：学校, 专业, 代码, 招生院系, 总分, 政治, 外语, 专业课一, 专业课二, 录取年份
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Page
from pyecharts.globals import CurrentConfig, ThemeType

SCORE_COLUMNS = ["总分", "政治", "外语", "专业课一", "专业课二"]
BASE_DIR = Path(__file__).parent
DEFAULT_CSV = BASE_DIR / "data" / "kaoyan_scores.csv"
DEFAULT_OUT = BASE_DIR / "dashboard.html"

# 本地带了 echarts.min.js 就离线渲染，否则回退到官方 CDN
if (BASE_DIR / "assets" / "echarts.min.js").exists():
    CurrentConfig.ONLINE_HOST = "./assets/"


def load_data(csv_path: Path) -> pd.DataFrame:
    """读取并清洗分数线数据。"""
    df = pd.read_csv(csv_path, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]

    for col in SCORE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["录取年份"] = pd.to_numeric(df["录取年份"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["学校", "专业", "总分", "录取年份"])

    df["学校"] = df["学校"].astype(str).str.strip()
    df["专业"] = df["专业"].astype(str).str.strip()
    return df


def school_summary(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """按院校聚合：平均分、最高分、覆盖专业数。"""
    summary = (
        df.groupby("学校")
        .agg(
            平均总分=("总分", "mean"),
            最高总分=("总分", "max"),
            最低总分=("总分", "min"),
            专业数=("专业", "nunique"),
            记录数=("总分", "size"),
        )
        .sort_values("平均总分", ascending=False)
        .head(top_n)
        .round(1)
        .reset_index()
    )
    return summary


def year_trend(df: pd.DataFrame) -> pd.DataFrame:
    """按年份聚合，观察分数线走势。"""
    trend = (
        df.groupby("录取年份")
        .agg(平均总分=("总分", "mean"), 样本数=("总分", "size"))
        .reset_index()
    )
    trend["平均总分"] = trend["平均总分"].round(1)
    return trend


def bar_top_schools(summary: pd.DataFrame) -> Bar:
    """横向柱状图：平均总分 TOP N。"""
    schools = summary["学校"].tolist()[::-1]
    scores = summary["平均总分"].tolist()[::-1]

    chart = (
        Bar(init_opts=opts.InitOpts(width="1000px", height="560px", theme=ThemeType.LIGHT))
        .add_xaxis(schools)
        .add_yaxis(
            "平均总分",
            scores,
            label_opts=opts.LabelOpts(is_show=True, position="right"),
            itemstyle_opts=opts.ItemStyleOpts(color="#3b82f6"),
        )
        .reversal_axis()
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="院校平均复试总分 TOP",
                subtitle="按全部专业与年份求均值",
                pos_left="center",
            ),
            xaxis_opts=opts.AxisOpts(name="分数", min_=0),
            yaxis_opts=opts.AxisOpts(name="院校"),
            toolbox_opts=opts.ToolboxOpts(is_show=True),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )
    return chart


def line_trend(trend: pd.DataFrame) -> Line:
    """折线图：逐年平均总分。"""
    chart = (
        Line(init_opts=opts.InitOpts(width="1000px", height="380px", theme=ThemeType.LIGHT))
        .add_xaxis([str(y) for y in trend["录取年份"]])
        .add_yaxis(
            "平均总分",
            trend["平均总分"].tolist(),
            is_smooth=True,
            is_symbol_show=True,
            symbol_size=8,
            label_opts=opts.LabelOpts(is_show=True),
            linestyle_opts=opts.LineStyleOpts(width=3),
            itemstyle_opts=opts.ItemStyleOpts(color="#f59e0b"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="分数线年度趋势", subtitle="各年份全部院校专业的平均总分", pos_left="center"
            ),
            xaxis_opts=opts.AxisOpts(name="年份", type_="category", boundary_gap=False),
            yaxis_opts=opts.AxisOpts(name="平均总分"),
            legend_opts=opts.LegendOpts(is_show=False),
            toolbox_opts=opts.ToolboxOpts(is_show=True),
        )
    )
    return chart


def build_dashboard(summary: pd.DataFrame, trend: pd.DataFrame, out_path: Path) -> Path:
    """把图表拼成一页看板并保存。"""
    page = Page(layout=Page.SimplePageLayout, page_title="考研分数线看板")
    page.add(bar_top_schools(summary), line_trend(trend))
    page.render(str(out_path))
    return out_path


def main() -> None:
    # 输出被管道重定向时统一用 UTF-8，避免 Windows 控制台中文乱码
    if not sys.stdout.isatty():
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="考研院校分数线分析")
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV, help="输入 CSV 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="输出 HTML 路径")
    parser.add_argument("--top", type=int, default=12, help="展示前 N 所院校")
    parser.add_argument("--year", type=int, default=None, help="只分析指定年份")
    parser.add_argument("--school", type=str, default=None, help="查询单个院校")
    args = parser.parse_args()

    df = load_data(args.input)
    scope = f"{df['录取年份'].min()}–{df['录取年份'].max()}"

    if args.year:
        df = df[df["录取年份"] == args.year]
        scope = str(args.year)
    if df.empty:
        raise SystemExit(f"没有匹配的数据（年份={args.year}）")

    if args.school:
        detail = df[df["学校"] == args.school].sort_values(["录取年份", "总分"])
        if detail.empty:
            raise SystemExit(f"未找到院校：{args.school}")
        print(f"\n=== {args.school} 分数线明细（{len(detail)} 条）===")
        print(detail[["录取年份", "专业", "总分", "政治", "外语"]].to_string(index=False))
        print(f"\n平均总分：{detail['总分'].mean():.1f}")
        return

    summary = school_summary(df, args.top)
    trend = year_trend(df)

    print(f"\n数据范围：{scope}，共 {len(df)} 条记录，{df['学校'].nunique()} 所院校")
    print(f"\n=== 平均总分 TOP {len(summary)} ===")
    print(summary.to_string(index=False))
    print("\n=== 年度趋势 ===")
    print(trend.to_string(index=False))

    out = build_dashboard(summary, trend, args.output)
    print(f"\n看板已生成：{out.resolve()}")


if __name__ == "__main__":
    main()