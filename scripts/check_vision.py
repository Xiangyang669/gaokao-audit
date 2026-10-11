"""一次性验证：DeepSeek 的多模态到底能不能用（spec §13 未验证前提①）。

**这个脚本的产物是"结论"，不是代码。** 结论写进 docs/vision-check.md。

跑法： py scripts/check_vision.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gaokao_audit.llm import client  # noqa: E402

ASSETS = ROOT / "assets" / "demo"
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
)

ROWS = [
    ("暨南大学", "201", "612", "18043", "稳"),
    ("华南师范大学", "203", "598", "27615", "稳"),
    ("广东工业大学", "202", "570", "51302", "冲"),
    ("深圳技术大学", "101", "556", "64021", "保"),
]

PROMPT = (
    "这是一张高考志愿填报表的截图。请**逐行**提取表格内容，不要合并、不要遗漏任何一行。\n"
    "只输出 JSON，形如：{\"items\":[{\"seq\":1,\"university_name\":\"\",\"major_group\":\"\","
    "\"min_score\":0,\"min_rank\":0,\"tier\":\"\"}]}\n"
    "其中 min_score / min_rank 是整数，tier 取值为 冲/稳/保 之一。"
)


def make_screenshot(path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font_path = next((f for f in FONT_CANDIDATES if Path(f).is_file()), None)
    if font_path is None:
        raise SystemExit("找不到中文字体，无法生成截图")
    font = ImageFont.truetype(font_path, 22)
    big = ImageFont.truetype(font_path, 26)

    w, h = 900, 90 + 46 * (len(ROWS) + 1)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((24, 22), "广东省 2025 年普通高考志愿表", font=big, fill="black")

    heads = ("院校名称", "专业组", "最低分", "最低位次", "档位")
    xs = (30, 330, 450, 570, 720)
    y = 84
    for x, t in zip(xs, heads):
        d.text((x, y), t, font=font, fill="black")
    d.line((24, y + 32, w - 24, y + 32), fill="black", width=2)
    y += 46
    for r in ROWS:
        for x, t in zip(xs, r):
            d.text((x, y), str(t), font=font, fill="black")
        d.line((24, y + 32, w - 24, y + 32), fill="#cccccc", width=1)
        y += 46

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def main() -> int:
    shot = ASSETS / "probe.png"
    if not shot.is_file():
        make_screenshot(shot)
        print(f"生成了探针截图：{shot}")

    print(f"模型：{client.MODEL_VISION}（base={client.API_BASE}）")
    try:
        raw = client.vision(shot, PROMPT, cache_key=f"vision-probe:{shot.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 调用失败：{type(exc).__name__}: {exc}")
        print("结论：多模态**不可用** —— 输入设计需要改。")
        return 1

    print(f"✅ 收到响应，{len(raw)} 字符")
    print("-" * 60)
    print(raw[:800])
    print("-" * 60)

    ok = False
    try:
        data = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        items = data.get("items", [])
        ok = len(items) == len(ROWS)
        print(f"解析成 JSON：是 ｜ 行数 {len(items)} / 期望 {len(ROWS)}")
    except Exception as exc:  # noqa: BLE001
        print(f"解析成 JSON：否（{type(exc).__name__}）")

    print()
    print("结论：" + ("多模态**可用**，输入设计维持「上传截图」" if ok else
                     "多模态接口通，但**结构化输出不稳** —— Task 2 要做解析容错"))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
