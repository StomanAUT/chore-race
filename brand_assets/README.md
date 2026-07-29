# Chore Race brand assets

- `icon.png`: 256 x 256 px transparent PNG
- `icon@2x.png`: 512 x 512 px transparent PNG
- `dark_icon.png`: 256 x 256 px dark-theme variant
- `dark_icon@2x.png`: 512 x 512 px dark-theme variant

The mark combines a golden trophy, racing flag, and celebration sparkles. Gold,
navy, black, and white keep it recognizable in both light and dark Home
Assistant themes, even at small integration-list sizes. The dark-theme files
currently contain the same high-contrast artwork so Home Assistant's explicit
dark-mode brand request never falls back to the missing-image placeholder.

The source artwork was generated with OpenAI ImageGen, made transparent with
the ImageGen chroma-key helper, and exported with
`scripts/export_brand_assets.py` according to Home Assistant's 256/512 px icon
specification.
