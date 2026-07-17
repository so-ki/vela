#!/usr/bin/env python3
"""Generate Vela Golden Path fishbone (Ishikawa) diagram as PNG."""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT
FONT_PATH = "/System/Library/Fonts/Supplemental/Songti.ttc"
if not Path(FONT_PATH).exists():
    FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"

font_manager.fontManager.addfont(FONT_PATH)
FONT = font_manager.FontProperties(fname=FONT_PATH)
FONT_BOLD = font_manager.FontProperties(fname=FONT_PATH, weight="bold")

# Colors
C_HEAD = "#1a3a5c"
C_SPINE = "#334155"
C_BIZ = "#2563eb"
C_LEGAL = "#ea580c"
C_AI = "#7c3aed"
C_OUT = "#059669"
C_AUX = "#dc2626"
C_RULE = "#0284c7"
C_EVID = "#0891b2"
C_GATE = "#d97706"
C_BG = "#F5F7FA"


def fp(size: float, bold: bool = False) -> font_manager.FontProperties:
    p = FONT_BOLD if bold else FONT
    p.set_size(size)
    return p


def wrap(text: str, width: int = 14) -> str:
    lines: list[str] = []
    for part in text.split("\n"):
        lines.extend(textwrap.wrap(part, width=width, break_long_words=False) or [""])
    return "\n".join(lines)


def draw_bone(
    ax,
    sx: float,
    sy: float,
    ex: float,
    ey: float,
    color: str = C_SPINE,
    lw: float = 1.6,
):
    ax.plot([sx, ex], [sy, ey], color=color, lw=lw, solid_capstyle="round", zorder=2)


def draw_label_box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    bullets: list[str],
    title_color: str,
    bg: str = "#ffffff",
    ec: str = "#cbd5e1",
    title_size: float = 8.5,
    bullet_size: float = 6.8,
    ha: str = "left",
):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.004,rounding_size=0.008",
        linewidth=1.2,
        edgecolor=ec,
        facecolor=bg,
        transform=ax.transAxes,
        zorder=4,
    )
    ax.add_patch(box)
    tx = x + 0.008 if ha == "left" else x + w / 2
    ax.text(
        tx,
        y + h - 0.012,
        title,
        ha=ha,
        va="top",
        fontproperties=fp(title_size, True),
        color=title_color,
        transform=ax.transAxes,
        zorder=5,
    )
    body = "\n".join(f"· {b}" for b in bullets)
    ax.text(
        tx,
        y + h - 0.028,
        body,
        ha=ha,
        va="top",
        fontproperties=fp(bullet_size),
        color="#334155",
        linespacing=1.35,
        transform=ax.transAxes,
        zorder=5,
    )


def draw_head(ax, x: float, y: float, w: float, h: float):
    pts = [(x, y + h / 2), (x + w, y + h), (x + w, y)]
    poly = Polygon(pts, closed=True, facecolor=C_HEAD, edgecolor=C_HEAD, transform=ax.transAxes, zorder=6)
    ax.add_patch(poly)
    ax.text(
        x + w * 0.55,
        y + h * 0.62,
        "Vela 协查",
        ha="center",
        va="center",
        fontproperties=fp(14, True),
        color="white",
        transform=ax.transAxes,
        zorder=7,
    )
    ax.text(
        x + w * 0.55,
        y + h * 0.38,
        "Golden Path\n可信交付",
        ha="center",
        va="center",
        fontproperties=fp(11, True),
        color="#dbeafe",
        transform=ax.transAxes,
        zorder=7,
    )


