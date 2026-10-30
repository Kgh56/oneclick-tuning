"""Erzeugt das Programm-Logo (icon.ico + icon.png): Steuergerät-Chip mit Blitz.

Aufruf: python kunde/logo.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ORDNER = Path(__file__).resolve().parent
S = 1024  # Arbeitsgröße, wird danach herunterskaliert (sauberes Antialiasing)


def verlauf(w, h, a, b):
    """Diagonaler Farbverlauf von a (oben links) nach b (unten rechts)."""
    bild = Image.new("RGBA", (w, h))
    px = bild.load()
    for y in range(h):
        for x in range(w):
            t = (x + y) / (w + h - 2)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    return bild


def maske(form):
    m = Image.new("L", (S, S), 0)
    form(ImageDraw.Draw(m))
    return m


BLITZ = [(0.56, 0.20), (0.33, 0.54), (0.48, 0.54), (0.42, 0.80), (0.67, 0.44), (0.52, 0.44), (0.58, 0.20)]


def blitz(d, f=1.0, dx=0.0):
    c = 0.5
    d.polygon([(S * (c + (x - c) * f + dx), S * (c + (y - c) * f)) for x, y in BLITZ], fill=255)


def gross():
    rot, orange = (255, 45, 85), (255, 159, 10)
    bild = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # Kachel: dunkel mit leuchtendem Verlaufsrand
    kachel = maske(lambda d: d.rounded_rectangle((24, 24, S - 24, S - 24), 220, fill=255))
    bild.paste(verlauf(S, S, rot, orange), (0, 0), kachel)
    innen = maske(lambda d: d.rounded_rectangle((52, 52, S - 52, S - 52), 195, fill=255))
    bild.paste(verlauf(S, S, (28, 28, 34), (6, 6, 9)), (0, 0), innen)

    # Chip-Beinchen
    beine = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(beine)
    for i in range(4):
        p = 330 + i * 110
        d.rounded_rectangle((p - 26, 175, p + 26, 300), 14, fill=255)
        d.rounded_rectangle((p - 26, S - 300, p + 26, S - 175), 14, fill=255)
        d.rounded_rectangle((175, p - 26, 300, p + 26), 14, fill=255)
        d.rounded_rectangle((S - 300, p - 26, S - 175, p + 26), 14, fill=255)
    bild.paste(verlauf(S, S, rot, orange), (0, 0), beine)

    # Chip-Körper mit Verlaufsrand
    bild.paste(verlauf(S, S, rot, orange), (0, 0),
               maske(lambda d: d.rounded_rectangle((262, 262, S - 262, S - 262), 70, fill=255)))
    bild.paste(verlauf(S, S, (40, 40, 48), (14, 14, 18)), (0, 0),
               maske(lambda d: d.rounded_rectangle((286, 286, S - 286, S - 286), 52, fill=255)))

    # Blitz mit Glühen
    glut = maske(lambda d: blitz(d, 0.62)).filter(ImageFilter.GaussianBlur(28))
    bild.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (S, S), orange).split(), glut.point(lambda v: v * 0.9))))
    bild.paste(verlauf(S, S, (255, 255, 255), (255, 214, 140)), (0, 0), maske(lambda d: blitz(d, 0.62)))
    return bild


def klein():
    """Für 16–32 px: nur Verlaufskachel mit weißem Blitz – bleibt scharf."""
    bild = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bild.paste(verlauf(S, S, (255, 45, 85), (255, 159, 10)), (0, 0),
               maske(lambda d: d.rounded_rectangle((0, 0, S, S), 230, fill=255)))
    bild.paste(Image.new("RGBA", (S, S), (255, 255, 255, 255)), (0, 0), maske(lambda d: blitz(d, 1.25)))
    return bild


def main():
    g, k = gross(), klein()
    g.resize((512, 512), Image.LANCZOS).save(ORDNER / "icon.png")
    groessen = {n: (k if n <= 32 else g).resize((n, n), Image.LANCZOS) for n in (16, 20, 24, 32, 48, 64, 128, 256)}
    groessen[256].save(ORDNER / "icon.ico", format="ICO", sizes=[(n, n) for n in groessen],
                       append_images=[groessen[n] for n in groessen if n != 256])
    print("icon.ico + icon.png erstellt")


if __name__ == "__main__":
    main()
