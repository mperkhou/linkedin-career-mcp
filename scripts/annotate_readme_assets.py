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
    start_index: int = 1,
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
    for offset, callout in enumerate(callouts):
        index = start_index + offset
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

    for offset, callout in enumerate(callouts):
        index = start_index + offset
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
    draw.text((panel[0] + 68, panel[1] + 24), "Background action", fill=TEXT, font=FONT_LEGEND)
    draw.text(
        (panel[0] + 68, panel[1] + 55),
        "run v1 and v2 resume workflow for 4 job(s)",
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
        (panel[2] - 98, panel[1] + 24, panel[2] - 62, panel[1] + 58),
        (241, 245, 249, 255),
        color_for(4),
        width=2,
        radius=17,
    )
    draw.text((panel[2] - 84, panel[1] + 32), "v", fill=MUTED, font=FONT_SMALL)
    draw_rounded(
        draw,
        (panel[2] - 52, panel[1] + 24, panel[2] - 16, panel[1] + 58),
        (241, 245, 249, 255),
        color_for(5),
        width=2,
        radius=17,
    )
    draw.text((panel[2] - 40, panel[1] + 32), "x", fill=MUTED, font=FONT_SMALL)

    console = (panel[0] + 24, panel[1] + 88, panel[2] - 24, panel[3] - 22)
    draw_rounded(draw, console, (15, 23, 42, 255), (51, 65, 85, 255), width=2, radius=10)
    console_lines = [
        "[v1] Generating Draft v1 for 4432391802",
        "[v1] Stored ARO YAML, resume HTML/PDF, and ATS fields",
        "[v2] Running GLM 5.2 second-pass refinement",
        "[v2] Stored Refined v2 with critique and validation metadata",
        "[tracker] Active resume links remain on the selected variant",
    ]
    y = console[1] + 20
    for line in console_lines:
        draw.text((console[0] + 18, y), line, fill=(226, 232, 240, 255), font=FONT_SMALL)
        y += 27

    callouts = [
        Callout("Live command output", console),
        Callout(
            "Current workflow summary",
            (panel[0] + 24, panel[1] + 18, panel[0] + 340, panel[1] + 50),
        ),
        Callout(
            "Running/completed state",
            (panel[2] - 226, panel[1] + 24, panel[2] - 112, panel[1] + 58),
        ),
        Callout(
            "Collapse and close controls",
            (panel[2] - 98, panel[1] + 24, panel[2] - 16, panel[1] + 58),
        ),
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
        badge_x = x1 - 14 if index in {3, 4} else x1 + 12
        draw_badge(overlay_draw, (badge_x, max(18, badge_y)), index)
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
        "Daily review starts here: status colors, selected variants, ATS, source "
        "links, generated resumes, sync state, and cover-letter actions.",
        [
            Callout("Search, filters, Add, and Actions menu", (18, 76, 1458, 118)),
            Callout("Draft v1, Refined v2, and Manual pass badges", (228, 258, 404, 606)),
            Callout("Interview and N/A status row shading", (18, 310, 1538, 506)),
            Callout("ATS score from the selected resume variant", (812, 210, 876, 546)),
            Callout("JOD and source job links", (916, 210, 1068, 572)),
            Callout("Resume, HTML, Edit, Review, and Download actions", (1102, 210, 1238, 578)),
            Callout("ARO-to-rendered-resume sync state", (1288, 210, 1358, 546)),
            Callout("Manual cover-letter actions", (1400, 210, 1526, 546)),
        ],
    )
    annotate_screenshot(
        "tracker-add-seed.png",
        "tracker-add-seed-annotated.png",
        "Add And Seed Jobs",
        "The Add page can seed a batch, choose a posting-age window, and chain "
        "the selected local workflow stages for the new rows.",
        [
            Callout("Seed widget for batch loading", (20, 134, 1534, 530)),
            Callout("Job count maps to MAX_JOBS", (34, 202, 1520, 238)),
            Callout("Posting-age radio choices", (34, 254, 182, 338)),
            Callout("Default v1 plus v2 workflow toggles", (34, 352, 260, 410)),
            Callout("Optional manual pass and highlighting stages", (34, 424, 300, 466)),
            Callout(
                "Single LinkedIn or external URL fallbacks remain available",
                (20, 544, 1534, 888),
            ),
        ],
    )
    annotate_screenshot(
        "tracker-actions-menu.png",
        "tracker-actions-menu-annotated.png",
        "Tracker Actions Menu",
        "Selected rows can run the main v1 plus v2 path, a v1-only path, v2 "
        "reruns, Codex manual pass, highlighting, or ARO sync.",
        [
            Callout("Actions menu trigger", (1384, 78, 1458, 116)),
            Callout("Resume workflow choices", (1196, 146, 1438, 354)),
            Callout("Optional highlighting chain after draft generation", (1196, 370, 1438, 404)),
            Callout("Selected-row count and Run button", (1196, 420, 1448, 452)),
            Callout("Actions operate on checked tracker rows", (36, 152, 58, 532)),
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
        "job-description-diff.png",
        "job-description-diff-annotated.png",
        "JOD Diff View",
        "Same JOD editor after scrolling below the raw text panes to inspect trimming "
        "and line-level comparison.",
        [
            Callout("Raw comparison panes continue directly above", (18, 96, 1568, 206)),
            Callout("Text removed while creating the prompt JOD", (18, 194, 1568, 524)),
            Callout("Line-level parsed-versus-prompt diff", (18, 536, 1568, 898)),
        ],
        start_index=5,
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
        "resume-variant-review.png",
        "resume-variant-review-annotated.png",
        "Resume Variant Review",
        "The review page compares stored variants, variant-specific artifacts, "
        "ATS movement, ARO diff, accepted/rejected changes, and unsupported terms.",
        [
            Callout("Selected variant badge", (1452, 18, 1526, 40)),
            Callout("Draft v1, Refined v2, and Manual pass variants", (20, 126, 1532, 548)),
            Callout("ATS component scores and deltas per variant", (316, 214, 494, 532)),
            Callout("Variant-specific PDF/HTML artifacts", (600, 214, 678, 464)),
            Callout("Reversible selection actions", (886, 212, 1080, 502)),
            Callout("v1/v2 ARO diff", (20, 562, 1532, 1094)),
            Callout("Accepted, rejected, and unsupported review details", (20, 1108, 1450, 1654)),
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