def gen_fishbone():
    fig, ax = plt.subplots(figsize=(28, 18), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)

    # Header bar
    hdr = FancyBboxPatch(
        (0.02, 0.955),
        0.96,
        0.038,
        boxstyle="round,pad=0.004,rounding_size=0.006",
        facecolor=C_HEAD,
        edgecolor=C_HEAD,
        transform=ax.transAxes,
        zorder=1,
    )
    ax.add_patch(hdr)
    ax.text(
        0.5,
        0.974,
        "Vela 出海法务台 · Golden Path 鱼骨图（主流程 × 辅线 × 三层架构）",
        ha="center",
        va="center",
        fontproperties=fp(16, True),
        color="white",
        transform=ax.transAxes,
    )

    # Main spine
    spine_y = 0.50
    spine_x0, spine_x1 = 0.08, 0.78
    ax.plot([spine_x0, spine_x1], [spine_y, spine_y], color=C_SPINE, lw=3.5, zorder=2)
    draw_head(ax, 0.78, spine_y - 0.055, 0.17, 0.11)

    # Spine step markers
    steps = [
        (0.12, "①", "场景输入", C_BIZ),
        (0.24, "②", "确认范围", C_LEGAL),
        (0.36, "③", "检索分级", C_AI),
        (0.48, "④", "双语简报", C_AI),
        (0.60, "⑤", "法务复核", C_LEGAL),
        (0.72, "⑥", "Word导出", C_OUT),
    ]
    for sx, num, label, col in steps:
        circ = plt.Circle((sx, spine_y), 0.014, color=col, transform=ax.transAxes, zorder=5)
        ax.add_patch(circ)
        ax.text(sx, spine_y, num, ha="center", va="center", fontproperties=fp(7, True), color="white", zorder=6)
        ax.text(
            sx,
            spine_y - 0.028,
            label,
            ha="center",
            va="top",
            fontproperties=fp(7.5, True),
            color=col,
            transform=ax.transAxes,
            zorder=6,
        )

    # ── TOP bones (odd steps + layers) ─────────────────────────────────────

    # ① 场景输入
    draw_bone(ax, 0.12, spine_y, 0.10, 0.78, C_BIZ)
    draw_bone(ax, 0.10, 0.78, 0.06, 0.84, C_BIZ, 1.0)
    draw_bone(ax, 0.10, 0.78, 0.14, 0.84, C_BIZ, 1.0)
    draw_bone(ax, 0.10, 0.78, 0.06, 0.72, C_BIZ, 1.0)
    draw_bone(ax, 0.10, 0.78, 0.14, 0.72, C_BIZ, 1.0)
    draw_label_box(
        ax,
        0.02,
        0.855,
        0.17,
        0.095,
        "① 场景输入 · 投资/出海业务部",
        [
            "规则包自动匹配（目的地→标准模板）",
            "文档抽取→协查材料核对表",
            "材料核对/事实验真（待核对防幻觉）",
            "多文件合并与冲突检测",
            "Playbook 可选（记习惯不改模板）",
        ],
        C_BIZ,
        bg="#eff6ff",
        ec="#93c5fd",
    )
    ax.text(
        0.105,
        0.848,
        "产出：结构化项目事实 + 原文件归档（无法条清单）",
        ha="center",
        va="top",
        fontproperties=fp(6.5, True),
        color="#1d4ed8",
        transform=ax.transAxes,
    )

    # ③ 检索与风险分级
    draw_bone(ax, 0.36, spine_y, 0.34, 0.80, C_AI)
    draw_bone(ax, 0.34, 0.80, 0.28, 0.86, C_AI, 1.0)
    draw_bone(ax, 0.34, 0.80, 0.40, 0.86, C_AI, 1.0)
    draw_bone(ax, 0.34, 0.80, 0.28, 0.74, C_AI, 1.0)
    draw_bone(ax, 0.34, 0.80, 0.40, 0.74, C_AI, 1.0)
    draw_label_box(
        ax,
        0.23,
        0.868,
        0.21,
        0.088,
        "③ 检索与风险分级 · 系统自动→法务审核",
        [
            "规则引擎/清单生成（非 LLM 编题）",
            "RAG + 确定性关键词维度加权",
            "Brazil Connector / 外链降级（查不到不编）",
            "Grounding 溯源 + 匹配度 0-100",
            "S1/S2/S3 分级 · Investigation Agent 流水线",
        ],
        C_AI,
        bg="#f5f3ff",
        ec="#c4b5fd",
    )
    ax.text(
        0.34,
        0.858,
        "原则：无可靠依据→扩检/S3/外链，不捏造法条",
        ha="center",
        va="top",
        fontproperties=fp(6.5, True),
        color="#6d28d9",
        transform=ax.transAxes,
    )

    # ⑤ 法务人工复核
    draw_bone(ax, 0.60, spine_y, 0.58, 0.80, C_LEGAL)
    draw_label_box(
        ax,
        0.50,
        0.865,
        0.18,
        0.085,
        "⑤ 法务人工复核 · 法务部",
        [
            "复核工作台：通过/驳回/批注/外聘标记",
            "Gate A 锁：要件不齐→不能逐条复核",
            "业务反馈视图 · 退回业务修订",
            "Playbook 偏差日志 · 个人偏好学习",
            "定稿 v1.x · Audit Bundle 审计包",
        ],
        C_LEGAL,
        bg="#fff7ed",
        ec="#fdba74",
    )
    ax.text(
        0.59,
        0.858,
        "原则：对外效力由法务控制，系统不替律师签字",
        ha="center",
        va="top",
        fontproperties=fp(6.5, True),
        color="#c2410c",
        transform=ax.transAxes,
    )

    # ── BOTTOM bones (even steps) ───────────────────────────────────────────

    # ② 法务确认范围
    draw_bone(ax, 0.24, spine_y, 0.22, 0.22, C_LEGAL)
    draw_label_box(
        ax,
        0.12,
        0.08,
        0.20,
        0.115,
        "② 法务确认范围 · 法务部",
        [
            "Gate A 材料门控（维度下构成要件齐否）",
            "协查维度确认（法务定，非 AI 自动开查）",
            "匹配度阈值默认 70 分 · Top-N 法条条数",
            "Playbook 建议项可选并入清单",
            "定范围与门槛；不出 Word 定稿",
        ],
        C_LEGAL,
        bg="#fff7ed",
        ec="#fdba74",
    )
    ax.text(
        0.22,
        0.075,
        "Gate A 不过 → 打回业务补材料",
        ha="center",
        va="top",
        fontproperties=fp(6.5, True),
        color="#c2410c",
        transform=ax.transAxes,
    )

    # ④ 生成双语简报
    draw_bone(ax, 0.48, spine_y, 0.46, 0.22, C_AI)
    draw_label_box(
        ax,
        0.36,
        0.08,
        0.20,
        0.115,
        "④ 生成双语简报 · 系统",
        [
            "中葡对照条目：要点/法条/匹配度/溯源",
            "LLM 润色可选（不改结论来源）",
            "免责声明：协查辅助，非正式法律意见",
            "Verification 3 pass 自检（见右下说明）",
            "Gate A 聚合协查后：缺要件→锁定复核",
        ],
        C_AI,
        bg="#f5f3ff",
        ec="#c4b5fd",
    )
    ax.text(
        0.46,
        0.075,
        "产出：协查草稿包（清单+法条+简报）→ 法务复核",
        ha="center",
        va="top",
        fontproperties=fp(6.5, True),
        color="#6d28d9",
        transform=ax.transAxes,
    )

    # ⑥ 导出 Word
    draw_bone(ax, 0.72, spine_y, 0.70, 0.22, C_OUT)
    draw_label_box(
        ax,
        0.60,
        0.08,
        0.16,
        0.095,
        "⑥ 导出 Word 协查底稿",
        [
            "Word 模板：项目/子行业/双语/引用/结论",
            "导出门禁：必须先定稿",
            "PDF / 审计包可选存档",
        ],
        C_OUT,
        bg="#ecfdf5",
        ec="#6ee7b7",
    )

    # ── LEFT: 三层架构 ───────────────────────────────────────────────────────
    layer_x = 0.02
    layers = [
        (
            0.62,
            "规则层 · 查什么",
            C_RULE,
            "#f0f9ff",
            "#7dd3fc",
            [
                "规则包（标准模板）：题/触发/维度/Gate A 字段",
                "子行业识别：光伏/储能/客车→题量不同",
                "Playbook：默认维度/建议题/阈值风格",
                "驳回闭环→建议收紧触发（人工改模板）",
            ],
        ),
        (
            0.42,
            "证据层 · 依据从哪来",
            C_EVID,
            "#ecfeff",
            "#67e8f9",
            [
                "精选语料库 ~70 条 MVP + 维度/题绑定",
                "RAG Top 命中 + LexML/Planalto 外链核对",
                "按需拉官方页验 URN（非全库实时镜像）",
                "Reg Feed + 语料 Agent：半自动、人审入库",
            ],
        ),
        (
            0.22,
            "门控层 · 能不能定稿",
            C_GATE,
            "#fffbeb",
            "#fcd34d",
            [
                "Gate A：材料构成要件够不够开查/复核",
                "70 分匹配度 · S1/S2/S3 · Grounding",
                "材料 fact 验真 · Verification 3 pass",
                "法务逐条复核 + 定稿 = 最终能不能签",
                "LLM 边界：仅润色/抽取，不新增法条结论",
            ],
        ),
    ]
    for ly, title, tc, bg, ec, bullets in layers:
        draw_bone(ax, spine_x0, spine_y, layer_x + 0.04, ly, tc, 2.0)
        draw_label_box(ax, layer_x, ly - 0.04, 0.19, 0.11, title, bullets, tc, bg=bg, ec=ec)

    ax.text(
        0.115,
        0.78,
        "三层架构\n（贯穿全程）",
        ha="center",
        va="center",
        fontproperties=fp(9, True),
        color=C_HEAD,
        transform=ax.transAxes,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#e2e8f0", edgecolor=C_HEAD, lw=1.2),
    )

    # ── RIGHT: 辅线 法规监测 ─────────────────────────────────────────────────
    aux_x0, aux_y0, aux_w, aux_h = 0.84, 0.28, 0.14, 0.62
    aux_box = FancyBboxPatch(
        (aux_x0, aux_y0),
        aux_w,
        aux_h,
        boxstyle="round,pad=0.006,rounding_size=0.01",
        linewidth=2.0,
        edgecolor=C_AUX,
        facecolor="#fef2f2",
        linestyle="--",
        transform=ax.transAxes,
        zorder=3,
    )
    ax.add_patch(aux_box)
    ax.text(
        aux_x0 + aux_w / 2,
        aux_y0 + aux_h - 0.025,
        "辅线 · 法规监测 Agent",
        ha="center",
        va="top",
        fontproperties=fp(10, True),
        color=C_AUX,
        transform=ax.transAxes,
    )
    ax.text(
        aux_x0 + aux_w / 2,
        aux_y0 + aux_h - 0.055,
        "（并行，不阻塞 ①-⑥）",
        ha="center",
        va="top",
        fontproperties=fp(7.5),
        color="#991b1b",
        transform=ax.transAxes,
    )
    aux_items = [
        "Regulatory Feed：探测官方法规源变化",
        "语料 diff：本地库 vs 快照",
        "LexML 同步：已入库 URN 拉最新正文",
        "语料维护 Agent → 待人工审核队列",
        "项目影响分析：进行中/已定稿项目",
        "法务通知：建议增量协查/重跑",
        "定稿保护：不改已导出 Word，须重跑",
    ]
    ax.text(
        aux_x0 + 0.012,
        aux_y0 + aux_h - 0.085,
        "\n".join(f"· {i}" for i in aux_items),
        ha="left",
        va="top",
        fontproperties=fp(7.2),
        color="#334155",
        linespacing=1.4,
        transform=ax.transAxes,
    )
    ax.text(
        aux_x0 + aux_w / 2,
        aux_y0 + 0.012,
        "法规在变→提醒+排队+建议\n人不审不动库、不改定稿",
        ha="center",
        va="bottom",
        fontproperties=fp(7, True),
        color=C_AUX,
        transform=ax.transAxes,
    )
    # Dashed link to evidence layer
    ax.plot(
        [0.21, aux_x0],
        [0.47, 0.55],
        color=C_AUX,
        lw=1.5,
        linestyle="--",
        zorder=2,
    )
    ax.text(0.52, 0.56, "影响证据层是否过时", ha="center", fontproperties=fp(6.5), color=C_AUX, transform=ax.transAxes)

    # ── Verification 3 pass detail box ────────────────────────────────────────
    vbox = FancyBboxPatch(
        (0.34, 0.198),
        0.30,
        0.078,
        boxstyle="round,pad=0.004,rounding_size=0.008",
        facecolor="#fefce8",
        edgecolor="#ca8a04",
        lw=1.2,
        transform=ax.transAxes,
        zorder=4,
    )
    ax.add_patch(vbox)
    ax.text(
        0.50,
        0.272,
        "Verification 三 Pass（Lavern 简化 · 不用 AI 拍板）",
        ha="center",
        va="top",
        fontproperties=fp(8, True),
        color="#a16207",
        transform=ax.transAxes,
    )
    ax.text(
        0.50,
        0.248,
        "① 引证准确性：溯源通过率 · 已通过但引证待核\n"
        "② 检索完整性：是否还有完全零命中核查题\n"
        "③ 高风险门控：高优先级却被阻断的题\n"
        "未全过 → 建议法务先处理，不静默当 OK",
        ha="center",
        va="top",
        fontproperties=fp(7),
        color="#713f12",
        linespacing=1.35,
        transform=ax.transAxes,
    )

    # ── Legend footer ─────────────────────────────────────────────────────────
    leg = FancyBboxPatch(
        (0.02, 0.01),
        0.96,
        0.055,
        boxstyle="round,pad=0.004,rounding_size=0.008",
        facecolor="#f1f5f9",
        edgecolor="#cbd5e1",
        transform=ax.transAxes,
        zorder=1,
    )
    ax.add_patch(leg)
    legend_items = [
        (C_BIZ, "业务协同"),
        (C_LEGAL, "法务主导"),
        (C_AI, "AI 引擎"),
        (C_OUT, "结果输出"),
        (C_AUX, "辅线监测"),
        (C_RULE, "规则层"),
        (C_EVID, "证据层"),
        (C_GATE, "门控层"),
    ]
    lx = 0.04
    for col, label in legend_items:
        ax.add_patch(
            FancyBboxPatch(
                (lx, 0.028),
                0.018,
                0.018,
                boxstyle="round,pad=0",
                facecolor=col,
                edgecolor=col,
                transform=ax.transAxes,
            )
        )
        ax.text(lx + 0.022, 0.037, label, va="center", fontproperties=fp(7.5), color="#475569", transform=ax.transAxes)
        lx += 0.105
    ax.text(
        0.5,
        0.037,
        "交付物：结构化事实 · 核查清单 · 双语简报 · 协查底稿 · 审计包  |  数据源：LexML · STF/STJ · Jusbrasil · Planalto",
        ha="center",
        va="center",
        fontproperties=fp(7.5),
        color="#64748b",
        transform=ax.transAxes,
    )

    out = OUT_DIR / "vela_golden_path_fishbone.png"
    out2x = OUT_DIR / "vela_golden_path_fishbone@2x.png"
    fig.savefig(out, bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=200)
    fig.savefig(out2x, bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=400)
    plt.close(fig)
    return out, out2x


def main():
    p1, p2 = gen_fishbone()
    print(p1)
    print(p2)


if __name__ == "__main__":
    main()
