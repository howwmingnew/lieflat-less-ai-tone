"""重畫 hero 圖裡的文字，其餘像素不動。

hero 圖沒有原始設計檔，改字只能直接改像素。作法是把要改的文字矩形清成底色、
把穿過的網格線補回去，再用量測出來的字級與座標重畫該行字。標題、kicker、
Moxt 標誌、分隔線與整張底圖都不會被碰到。

座標與顏色都是從 1600×720 的原圖量出來的，改圖尺寸或版面就要重新量。
中文用 PingFang TC Medium 配 stroke_width=1 的超取樣，對應原圖瀏覽器合成粗體的
筆畫粗細；等寬字用 Menlo，與原圖的 kicker／頁尾一致。

用法：
    python3 scripts/patch-hero-text.py            # 兩張圖都重畫
    python3 scripts/patch-hero-text.py --target zh
    python3 scripts/patch-hero-text.py --assets <目錄> --dry-run

需要 Pillow（pip install pillow）與 macOS 內建的 PingFang／Menlo 字型。
重跑的結果與上一次相同，可以安全地重複執行。
"""
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS = REPO / "assets"
ZH_IMAGE = "less-ai-tone-hero-zh.png"
EN_IMAGE = "less-ai-tone-hero-en.png"

# 從原圖量到的版面常數（1600×720）
CANVAS = (1600, 720)
BG = (247, 245, 239)
GRID = (236, 234, 227)
GRID_STEP = 56
GRID_PHASE = 1
INK_DARK = (23, 23, 23)     # 標題與統計數字
INK_BODY = (57, 55, 51)     # 副標
INK_MUTED = (95, 92, 85)    # 標籤
INK_FOOTER = (113, 109, 101)

SUBTITLE_SIZE = 27
LABEL_SIZE = 15
FOOTER_SIZE = 13.26
LINE_GAP = 42               # 副標兩行的行距
PUNCT_KERN = 13             # 原圖「」，」被擠壓掉的半個字寬
SUPERSAMPLE = 4
FOOTER_SUPERSAMPLE = 8      # 等寬字較細，拉高倍率讓 stroke 只加一點點

MENLO = Path("/System/Library/Fonts/Menlo.ttc")
PINGFANG_CANDIDATES = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/Library/Fonts/PingFang.ttc"),
)
PINGFANG_ASSET_GLOB = "com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc"
PINGFANG_TC_MEDIUM = 6      # PingFang.ttc 內的字型索引

OLD_FOOTER = "github.com/larashero3-dotcom/lieflat-less-ai-tone"
NEW_FOOTER = "github.com/howwmingnew/lieflat-less-ai-tone"


def find_pingfang():
    for path in PINGFANG_CANDIDATES:
        if path.exists():
            return path
    assets = Path("/System/Library/AssetsV2")
    if assets.is_dir():
        for path in sorted(assets.glob(PINGFANG_ASSET_GLOB)):
            return path
    return None


def clear(draw, box):
    """清成底色，並把穿過這塊的網格線補回去。"""
    x0, y0, x1, y1 = box
    draw.rectangle([x0, y0, x1, y1], fill=BG)
    for x in range(x0, x1 + 1):
        if (x - GRID_PHASE) % GRID_STEP == 0:
            draw.line([(x, y0), (x, y1)], fill=GRID)
    for y in range(y0, y1 + 1):
        if (y - GRID_PHASE) % GRID_STEP == 0:
            draw.line([(x0, y), (x1, y)], fill=GRID)


