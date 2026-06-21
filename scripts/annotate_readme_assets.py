"""Regenerate README screenshot callouts without covering the UI.

This is a small developer utility for the static documentation assets. It reads
clean screenshots from docs/assets and writes the annotated variants referenced
by README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"

BG = (248, 250, 252, 255)
PANEL = (255, 255, 255, 255)
TEXT = (15, 23, 42, 255)
MUTED = (71, 85, 105, 255)
BORDER = (203, 213, 225, 255)
ACCENT = (15, 118, 110, 255)
PALETTE = [
    (15, 118, 110, 255),
    (37, 99, 235, 255),
    (124, 58, 237, 255),
    (190, 24, 93, 255),
    (180, 83, 9, 255),
    (22, 101, 52, 255),
    (2, 132, 199, 255),
    (67, 56, 202, 255),
    (194, 65, 12, 255),
    (8, 145, 178, 255),
    (77, 124, 15, 255),
    (162, 28, 175, 255),
    (185, 28, 28, 255),
]


@dataclass(frozen=True)
class Callout:
    label: str
    box: tuple[int, int, int, int]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = font(30, bold=True)
FONT_LEGEND = font(20, bold=True)
FONT_BODY = font(18)
FONT_BADGE = font(18, bold=True)
FONT_SMALL = font(15)


def text_size(
    draw: ImageDraw.ImageDraw, text: str, used_font: ImageFont.ImageFont
) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=used_font)
    return right - left, bottom - top


def draw_rounded(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int, int] | None,
    outline: tuple[int, int, int, int],
    width: int = 3,
    radius: int = 14,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def color_for(index: int) -> tuple[int, int, int, int]:
    return PALETTE[(index - 1) % len(PALETTE)]


def fill_for(index: int, alpha: int = 24) -> tuple[int, int, int, int]:
    red, green, blue, _ = color_for(index)
    return red, green, blue, alpha


def draw_badge(draw: ImageDraw.ImageDraw, center: tuple[int, int], number: int) -> None:
    x, y = center
    radius = 17
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=color_for(number),
        outline=(255, 255, 255, 255),
        width=4,
    )
    label = str(number)
    tw, th = text_size(draw, label, FONT_BADGE)
    draw.text((x - tw / 2, y - th / 2 - 1), label, fill=(255, 255, 255, 255), font=FONT_BADGE)


def badge_position(
    box: tuple[int, int, int, int], offset_x: int, offset_y: int, image_size: tuple[int, int]
) -> tuple[int, int]:
    x1, y1, x2, y2 = box
    base_w, base_h = image_size
    bx = offset_x + max(18, min(base_w - 18, x1 + 12))
    by = offset_y + max(18, min(base_h - 18, y1 - 18))
    if y1 < 44:
        by = offset_y + min(base_h - 18, y2 + 18)
    return bx, by


def annotate_screenshot(
    source: str,
    target: str,
    title: str,
    subtitle: str,
    callouts: list[Callout],
) -> None:
    base = Image.open(ASSET_DIR / source).convert("RGBA")
    base_w, base_h = base.size
    pad = 28
    gutter = 455
    legend_gap = 26
    canvas_w = base_w + gutter + pad * 2 + legend_gap
    canvas_h = base_h + pad * 2

    image = Image.new("RGBA", (canvas_w, canvas_h), BG)
    image.alpha_composite(base, (pad, pad))
    draw = ImageDraw.Draw(image)

    draw_rounded(
        draw,
        (pad - 1, pad - 1, pad + base_w + 1, pad + base_h + 1),
        None,
        BORDER,
        width=2,
        radius=10,
    )

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for index, callout in enumerate(callouts, start=1):
        x1, y1, x2, y2 = callout.box
        adjusted = (pad + x1, pad + y1, pad + x2, pad + y2)
        draw_rounded(overlay_draw, adjusted, fill_for(index), color_for(index), width=4, radius=12)
        draw_badge(overlay_draw, badge_position(callout.box, pad, pad, base.size), index)
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    legend_x = pad + base_w + legend_gap
    legend_y = pad
    legend_w = gutter
    draw_rounded(
        draw,
        (legend_x, legend_y, legend_x + legend_w, legend_y + base_h),
        PANEL,
        BORDER,
        width=2,
        radius=16,
    )
    draw.text((legend_x + 26, legend_y + 28), title, fill=TEXT, font=FONT_TITLE)
    y = legend_y + 72
    for line in wrap(subtitle, width=42):
        draw.text((legend_x + 26, y), line, fill=MUTED, font=FONT_SMALL)
        y += 21
    y += 16

    for index, callout in enumerate(callouts, start=1):
        draw_badge(draw, (legend_x + 43, y + 15), index)
        lines = wrap(callout.label, width=34)
        for line in lines:
            draw.text((legend_x + 70, y + 2), line, fill=TEXT, font=FONT_LEGEND)
            y += 27
        y += 18

    image.convert("RGB").save(ASSET_DIR / target, optimize=True, quality=92)


def draw_progress_panel(target: str) -> None:
    width = 1500
    panel_w = 1040
    legend_w = 395
    pad = 28
    height = 330
    image = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(image)

    panel = (pad, pad, pad + panel_w, height - pad)
    draw_rounded(draw, panel, PANEL, BORDER, width=2, radius=14)
    draw.text((panel[0] + 68, panel[1] + 24), "Background progress", fill=TEXT, font=FONT_LEGEND)
    draw.text(
        (panel[0] + 68, panel[1] + 55),
        "Resume regeneration is running",
        fill=MUTED,
        font=FONT_SMALL,
    )
    draw_rounded(
        draw,
        (panel[2] - 226, panel[1] + 24, panel[2] - 112, panel[1] + 58),
        (236, 253, 245, 255),
        color_for(3),
        width=2,
        radius=17,
    )
    draw.text((panel[2] - 204, panel[1] + 32), "Running", fill=ACCENT, font=FONT_SMALL)
    draw_rounded(
        draw,
        (panel[2] - 98, panel[1] + 24, panel[2] - 28, panel[1] + 58),
        (241, 245, 249, 255),
        color_for(4),
        width=2,
        radius=17,
    )
    draw.text((panel[2] - 78, panel[1] + 32), "Hide", fill=MUTED, font=FONT_SMALL)

    console = (panel[0] + 24, panel[1] + 88, panel[2] - 24, panel[3] - 22)
    draw_rounded(draw, console, (15, 23, 42, 255), (51, 65, 85, 255), width=2, radius=10)
    console_lines = [
        "[aro] Loading job row lts-4284753009",
        "[jod] Prompt JOD ready: 1,785 words",
        "[targets] Generated 9 compact requirement targets with GLM 5.2",
        "[experience] Rewriting prior-role bullets from ARO evidence",
        "[render] Stored ARO, resume HTML/PDF, and refreshed ATS fields",
    ]
    y = console[1] + 20
    for line in console_lines:
        draw.text((console[0] + 18, y), line, fill=(226, 232, 240, 255), font=FONT_SMALL)
        y += 27

    callouts = [
        Callout("Live command output", console),
        Callout(
            "Current action summary", (panel[0] + 24, panel[1] + 20, panel[0] + 340, panel[1] + 66)
        ),
        Callout(
            "Running/completed state",
            (panel[2] - 226, panel[1] + 24, panel[2] - 112, panel[1] + 58),
        ),
        Callout("Collapse control", (panel[2] - 98, panel[1] + 24, panel[2] - 28, panel[1] + 58)),
    ]

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for index, callout in enumerate(callouts, start=1):
        draw_rounded(
            overlay_draw, callout.box, fill_for(index), color_for(index), width=4, radius=12
        )
        x1, y1, _, y2 = callout.box
        badge_y = y1 - 14
        if y1 < 76:
            badge_y = y1 + (y2 - y1) // 2
        draw_badge(overlay_draw, (x1 + 12, max(18, badge_y)), index)
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    legend_x = panel[2] + 24
    draw_rounded(
        draw, (legend_x, pad, legend_x + legend_w, height - pad), PANEL, BORDER, width=2, radius=14
    )
    draw.text((legend_x + 24, pad + 24), "Progress Panel", fill=TEXT, font=FONT_TITLE)
    y = pad + 76
    for index, callout in enumerate(callouts, start=1):
        draw_badge(draw, (legend_x + 40, y + 15), index)
        draw.text((legend_x + 68, y + 4), callout.label, fill=TEXT, font=FONT_BODY)
        y += 54

    image.convert("RGB").save(ASSET_DIR / target, optimize=True, quality=92)


def main() -> None:
    annotate_screenshot(
        "tracker-main.png",
        "tracker-main-annotated.png",
        "Tracker Table",
        "Daily review starts here: status, ATS, source links, generated resumes, "
        "sync state, and manual cover-letter actions.",
        [
            Callout("Search, filtering, and workflow actions", (18, 76, 1500, 124)),
            Callout("ATS score from the current rendered resume", (802, 144, 914, 296)),
            Callout("JOD and source job links", (918, 144, 1110, 296)),
            Callout("Resume view, edit, and download actions", (1112, 144, 1294, 296)),
            Callout("ARO-to-rendered-resume sync state", (1306, 144, 1416, 296)),
            Callout("Manual cover-letter actions", (1418, 144, 1576, 296)),
        ],
    )
    annotate_screenshot(
        "job-description-editor.png",
        "job-description-editor-annotated.png",
        "JOD Editor",
        "The source posting and prompt-ready JOD stay side by side so manual "
        "edits can be saved and rescored.",
        [
            Callout("Save edits and refresh ATS", (18, 190, 244, 238)),
            Callout("Parsed source posting text", (18, 258, 790, 864)),
            Callout("Prompt JOD used for matching and targets", (796, 258, 1568, 864)),
            Callout("ATS summary for the current resume/JOD pair", (1276, 18, 1564, 166)),
        ],
    )
    annotate_screenshot(
        "resume-editor.png",
        "resume-editor-annotated.png",
        "Resume Editor",
        "Manual edits update the ARO, then the same object renders back to HTML, "
        "PDF, and ATS fields.",
        [
            Callout("Save, render, and rescore controls", (18, 200, 280, 250)),
            Callout("ARO-backed header and section fields", (18, 272, 1568, 654)),
            Callout("Rich-text controls for editable sections", (800, 342, 884, 386)),
            Callout("Rendered resume sections available for review", (18, 660, 1568, 892)),
            Callout("Live ATS proxy summary", (1278, 18, 1564, 176)),
        ],
    )
    annotate_screenshot(
        "cover-letter-editor.png",
        "cover-letter-editor-annotated.png",
        "Cover Letter Editor",
        "Cover letters remain manual by design: write, format, save, and export from the tracker.",
        [
            Callout("Save and export controls", (18, 120, 184, 168)),
            Callout("Rich-text controls", (28, 202, 126, 232)),
            Callout("Cover-letter body editor", (18, 238, 1568, 866)),
            Callout("Empty by default until the user writes one", (1438, 132, 1554, 162)),
        ],
    )
    draw_progress_panel("background-progress-annotated.png")


if __name__ == "__main__":
    main()
