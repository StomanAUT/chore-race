"""Export transparent Chore Race brand assets from the generated chroma image."""

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tmp" / "imagegen" / "chore-race-chroma.png"
OUTPUT = ROOT / "brand_assets"


def remove_green_screen(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()

    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, _ = pixels[x, y]
            dominance = green - max(red, blue)
            alpha = 255
            if dominance > 12 and green > 70:
                alpha = max(0, min(255, int(255 * (1 - (dominance - 12) / 110))))
            pixels[x, y] = (red, min(green, max(red, blue)), blue, alpha)

    alpha = (
        rgba.getchannel("A")
        .filter(ImageFilter.MinFilter(5))
        .filter(ImageFilter.GaussianBlur(0.45))
    )
    rgba.putalpha(alpha)
    return rgba


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    image = remove_green_screen(Image.open(SOURCE))
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise RuntimeError("Generated image contains no visible pixels")

    image = image.crop(bounds)
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side))
    position = ((side - image.width) // 2, (side - image.height) // 2)
    canvas.alpha_composite(image, position)

    for size, filename in ((512, "icon.png"), (1024, "icon@2x.png")):
        exported = canvas.resize((size, size), Image.Resampling.LANCZOS)
        exported.save(OUTPUT / filename, optimize=True)


if __name__ == "__main__":
    main()
