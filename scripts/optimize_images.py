"""
Optimize airport images: resize, compress, create WebP.
Run: python scripts/optimize_images.py
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Install pillow: pip install pillow")
    sys.exit(1)

IMAGES_DIR = Path(__file__).parent.parent / "static" / "images" / "airports"
MAX_SIZE = (800, 600)
JPEG_QUALITY = 85
WEBP_QUALITY = 85


def main():
    create_webp = "--webp" in sys.argv
    if not IMAGES_DIR.exists():
        print(f"Directory not found: {IMAGES_DIR}")
        return

    for img_path in sorted(IMAGES_DIR.glob("*.jpg")):
        try:
            img = Image.open(img_path)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail(MAX_SIZE)
            img.save(img_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
            if create_webp:
                webp_path = img_path.with_suffix(".webp")
                img.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
                print(f"  {img_path.name} + {webp_path.name}")
            else:
                print(f"  Optimized {img_path.name}")
        except Exception as e:
            print(f"  Error {img_path.name}: {e}")

    print(f"\nDone. Images in {IMAGES_DIR}")
    if create_webp:
        print("WebP created. Frontend uses <picture> for modern browsers.")


if __name__ == "__main__":
    main()
