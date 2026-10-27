#!/usr/bin/env python3
"""Build deterministic vertical overlay, preview, thumbnail, and optional cover."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import outside_package, child_output


from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


from shared.fonts import load_font
import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


W, H = 1080, 1920


def color(value, default):
    value = value or default
    value = value.lstrip("#")
    if len(value) == 6:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    if len(value) == 8:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4, 6))
    raise ValueError(f"Invalid color: {value}")


def font(path, size):
    return load_font(path, size)


def paper_background(path, paper):
    if path:
        return Image.open(path).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)
    base = Image.new("RGBA", (W, H), paper)
    rng = random.Random(10801920)
    noise = Image.new("L", (W // 4, H // 4))
    noise.putdata([max(0, min(255, 128 + rng.randint(-18, 18))) for _ in range(noise.width * noise.height)])
    noise = noise.resize((W, H), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
    texture = Image.new("RGBA", (W, H), (90, 75, 60, 0))
    texture.putalpha(noise.point(lambda p: int(abs(p - 128) * 0.8)))
    return Image.alpha_composite(base, texture)


def fit_cover(image, size):
    target_w, target_h = size
    ratio = max(target_w / image.width, target_h / image.height)
    scaled = image.resize((round(image.width * ratio), round(image.height * ratio)), Image.Resampling.LANCZOS)
    left = (scaled.width - target_w) // 2
    top = (scaled.height - target_h) // 2
    return scaled.crop((left, top, left + target_w, top + target_h))


def fit_contain(image, size):
    target_w, target_h = size
    ratio = min(target_w / image.width, target_h / image.height)
    return image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)


def draw_segments(draw, y, segments, title_font, palette, align="center", right=W / 2, gap=0):
    pieces = [(item["text"], palette.get(item.get("color", "ink"), palette["ink"])) for item in segments]
    widths = [draw.textlength(text, font=title_font) for text, _ in pieces]
    total = sum(widths) + max(0, len(pieces) - 1) * gap
    x = float(right) - total if align == "right" else (W - total) / 2
    for index, ((text, fill), width) in enumerate(zip(pieces, widths)):
        draw.text((x, y), text, font=title_font, fill=fill, anchor="la")
        x += width + (gap if index < len(pieces) - 1 else 0)


def shaped_logo(item):
    x, y, width, height = item["box"]
    logo = fit_cover(Image.open(item["path"]).convert("RGBA"), (width, height))
    shape = item.get("shape", "none")
    if shape == "none":
        return logo, (x, y)
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    if shape == "circle":
        draw.ellipse((1, 1, width - 2, height - 2), fill=255)
    elif shape == "rounded":
        draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=item.get("radius", 18), fill=255)
    else:
        raise ValueError(f"Unknown logo shape: {shape}")
    logo.putalpha(Image.composite(logo.getchannel("A"), Image.new("L", logo.size, 0), mask))
    return logo, (x, y)


def key_background(image, mode, threshold=64, softness=48):
    image = image.convert("RGBA")
    data = []
    for r, g, b, a in image.getdata():
        lum = (r * 299 + g * 587 + b * 114) // 1000
        distance = lum if mode == "dark" else 255 - lum
        alpha = max(0, min(255, round((distance - threshold) * 255 / max(1, softness))))
        data.append((r, g, b, min(a, alpha)))
    image.putdata(data)
    return image


def paste_wordmark(canvas, item):
    x, y, width, height = item["box"]
    image = Image.open(item["path"]).convert("RGBA")
    mode = item.get("key_background")
    if mode:
        image = key_background(image, mode, item.get("threshold", 48), item.get("softness", 52))
    image = fit_contain(image, (width, height))
    canvas.alpha_composite(image, (x + (width - image.width) // 2, y + (height - image.height) // 2))


def photo_layer(spec):
    photo = Image.open(spec["path"]).convert("RGBA")
    if spec.get("crop"):
        photo = photo.crop(tuple(spec["crop"]))
    x, y, width, height = spec["box"]
    photo = fit_cover(photo, (width, height))
    photo = ImageEnhance.Contrast(photo).enhance(float(spec.get("contrast", 1.03)))
    photo = ImageEnhance.Brightness(photo).enhance(float(spec.get("brightness", 1.01)))
    fade_top = int(spec.get("fade_top", 160))
    fade_bottom = int(spec.get("fade_bottom", 260))
    mask = Image.new("L", (width, height), 255)
    pixels = mask.load()
    for row in range(height):
        alpha = 255
        if fade_top and row < fade_top:
            alpha = min(alpha, round(255 * row / fade_top))
        if fade_bottom and row >= height - fade_bottom:
            alpha = min(alpha, round(255 * (height - 1 - row) / fade_bottom))
        for col in range(width):
            pixels[col, row] = max(0, alpha)
    photo.putalpha(Image.composite(photo.getchannel("A"), Image.new("L", photo.size, 0), mask))
    return photo, (x, y)


def draw_bottom(canvas, cfg, palette, small_font):
    draw = ImageDraw.Draw(canvas)
    if cfg.get("partnership_label", "联合呈现"):
        draw.text((W / 2, 1308), cfg.get("partnership_label", "联合呈现"), font=small_font, fill=palette["accent"], anchor="ma")
        draw.line((120, 1348, 960, 1348), fill=palette["ink"][:3] + (85,), width=1)
    for item in cfg.get("logos", []):
        logo, xy = shaped_logo(item)
        canvas.alpha_composite(logo, xy)
    for item in cfg.get("wordmarks", []):
        paste_wordmark(canvas, item)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    out = outside_package(Path(cfg["output_dir"]))
    protected_inputs = [args.config]
    def collect_assets(value):
        if isinstance(value, str) and Path(value).is_file():
            protected_inputs.append(Path(value))
        elif isinstance(value, dict):
            for nested in value.values(): collect_assets(nested)
        elif isinstance(value, list):
            for nested in value: collect_assets(nested)
    for key in ("photo", "center_frame", "background", "logos", "wordmarks", "fonts"):
        collect_assets(cfg.get(key))
    planned = {key: child_output(out, cfg.get(key, default), *protected_inputs) for key, default in [("preview_name", "frame-preview.png"), ("mobile_name", "frame-mobile.png"), ("overlay_name", "frame-overlay.png"), ("cover_name", "cover.jpg")]}
    if len({p.resolve() for p in planned.values()}) != len(planned):
        raise ValueError("Visual outputs must have distinct names")
    out.mkdir(parents=True, exist_ok=True)

    colors = cfg.get("colors", {})
    palette = {
        "paper": color(colors.get("paper"), "#F4F1EA"),
        "ink": color(colors.get("ink"), "#2A2825"),
        "accent": color(colors.get("accent"), "#A4372E"),
    }
    fonts = cfg.get("fonts", {})
    title_font = font(fonts.get("title"), int(cfg.get("title_size", 72)))
    sans_font = font(fonts.get("sans"), int(cfg.get("subtitle_size", 34)))
    small_font = font(fonts.get("sans"), int(cfg.get("small_size", 24)))

    canvas = paper_background(cfg.get("background"), palette["paper"])
    if cfg.get("photo"):
        image, xy = photo_layer(cfg["photo"])
        canvas.alpha_composite(image, xy)

    draw = ImageDraw.Draw(canvas)
    title_y = cfg.get("title_y", [126, 242])
    title_align = cfg.get("title_align", "center")
    title_right = float(cfg.get("title_right", W / 2))
    title_segment_gap = float(cfg.get("title_segment_gap", 0))
    for y, line in zip(title_y, cfg.get("title", [])):
        draw_segments(draw, y, line, title_font, palette, title_align, title_right, title_segment_gap)
    if cfg.get("separator", True):
        draw.line(tuple(cfg.get("separator_line", [120, 374, 960, 374])), fill=palette["ink"][:3] + (115,), width=2)
    if cfg.get("subtitle"):
        subtitle_align = cfg.get("subtitle_align", title_align)
        subtitle_x = float(cfg.get("subtitle_right", title_right)) if subtitle_align == "right" else W / 2
        subtitle_anchor = "ra" if subtitle_align == "right" else "ma"
        draw.text((subtitle_x, cfg.get("subtitle_y", 425)), cfg["subtitle"], font=sans_font, fill=palette["ink"], anchor=subtitle_anchor)
    if cfg.get("tagline"):
        tagline_align = cfg.get("tagline_align", title_align)
        tagline_x = float(cfg.get("tagline_right", title_right)) if tagline_align == "right" else W / 2
        tagline_anchor = "ra" if tagline_align == "right" else "ma"
        draw.text((tagline_x, cfg.get("tagline_y", 492)), cfg["tagline"], font=small_font, fill=palette["accent"], anchor=tagline_anchor)

    # The cover and video preview share typography/background, but only the
    # preview receives the center video frame.
    cover_canvas = canvas.copy()
    if cfg.get("center_frame"):
        center = fit_cover(Image.open(cfg["center_frame"]).convert("RGBA"), (1080, 608))
        canvas.alpha_composite(center, (0, 656))
    draw_bottom(canvas, cfg, palette, small_font)
    draw_bottom(cover_canvas, cfg, palette, small_font)

    preview = planned["preview_name"]
    mobile = planned["mobile_name"]
    overlay = planned["overlay_name"]
    canvas.save(preview)
    canvas.resize((270, 480), Image.Resampling.LANCZOS).save(mobile)
    overlay_canvas = canvas.copy()
    overlay_canvas.paste(Image.new("RGBA", (1080, 608), (0, 0, 0, 0)), (0, 656))
    overlay_canvas.save(overlay)
    print(preview)
    print(mobile)
    print(overlay)

    if cfg.get("photo"):
        cover = planned["cover_name"]
        cover_canvas.convert("RGB").save(cover, quality=95, subsampling=0)
        print(cover)


if __name__ == "__main__":
    main()
