"""生成演示资产：一张志愿表截图 + 一句示例提问 + **真跑出来的**预生成报告。

跑法： py scripts/make_demo.py

⚠️ 预生成报告**必须是真跑出来的**，不能手写 —— 手写的等于造假，
而且演示一旦和真实输出不一致，就失去了"这是真系统"的全部意义。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gaokao_audit import config, db  # noqa: E402
from gaokao_audit.llm import client  # noqa: E402
from gaokao_audit.llm.schemas import Intent  # noqa: E402
from gaokao_audit.models import AuditContext, PlanItem  # noqa: E402
from gaokao_audit.pipeline import flow, parse  # noqa: E402

ASSETS = ROOT / "assets" / "demo"
SHOT = ASSETS / "screenshot.png"
REPORT = ASSETS / "report.md"
QUESTION = "我这表稳不稳，会不会滑档？"

CAND_RANK = 20000
CATEGORY = "物理类"
YEAR = 2025

FONT_CANDIDATES = (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf")


def pick_rows(conn, n=12):
    """从真实库里挑 n 条：大部分是考生够得着的（干净的），另挑 1 条够不着的（用来埋错）。"""
    reachable = conn.execute(
        "select university_name, major_group, min_score, min_rank from admission_line "
        "where year=? and category=? and min_rank is not null and min_rank >= ? "
        "order by min_rank desc limit ?",
        (YEAR, CATEGORY, CAND_RANK, n - 1),
    ).fetchall()
    unreachable = conn.execute(
        "select university_name, major_group, min_score, min_rank from admission_line "
        "where year=? and category=? and min_rank is not null and min_rank < ? "
        "order by min_rank desc limit 1",
        (YEAR, CATEGORY, CAND_RANK),
    ).fetchone()
    return [tuple(r) for r in reachable], tuple(unreachable) if unreachable else None


def draw(rows, path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font_path = next((f for f in FONT_CANDIDATES if Path(f).is_file()), None)
    font = ImageFont.truetype(font_path, 20)
    big = ImageFont.truetype(font_path, 24)

    head = ("院校名称", "专业组", "最低分", "最低位次", "档位")
    xs = (30, 330, 450, 580, 740)
    w, h = 900, 96 + 40 * (len(rows) + 1)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((24, 20), "广东省 2025 年普通高考志愿表", font=big, fill="black")
    y = 70
    for x, t in zip(xs, head):
        d.text((x, y), t, font=font, fill="black")
    d.line((24, y + 28, w - 24, y + 28), fill="black", width=2)
    y += 40
    for r in rows:
        for x, t in zip(xs, r):
            d.text((x, y), str(t), font=font, fill="black")
        d.line((24, y + 28, w - 24, y + 28), fill="#dddddd", width=1)
        y += 40
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def main() -> int:
    conn = db.connect(config.DB_PATH)
    good, bad = pick_rows(conn)
    if bad is None:
        print("找不到'够不着'的组，无法埋错")
        return 1

    # 最后一条：考生够不着，却标成「稳」—— 这正是实测里翻车的那个形态
    rows = [(s, g, sc, rk, "稳") for (s, g, sc, rk) in good] + [
        (bad[0], bad[1], bad[2], bad[3], "稳")
    ]
    draw(rows, SHOT)
    print(f"生成截图：{SHOT}（{len(rows)} 行；最后一行故意标错档位）")

    # 真解析一次（首次会真调模型，之后走缓存）
    parsed = parse.parse_screenshot(SHOT)
    print(f"解析：读到 {parsed.raw_item_count} 条，期望 {len(rows)} 条，degraded={parsed.degraded}")
    if parsed.raw_item_count != len(rows):
        print(f"⚠️ 行数对不上（{parsed.raw_item_count} vs {len(rows)}）—— 这本身就是有价值的信息，先记下来")

    ctx = AuditContext(year=YEAR, category=CATEGORY, candidate_rank=CAND_RANK,
                       candidate_subjects=("物理", "化学", "生物"))
    items = [PlanItem(seq=p.seq, university_name=p.university_name, major_group=p.major_group,
                      claimed_min_score=p.claimed_min_score, claimed_rank=p.claimed_rank,
                      subject_req=None, tier=p.tier or "稳") for p in parsed.items]

    rep = flow.build(items, QUESTION, conn, ctx)
    print(f"审计：intent={rep.intent.value} findings={len(rep.findings)} outcomes={rep.outcomes}")
    for f in rep.findings:
        print(f"   第{f.seq}条 {f.kind}: {f.detail[:60]}")

    REPORT.write_text(
        f"""# 演示报告（真跑产出，非手写）

- 生成方式：`py scripts/make_demo.py`
- 输入：`assets/demo/screenshot.png`（{len(rows)} 行）+ 提问「{QUESTION}」
- 模型：{client.MODEL_TEXT} ｜ 意图分类：{rep.intent.value}
- 跑过的检查：{'、'.join(rep.outcomes)}
- 降级：{rep.degraded or '无'}

## 报告正文

{rep.narrative}

## 结构化发现（{len(rep.findings)} 条）

{chr(10).join(f"- **第 {f.seq} 条 · {f.kind}**：{f.detail}（证据：{f.evidence}）" for f in rep.findings) or '（无）'}
""",
        encoding="utf-8",
    )
    print(f"写入报告：{REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
