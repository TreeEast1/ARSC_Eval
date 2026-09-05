"""Export a small documentary gallery for the public BDD-OIA dataset page.

The full last-frame archive stays untracked. This script copies a few
downscaled, captioned frames so GitHub readers can see the annotation form
without downloading the official release.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = PROJECT_ROOT / "data" / "raw" / "lastframe" / "data"
OUT_DIR = PROJECT_ROOT / "docs" / "dataset" / "examples"

ACTION_NAMES = ["Forward", "Stop", "Left", "Right"]
RATIONALE_NAMES = [
    "green_light",
    "follow",
    "road_clear",
    "red_light",
    "traffic_sign",
    "car",
    "person",
    "rider",
    "other_obstacle",
    "left_lane",
    "left_green_light",
    "left_follow",
    "no_left_lane",
    "left_obstacle",
    "left_solid_line",
    "right_lane",
    "right_green_light",
    "right_follow",
    "no_right_lane",
    "right_obstacle",
    "right_solid_line",
]
ACTION_ZH = {
    "Forward": "前进",
    "Stop": "停止",
    "Left": "左转",
    "Right": "右转",
}
RATIONALE_ZH = {
    "green_light": "绿灯",
    "follow": "跟随前车",
    "road_clear": "前方畅通",
    "red_light": "红灯",
    "traffic_sign": "交通标志",
    "car": "车辆",
    "person": "行人",
    "rider": "骑行者",
    "other_obstacle": "其他障碍",
    "left_lane": "左侧车道",
    "left_green_light": "左转绿灯",
    "left_follow": "左转跟随",
    "no_left_lane": "无左侧车道",
    "left_obstacle": "左侧障碍",
    "left_solid_line": "左侧实线",
    "right_lane": "右侧车道",
    "right_green_light": "右转绿灯",
    "right_follow": "右转跟随",
    "no_right_lane": "无右侧车道",
    "right_obstacle": "右侧障碍",
    "right_solid_line": "右侧实线",
}

# Hand-picked test-split cases that illustrate the label form.
CASES = [
    {
        "file_name": "073873be-32a8b6b8_1.jpg",
        "slug": "01_stop_red_light",
        "title": "案例 1 · 夜间路口停车",
        "note": "单一动作 Stop；理由是红灯，并同时标了骑行者。",
    },
    {
        "file_name": "25e9f9ef-223e3050_3.jpg",
        "slug": "02_forward_green_clear",
        "title": "案例 2 · 绿灯直行",
        "note": "单一动作 Forward；理由是绿灯 + 前方畅通。",
    },
    {
        "file_name": "57aff47a-053377cd_3.jpg",
        "slug": "03_forward_follow",
        "title": "案例 3 · 跟随前车前进",
        "note": "单一动作 Forward；理由是跟随前车 + 前方畅通。",
    },
    {
        "file_name": "309b6cd6-52335834_3.jpg",
        "slug": "04_left_lane",
        "title": "案例 4 · 左转",
        "note": "单一动作 Left；理由是存在左侧车道。",
    },
    {
        "file_name": "074496ba-42552499_1.jpg",
        "slug": "05_right_green",
        "title": "案例 5 · 可右转",
        "note": "单一动作 Right；理由同时包含绿灯、前方畅通和右转绿灯。",
    },
    {
        "file_name": "a10582c9-a96da043_3.jpg",
        "slug": "06_forward_left_multihot",
        "title": "案例 6 · 多动作同时成立",
        "note": "Forward 与 Left 同时为 1。动作不是互斥四选一。",
    },
]

BG = (15, 18, 23)
PANEL = (28, 32, 40)
TEXT = (236, 239, 244)
MUTED = (156, 163, 175)
LINE = (55, 65, 81)
ACTION_COLOR = {
    "Forward": (37, 99, 235),
    "Stop": (220, 38, 38),
    "Left": (217, 119, 6),
    "Right": (5, 150, 105),
}
REASON_COLOR = (67, 56, 202)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ]
    for path, index in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index)
    return ImageFont.load_default()


def load_manifest() -> dict[str, dict]:
    records = {}
    with (PROJECT_ROOT / "data" / "processed" / "test.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            records[rec["file_name"]] = rec
    return records


def names_from(bits: list[int], vocab: list[str]) -> list[str]:
    return [name for name, bit in zip(vocab, bits) if bit]


def fit_image(path: Path, width: int, height: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def draw_chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fill: tuple[int, int, int],
    font: ImageFont.ImageFont,
) -> int:
    x, y = xy
    pad_x, pad_y = 10, 6
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + pad_x * 2
    h = bbox[3] - bbox[1] + pad_y * 2
    draw.rounded_rectangle((x, y, x + w, y + h), radius=8, fill=fill)
    draw.text((x + pad_x, y + pad_y - 1), text, fill=(255, 255, 255), font=font)
    return w + 8


def wrap_chips(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    items: list[tuple[str, tuple[int, int, int]]],
    font: ImageFont.ImageFont,
    max_x: int,
) -> int:
    x, y = start
    row_h = 34
    for text, color in items:
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        bbox = probe.textbbox((0, 0), text, font=font)
        need = bbox[2] - bbox[0] + 28
        if x + need > max_x:
            x = start[0]
            y += row_h
        x += draw_chip(draw, (x, y), text, color, font)
    return y + row_h


def render_card(case: dict, record: dict, out_path: Path) -> None:
    width, photo_h, panel_h = 960, 420, 250
    canvas = Image.new("RGB", (width, photo_h + panel_h), BG)
    photo = fit_image(IMAGE_ROOT / case["file_name"], width, photo_h)
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, photo_h, width, photo_h + panel_h), fill=PANEL)
    draw.line((0, photo_h, width, photo_h), fill=LINE, width=2)

    title_font = load_font(28, bold=True)
    body_font = load_font(18)
    chip_font = load_font(16, bold=True)
    small_font = load_font(15)

    y = photo_h + 16
    draw.text((20, y), case["title"], fill=TEXT, font=title_font)
    y += 38
    draw.text((20, y), f"文件名  {case['file_name']}", fill=MUTED, font=small_font)
    y += 28

    actions = names_from(record["actions"], ACTION_NAMES)
    reasons = names_from(record["rationales"], RATIONALE_NAMES)
    draw.text((20, y), "动作标签  Action", fill=MUTED, font=small_font)
    y += 24
    y = wrap_chips(
        draw,
        (20, y),
        [(f"{name}  {ACTION_ZH[name]}", ACTION_COLOR[name]) for name in actions],
        chip_font,
        width - 20,
    )
    draw.text((20, y + 4), "理由标签  Rationale", fill=MUTED, font=small_font)
    y += 28
    y = wrap_chips(
        draw,
        (20, y),
        [(f"{name}  {RATIONALE_ZH[name]}", REASON_COLOR) for name in reasons],
        chip_font,
        width - 20,
    )
    draw.text((20, y + 6), case["note"], fill=TEXT, font=body_font)
    canvas.save(out_path, format="JPEG", quality=85, optimize=True)


def render_schema(out_path: Path) -> None:
    width, height = 1200, 620
    image = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    title_font = load_font(30, bold=True)
    body_font = load_font(18)
    mono_font = load_font(16)
    small_font = load_font(15)

    draw.text((40, 28), "一条 BDD-OIA 样本长什么样", fill=(15, 23, 42), font=title_font)
    draw.text(
        (40, 72),
        "输入是一张行车记录仪末帧；输出是两组可同时成立的 0/1 标签，不是一段自由文本解释。",
        fill=(71, 85, 105),
        font=body_font,
    )

    boxes = [
        (40, 130, 360, 560, "1. 图像", "last-frame JPEG\n1280 × 720 RGB\n官方划分中的一张静态图\n\n本实验只用末帧，\n不用完整视频。"),
        (420, 130, 740, 560, "2. 动作向量 · 4 维", "Forward  Stop  Left  Right\n示例: [0, 1, 0, 0]\n\n含义: Stop = 1\n其余动作 = 0\n\n可以多个动作同时为 1\n例如 [1, 0, 1, 0]"),
        (800, 130, 1160, 560, "3. 理由向量 · 21 维", "21 个预定义理由标签\n示例: red_light, rider = 1\n\n这是标签恢复任务\n不是模型内部推理轨迹\n也不是忠实解释。"),
    ]
    for x0, y0, x1, y1, title, body in boxes:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=16, fill=(255, 255, 255), outline=(203, 213, 225), width=2)
        draw.text((x0 + 22, y0 + 20), title, fill=(15, 23, 42), font=title_font)
        draw.multiline_text((x0 + 22, y0 + 80), body, fill=(51, 65, 85), font=mono_font, spacing=8)

    draw.polygon([(372, 330), (408, 314), (408, 346)], fill=(37, 99, 235))
    draw.polygon([(752, 330), (788, 314), (788, 346)], fill=(37, 99, 235))
    draw.text((40, 580), "官方原始标注还可能带第 5 个动作位；本实验只使用前 4 位，并丢掉四动作全空样本。", fill=(100, 116, 139), font=small_font)
    image.save(out_path, format="PNG")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    missing = [case["file_name"] for case in CASES if case["file_name"] not in manifest]
    if missing:
        raise SystemExit(f"missing test records: {missing}")
    absent = [case["file_name"] for case in CASES if not (IMAGE_ROOT / case["file_name"]).exists()]
    if absent:
        raise SystemExit(f"missing image files: {absent}")

    render_schema(OUT_DIR / "00_sample_schema.png")
    for case in CASES:
        render_card(case, manifest[case["file_name"]], OUT_DIR / f"{case['slug']}.jpg")
        print("wrote", case["slug"])


if __name__ == "__main__":
    main()
