#!/usr/bin/env python3
"""Generate Vela meeting diagrams as PNG (no HTML)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT
FONT_PATH = "/System/Library/Fonts/Supplemental/Songti.ttc"
if not Path(FONT_PATH).exists():
    FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"

font_manager.fontManager.addfont(FONT_PATH)
FONT = font_manager.FontProperties(fname=FONT_PATH)
FONT_BOLD = font_manager.FontProperties(fname=FONT_PATH, weight="bold")


def fp(size: float, bold: bool = False) -> font_manager.FontProperties:
    p = FONT_BOLD if bold else FONT
    p.set_size(size)
    return p


def wrap(text: str, width: int = 16) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False))


def draw_round_box(ax, x, y, w, h, fc="#fff", ec="#cbd5e1", lw=1.5, radius=0.02, zorder=2):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        transform=ax.transAxes,
        zorder=zorder,
    )
    ax.add_patch(box)
    return box


def draw_arrow(ax, x1, y1, x2, y2, color="#e67e22", style="-|>", lw=1.8):
    arr = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle=style,
        mutation_scale=12,
        linewidth=lw,
        color=color,
        transform=ax.transAxes,
        zorder=3,
    )
    ax.add_patch(arr)


def draw_num(ax, x, y, n: str, color="#1a3a5c"):
    circ = plt.Circle((x, y), 0.012, color=color, transform=ax.transAxes, zorder=5)
    ax.add_patch(circ)
    ax.text(x, y, n, ha="center", va="center", fontproperties=fp(7, True), color="white", zorder=6)


def gen_system_flow():
    fig, ax = plt.subplots(figsize=(16, 10), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("#eef2f6")
    ax.set_facecolor("#eef2f6")

    # Header
    draw_round_box(ax, 0.03, 0.905, 0.94, 0.08, fc="#1a3a5c", ec="#1a3a5c", radius=0.015)
    ax.text(0.5, 0.955, "系统流程与功能总览", ha="center", va="center", fontproperties=fp(22, True), color="white")
    ax.text(
        0.5,
        0.922,
        "泳道图 · 主路径 ①–⑦ · 同一 project_id · 重点技术标注",
        ha="center",
        va="center",
        fontproperties=fp(10),
        color="#dbeafe",
    )

    lanes = [
        ("业务协同层", "#2563eb", 0.74, 0.14),
        ("法务主导层", "#ea580c", 0.56, 0.14),
        ("AI 引擎层", "#7c3aed", 0.36, 0.14),
        ("结果输出层", "#059669", 0.16, 0.14),
    ]

    for label, color, y, h in lanes:
        draw_round_box(ax, 0.03, y, 0.12, h, fc=color, ec=color, radius=0.012)
        ax.text(0.09, y + h / 2, label, ha="center", va="center", fontproperties=fp(11, True), color="white")
        draw_round_box(ax, 0.16, y + 0.01, 0.62, h - 0.02, fc="#f8fafc", ec="#e2e8f0", radius=0.012)

    # Business lane boxes
    biz = [
        ("①", "冷启动", "Playbook 访谈\n行业·风险偏好·模板", 0.18, 0.755, True),
        ("②", "提交材料", "方案·合同·尽调清单\n同一 project_id", 0.34, 0.755, True),
        ("", "补充材料", "打回后重提\n版本留痕", 0.50, 0.755, False),
    ]
    for num, title, sub, x, y, main in biz:
        ec = "#1a3a5c" if main else "#cbd5e1"
        fc = "#fafcff" if main else "#fff"
        draw_round_box(ax, x, y, 0.13, 0.095, fc=fc, ec=ec, lw=2 if main else 1.2)
        if num:
            draw_num(ax, x + 0.015, y + 0.082, num)
        ax.text(x + 0.065, y + 0.068, title, ha="center", va="center", fontproperties=fp(10, True))
        ax.text(x + 0.065, y + 0.035, sub, ha="center", va="center", fontproperties=fp(7.5), color="#64748b")

    draw_arrow(ax, 0.31, 0.802, 0.34, 0.802)
    draw_arrow(ax, 0.47, 0.802, 0.50, 0.802)

    # Legal lane
    legal = [
        ("③", "定范围", "勾选核查项\n阈值 · Top-N", 0.18, 0.575, True),
        ("⑥", "逐条复核", "确认/驳回\n批注·偏好写入", 0.38, 0.575, True),
        ("⑦", "定稿签发", "法务签字\n版本锁定", 0.56, 0.575, True),
    ]
    for num, title, sub, x, y, main in legal:
        draw_round_box(ax, x, y, 0.15, 0.095, fc="#fff7ed" if main else "#fff", ec="#1a3a5c" if main else "#fdba74", lw=2 if main else 1.2)
        draw_num(ax, x + 0.015, y + 0.082, num, color="#ea580c")
        ax.text(x + 0.075, y + 0.068, title, ha="center", va="center", fontproperties=fp(10, True))
        ax.text(x + 0.075, y + 0.035, sub, ha="center", va="center", fontproperties=fp(7.5), color="#64748b")

    draw_arrow(ax, 0.33, 0.622, 0.38, 0.622)
    draw_arrow(ax, 0.53, 0.622, 0.56, 0.622)

    # AI lane
    ai = [
        ("④", "协查包生成", "结构化清单\n检索计划 · Playbook", 0.18, 0.375, True),
        ("⑤", "Gate A 门控", "Top 法条预览\nGrounding · S3 阻断", 0.36, 0.375, True),
        ("", "多源 RAG", "LexML · STF/STJ\nJusbrasil 语料", 0.54, 0.375, True),
    ]
    for num, title, sub, x, y, main in ai:
        draw_round_box(ax, x, y, 0.15, 0.095, fc="#f5f3ff", ec="#7c3aed", lw=2)
        if num:
            draw_num(ax, x + 0.015, y + 0.082, num, color="#7c3aed")
        ax.text(x + 0.075, y + 0.068, title, ha="center", va="center", fontproperties=fp(10, True))
        ax.text(x + 0.075, y + 0.035, sub, ha="center", va="center", fontproperties=fp(7.5), color="#64748b")

    draw_arrow(ax, 0.33, 0.422, 0.36, 0.422, color="#7c3aed")
    draw_arrow(ax, 0.51, 0.422, 0.54, 0.422, color="#7c3aed")

    # Parallel modules
    mods = [
        ("合同审查", "红黄绿条款\nhouse rules", 0.18, 0.285),
        ("尽调核查", "缺项清单\n材料对照", 0.34, 0.285),
        ("项目统摄", "Analyst 汇总\nRed Team 挑错", 0.50, 0.285),
    ]
    for title, sub, x, y in mods:
        draw_round_box(ax, x, y, 0.13, 0.075, fc="#faf5ff", ec="#c4b5fd", lw=1.2)
        ax.text(x + 0.065, y + 0.052, title, ha="center", va="center", fontproperties=fp(9, True))
        ax.text(x + 0.065, y + 0.025, sub, ha="center", va="center", fontproperties=fp(7), color="#64748b")

    ax.text(0.66, 0.33, "并行模块", fontproperties=fp(8, True), color="#7c3aed")

    # Preference loop
    draw_round_box(ax, 0.54, 0.285, 0.22, 0.075, fc="#ede9fe", ec="#7c3aed", lw=1.5, radius=0.012)
    ax.text(0.65, 0.335, "Playbook 偏好闭环", ha="center", fontproperties=fp(9, True), color="#5b21b6")
    ax.text(
        0.65,
        0.305,
        "复核行为 → user_preference\n下次协查自动应用阈值/Top-N",
        ha="center",
        fontproperties=fp(7),
        color="#64748b",
    )

    # Output lane
    outs = [
        ("协查 Word", "双语底稿\nURN 引证链", 0.18, 0.175),
        ("合同表", "issue 清单", 0.33, 0.175),
        ("尽调表", "缺项追踪", 0.44, 0.175),
        ("冲突表", "跨模块标红", 0.55, 0.175),
    ]
    for title, sub, x, y in outs:
        draw_round_box(ax, x, y, 0.10, 0.085, fc="#ecfdf5", ec="#059669", lw=1.5)
        ax.text(x + 0.05, y + 0.058, title, ha="center", fontproperties=fp(9, True))
        ax.text(x + 0.05, y + 0.028, sub, ha="center", fontproperties=fp(7), color="#64748b")

    # Vertical flow hints
    for x in [0.245, 0.43, 0.43]:
        pass
    draw_arrow(ax, 0.245, 0.755, 0.245, 0.67, color="#64748b", style="-|>", lw=1.2)
    draw_arrow(ax, 0.43, 0.575, 0.43, 0.47, color="#64748b", style="-|>", lw=1.2)
    draw_arrow(ax, 0.43, 0.375, 0.43, 0.26, color="#64748b", style="-|>", lw=1.2)

    # Aux lane - regulatory monitoring
    draw_round_box(ax, 0.80, 0.28, 0.17, 0.58, fc="#fff5f5", ec="#ef4444", lw=2, radius=0.015)
    ax.plot([0.80, 0.80], [0.28, 0.86], "--", color="#ef4444", lw=1.5, transform=ax.transAxes)
    ax.plot([0.97, 0.97], [0.28, 0.86], "--", color="#ef4444", lw=1.5, transform=ax.transAxes)
    ax.plot([0.80, 0.97], [0.86, 0.86], "--", color="#ef4444", lw=1.5, transform=ax.transAxes)
    ax.plot([0.80, 0.97], [0.28, 0.28], "--", color="#ef4444", lw=1.5, transform=ax.transAxes)
    ax.text(0.885, 0.815, "法规监测辅线", ha="center", fontproperties=fp(11, True), color="#dc2626")
    aux_steps = [
        "Reg Feed 抓取\nIBAMA·LexML·gov.br",
        "语料 Diff 对比\nLexML 增量同步",
        "影响分析\n核查项·项目清单",
        "工作台自动提醒\n已定稿不 silent 改",
    ]
    ay = 0.72
    for i, step in enumerate(aux_steps):
        draw_round_box(ax, 0.815, ay - i * 0.11, 0.12, 0.085, fc="#fff", ec="#fca5a5", lw=1.2)
        ax.text(0.875, ay - i * 0.11 + 0.042, step, ha="center", va="center", fontproperties=fp(7.2), color="#991b1b")
        if i < len(aux_steps) - 1:
            draw_arrow(ax, 0.875, ay - i * 0.11 - 0.005, 0.875, ay - (i + 1) * 0.11 + 0.09, color="#ef4444", lw=1.2)

    # Dashed link from aux to legal
    draw_arrow(ax, 0.80, 0.62, 0.71, 0.62, color="#ef4444", style="-|>", lw=1.2)
    ax.text(0.745, 0.635, "推送提醒", ha="center", fontproperties=fp(7), color="#dc2626")

    # Footer legend
    draw_round_box(ax, 0.03, 0.03, 0.94, 0.10, fc="#1a3a5c", ec="#1a3a5c", radius=0.012)
    legend = (
        "实线箭头=主流程  |  橙色=法务门控  |  紫色=AI/RAG  |  红色虚线框=法规监测辅线  |  "
        "技术要点：多源 RAG · Grounding URN · Gate A · Playbook 偏好闭环 · 语料 Agent 自动提醒"
    )
    ax.text(0.5, 0.08, legend, ha="center", va="center", fontproperties=fp(8.5), color="#e2e8f0")

    out = OUT_DIR / "vela_system_flow_swimlane.png"
    fig.savefig(out, bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=200)
    plt.close(fig)
    return out


def draw_card(ax, x, y, w, h, num, title, bullets, header_color, border_color, bg_color):
    draw_round_box(ax, x, y, w, h, fc=bg_color, ec=border_color, lw=1.8, radius=0.018)
    circ = plt.Circle((x + 0.018, y + h - 0.025), 0.014, color=header_color, transform=ax.transAxes, zorder=5)
    ax.add_patch(circ)
    ax.text(x + 0.018, y + h - 0.025, num, ha="center", va="center", fontproperties=fp(8, True), color="white", zorder=6)
    ax.text(x + w / 2, y + h - 0.045, title, ha="center", va="center", fontproperties=fp(11, True), color="#0f172a")
    by = y + h - 0.075
    for line in bullets:
        ax.text(x + 0.02, by, f"• {line}", ha="left", va="top", fontproperties=fp(8.2), color="#475569")
        by -= 0.038


def gen_differentiation():
    fig, ax = plt.subplots(figsize=(16, 11), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("#eef2f6")
    ax.set_facecolor("#eef2f6")

    draw_round_box(ax, 0.04, 0.91, 0.92, 0.075, fc="#1a3a5c", ec="#1a3a5c", radius=0.015)
    ax.text(0.5, 0.955, "差异化能力", ha="center", va="center", fontproperties=fp(22, True), color="white")
    ax.text(
        0.5,
        0.925,
        "九大能力 · 三列对齐 · 按「组织交付 → 智能学习 → 监测联动」分组",
        ha="center",
        va="center",
        fontproperties=fp(10),
        color="#dbeafe",
    )

    # Row headers
    rows = [
        ("组织与交付", 0.78, "#2563eb"),
        ("智能与学习", 0.52, "#7c3aed"),
        ("监测与联动", 0.26, "#059669"),
    ]
    for label, y, color in rows:
        draw_round_box(ax, 0.04, y, 0.08, 0.20, fc=color, ec=color, radius=0.012)
        ax.text(0.08, y + 0.10, label, ha="center", va="center", fontproperties=fp(10, True), color="white")

    cards = [
        # row1
        ("01", "项目制工作台", ["一投资项目一工作台", "协查·合同·尽调同上下文"], "#2563eb", "#93c5fd", "#eff6ff", 0.14, 0.78),
        ("02", "Playbook 冷启动", ["访谈固化法域与底线", "上传 house rules 解析"], "#ea580c", "#fdba74", "#fff7ed", 0.38, 0.78),
        ("03", "可引用 · 可签", ["URN + Grounding 校验", "Gate A 通过后 Word 定稿"], "#059669", "#6ee7b7", "#ecfdf5", 0.62, 0.78),
        # row2
        ("04", "Playbook 偏好闭环", ["复核/阈值/Top-N 写入偏好", "下次协查自动沿用习惯"], "#7c3aed", "#c4b5fd", "#f5f3ff", 0.14, 0.52),
        ("05", "统摄 + Red Team", ["Analyst 中性汇总全貌", "Red Team 专挑跨模块矛盾"], "#dc2626", "#fca5a5", "#fef2f2", 0.38, 0.52),
        ("06", "法源常新", ["LexML·STF·Jusbrasil 多源", "语料 Agent 增量维护"], "#0891b2", "#67e8f9", "#ecfeff", 0.62, 0.52),
        # row3
        ("07", "法规更新自动提醒", ["Reg Feed 抓取 gov.br 更新", "Diff 后推送受影响项目/核查项"], "#d97706", "#fcd34d", "#fffbeb", 0.14, 0.26),
        ("08", "多源法条引证链", ["语料 → LexML → 官方门户", "查不到不编，只给入口"], "#0284c7", "#7dd3fc", "#f0f9ff", 0.38, 0.26),
        ("09", "跨模块冲突检测", ["协查·合同·尽调汇入 issue 表", "不一致自动标红与建议"], "#be123c", "#fda4af", "#fff1f2", 0.62, 0.26),
    ]
    cw, ch = 0.22, 0.20
    for num, title, bullets, hc, bc, bg, x, y in cards:
        draw_card(ax, x, y, cw, ch, num, title, bullets, hc, bc, bg)

    # Center hub strip
    draw_round_box(ax, 0.14, 0.66, 0.70, 0.055, fc="#f8fafc", ec="#1a3a5c", lw=2, radius=0.012)
    ax.text(
        0.49,
        0.687,
        "核心定位：可签、可学习、可统摄的巴西出海法务工作台",
        ha="center",
        va="center",
        fontproperties=fp(11, True),
        color="#1a3a5c",
    )

    draw_round_box(ax, 0.04, 0.04, 0.92, 0.08, fc="#f1f5f9", ec="#cbd5e1", lw=1.2, radius=0.012)
    ax.text(
        0.5,
        0.08,
        "交付物：双语 Word · 四类 issue 表 · 审计日志  |  07 法规更新自动提醒：抓取 → Diff → 工作台推送（定稿底稿不自动改写）",
        ha="center",
        va="center",
        fontproperties=fp(8.5),
        color="#64748b",
    )

    out = OUT_DIR / "vela_differentiation.png"
    fig.savefig(out, bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=200)
    plt.close(fig)
    return out


def main():
    p1 = gen_system_flow()
    p2 = gen_differentiation()
    print(p1)
    print(p2)


if __name__ == "__main__":
    main()
