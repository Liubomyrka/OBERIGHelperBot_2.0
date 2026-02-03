import hashlib
import io
import os
import random
from typing import Optional

from utils.logger import logger


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return (r, g, b)


def _rand_pastel(rnd: random.Random, base: tuple[int, int, int]) -> tuple[int, int, int]:
    return (
        min(255, base[0] + rnd.randint(20, 80)),
        min(255, base[1] + rnd.randint(20, 80)),
        min(255, base[2] + rnd.randint(20, 80)),
    )


def create_birthday_image_bytes(
    name: str,
    seed: Optional[str] = None,
    greeting_type: str = "morning",
    size: tuple[int, int] = (1024, 576),
) -> Optional[bytes]:
    """
    Create a simple festive birthday image with optional text.
    Returns PNG bytes or None on failure.
    """
    try:
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except Exception as exc:
            logger.error(f"❌ Pillow не встановлено, зображення не буде створено: {exc}")
            return None

        seed_source = seed or name or "birthday"
        seed_int = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest(), 16) % (2**32)
        rnd = random.Random(seed_int)

        width, height = size
        if greeting_type == "evening":
            c1 = (40, 46, 99)
            c2 = (142, 52, 118)
        else:
            c1 = (255, 190, 120)
            c2 = (120, 200, 255)

        img = Image.new("RGB", (width, height), c1)
        draw = ImageDraw.Draw(img)

        # Gradient background
        for y in range(height):
            t = y / (height - 1)
            draw.line([(0, y), (width, y)], fill=_mix(c1, c2, t))

        # Confetti
        base_colors = [(255, 99, 132), (54, 162, 235), (255, 206, 86), (75, 192, 192)]
        for _ in range(220):
            x = rnd.randint(0, width - 1)
            y = rnd.randint(0, height - 1)
            size_px = rnd.randint(2, 6)
            color = _rand_pastel(rnd, rnd.choice(base_colors))
            draw.rectangle([x, y, x + size_px, y + size_px], fill=color)

        # Balloons
        for _ in range(5):
            cx = rnd.randint(120, width - 120)
            cy = rnd.randint(80, height - 220)
            r = rnd.randint(40, 70)
            color = _rand_pastel(rnd, rnd.choice(base_colors))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(255, 255, 255))
            draw.line([(cx, cy + r), (cx + rnd.randint(-15, 15), cy + r + 130)], fill=(255, 255, 255), width=2)

        # Title text
        title = "З Днем народження!"
        subtitle = name.strip() if name.strip() else "Іменинник"
        font_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets",
            "fonts",
            "Kotyhoroshko-Regular.0.2.otf",
        )

        font_title = None
        font_name = None
        if font_path:
            try:
                font_title = ImageFont.truetype(font_path, 64)
                font_name = ImageFont.truetype(font_path, 56)
            except Exception as exc:
                logger.warning(f"Не вдалося завантажити шрифт '{font_path}': {exc}")

        if font_title is None:
            font_title = ImageFont.load_default()
        if font_name is None:
            font_name = ImageFont.load_default()

        def _center_text(text: str, font: ImageFont.FreeTypeFont, y: int) -> int:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            return max(0, int((width - text_w) / 2))

        title_y = int(height * 0.12)
        name_y = int(height * 0.25)

        def _draw_text_with_shadow(text: str, font: ImageFont.FreeTypeFont, y: int):
            x = _center_text(text, font, y)
            # Shadow for contrast
            draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 120))
            draw.text((x, y), text, font=font, fill=(255, 255, 255))

        _draw_text_with_shadow(title, font_title, title_y)
        _draw_text_with_shadow(subtitle, font_name, name_y)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as exc:
        logger.error(f"❌ Помилка генерації зображення для дня народження: {exc}")
        return None