def render(text, font_path, index, size, fill, scale):
    """超取樣畫一行字，回傳 (影像, 畫筆在影像中的座標)。"""
    pad = 40
    font = ImageFont.truetype(str(font_path), int(size * scale), index=index)
    width = int((len(text) * size * 1.5 + pad * 2) * scale)
    height = int((size * 2 + pad * 2) * scale)
    canvas = Image.new("RGB", (width, height), BG)
    ImageDraw.Draw(canvas).text(
        (pad * scale, pad * scale), text, font=font, fill=fill,
        stroke_width=1, stroke_fill=fill)
    small = canvas.resize((width // scale, height // scale), Image.LANCZOS)
    return small, (pad, pad)


def ink_box(image, threshold=235):
    return image.convert("L").point(lambda v: 255 if v < threshold else 0).getbbox()


def pen_for(anchor, font_path, index, size, fill, ink_topleft, scale):
    """回推畫筆座標，使 anchor 的墨跡左上角落在 ink_topleft。"""
    image, (px, py) = render(anchor, font_path, index, size, fill, scale)
    box = ink_box(image)
    if box is None:
        raise ValueError(f"字型畫不出「{anchor}」，無法對位")
    return (ink_topleft[0] - (box[0] - px), ink_topleft[1] - (box[1] - py))


def draw_run(base, text, font_path, index, size, fill, pen, scale):
    """把一行字疊到 base 上，只疊墨跡，底下的網格線保留。"""
    image, (px, py) = render(text, font_path, index, size, fill, scale)
    box = ink_box(image)
    if box is None:
        return
    crop = image.crop(box)
    span = max(1, BG[0] - fill[0])
    mask = crop.convert("L").point(lambda v: max(0, min(255, (BG[0] - v) * 255 // span)))
    base.paste(crop, (pen[0] - px + box[0], pen[1] - py + box[1]), mask)


def advance(text, font_path, index, size, scale):
    font = ImageFont.truetype(str(font_path), int(size * scale), index=index)
    return font.getlength(text) / scale


def patch_footer(image, draw, pingfang=None):
    """頁尾網址：兩張圖共用同一個位置與字型。"""
    clear(draw, (74, 664, 470, 692))
    pen = pen_for(OLD_FOOTER, MENLO, 0, FOOTER_SIZE, INK_FOOTER, (78, 672), FOOTER_SUPERSAMPLE)
    draw_run(image, NEW_FOOTER, MENLO, 0, FOOTER_SIZE, INK_FOOTER, pen, FOOTER_SUPERSAMPLE)


def patch_zh(image, pingfang):
    draw = ImageDraw.Draw(image)
    tc = (pingfang, PINGFANG_TC_MEDIUM)

    # 副標兩行。原圖把「」，」擠壓掉半個字寬，所以拆成兩段畫，行尾才會對齊。
    clear(draw, (74, 350, 800, 438))
    head, tail = "用語言學方法量化「什麼是 AI 味」", "，再把它從中文寫作裡去"
    pen = pen_for("用", *tc, SUBTITLE_SIZE, INK_BODY, (78, 361), SUPERSAMPLE)
    draw_run(image, head, *tc, SUBTITLE_SIZE, INK_BODY, pen, SUPERSAMPLE)
    tail_x = round(pen[0] + advance(head, *tc, SUBTITLE_SIZE, SUPERSAMPLE) - PUNCT_KERN)
    draw_run(image, tail, *tc, SUBTITLE_SIZE, INK_BODY, (tail_x, pen[1]), SUPERSAMPLE)
    draw_run(image, "掉。", *tc, SUBTITLE_SIZE, INK_BODY, (pen[0], pen[1] + LINE_GAP), SUPERSAMPLE)

    # 三組統計數字的單位。阿拉伯數字不重畫，只清單位那一格。
    for box, text, ink_left in (((130, 466, 205, 503), "萬字", 143),
                                ((275, 466, 318, 503), "項", 286),
                                ((392, 466, 434, 503), "條", 401)):
        clear(draw, box)
        unit_pen = pen_for(text[0], *tc, SUBTITLE_SIZE, INK_DARK, (ink_left, 473), SUPERSAMPLE)
        draw_run(image, text, *tc, SUBTITLE_SIZE, INK_DARK, unit_pen, SUPERSAMPLE)

    # 三組標籤
    clear(draw, (74, 506, 418, 533))
    for text, ink_left in (("對照語料", 78), ("候選特徵", 236), ("通過檢驗", 352)):
        label_pen = pen_for(text[0], *tc, LABEL_SIZE, INK_MUTED, (ink_left, 513), SUPERSAMPLE)
        draw_run(image, text, *tc, LABEL_SIZE, INK_MUTED, label_pen, SUPERSAMPLE)

    patch_footer(image, draw)


def patch_en(image, pingfang):
    # 英文版只有頁尾網址要跟著 fork 改
    patch_footer(image, ImageDraw.Draw(image))


def process(path, patch, pingfang, dry_run):
    if not path.exists():
        return f"找不到 {path}"
    image = Image.open(path).convert("RGB")
    if image.size != CANVAS:
        return f"{path.name} 尺寸是 {image.size}，座標是按 {CANVAS} 量的，請重新量測"
    before = image.tobytes()
    patch(image, pingfang)
    if image.tobytes() == before:
        return f"{path.name} 內容未變（已是最新）"
    if dry_run:
        return f"{path.name} 會被改寫（--dry-run，未寫入）"
    image.save(path)
    return f"{path.name} 已重畫"


def main(argv):
    parser = argparse.ArgumentParser(description="重畫 hero 圖裡的文字")
    parser.add_argument("--assets", default=str(DEFAULT_ASSETS), help="圖片所在目錄")
    parser.add_argument("--target", choices=("zh", "en", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true", help="只回報會不會變動，不寫檔")
    args = parser.parse_args(argv)

    if not MENLO.exists():
        return f"找不到等寬字型：{MENLO}（這支腳本目前只在 macOS 上能跑）"
    pingfang = find_pingfang()
    if pingfang is None:
        return "找不到 PingFang.ttc（這支腳本目前只在 macOS 上能跑）"

    assets = Path(args.assets).expanduser()
    jobs = []
    if args.target in ("zh", "both"):
        jobs.append((assets / ZH_IMAGE, patch_zh))
    if args.target in ("en", "both"):
        jobs.append((assets / EN_IMAGE, patch_en))
    for path, patch in jobs:
        print(process(path, patch, pingfang, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
