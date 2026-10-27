"""Local CJK font selection; explicit invalid paths never fall back."""
import os
from pathlib import Path


def candidates():
    return [
        Path('/System/Library/Fonts/PingFang.ttc'),
        Path('/System/Library/Fonts/Supplemental/Songti.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf'),
        Path('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'),
        Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc',
        Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/simhei.ttf',
    ]


def font_path(value=None):
    if value:
        path = Path(value).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f'Font file does not exist: {path}')
        return path.resolve()
    for path in candidates():
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError('no usable Chinese font; configure an explicit font file')


def load_font(value, size):
    from PIL import ImageFont
    return ImageFont.truetype(str(font_path(value)), size)


def check_glyphs(font, text):
    """Conservative .notdef-mask check, followed by required visual QA."""
    marker = font.getmask('\U0010ffff')
    missing = []
    for char in sorted(set(text)):
        if char.isspace():
            continue
        mask = font.getmask(char)
        if mask.size == marker.size and bytes(mask) == bytes(marker):
            missing.append(char)
    if missing:
        raise ValueError('Font has missing glyphs: ' + ''.join(missing))
    return True
