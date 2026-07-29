"""Export Home Assistant-ready Chore Race brand assets."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tmp" / "imagegen" / "chore-race-brand-transparent.png"
OUTPUTS = (
    ROOT / "brand_assets",
    ROOT / "custom_components" / "chore_race" / "brand",
    ROOT / "docs" / "assets",
)


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise RuntimeError("Generated image contains no visible pixels")

    image = image.crop(bounds)
    padding = max(image.size) // 32
    side = max(image.size) + (padding * 2)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    position = ((side - image.width) // 2, (side - image.height) // 2)
    canvas.alpha_composite(image, position)

    for output in OUTPUTS:
        output.mkdir(parents=True, exist_ok=True)
        for size, filename in ((256, "icon.png"), (512, "icon@2x.png")):
            exported = canvas.resize((size, size), Image.Resampling.LANCZOS)
            exported.save(output / filename, optimize=True)


if __name__ == "__main__":
    main()
