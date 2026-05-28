from PIL import Image
import os

IMG_DIR = "mockups/nuova-immagine/img"

SIZES = {
    "hero.png":    (1200, 800),
    "hair-1.png":  (800, 600),
    "hair-2.png":  (800, 600),
    "hair-3.png":  (800, 600),
    "staff.png":   (800, 900),
    "salon-1.png": (700, 500),
    "salon-2.png": (700, 500),
    "salon-3.png": (700, 500),
    "salon-4.png": (700, 500),
}

for fname, (max_w, max_h) in SIZES.items():
    src = os.path.join(IMG_DIR, fname)
    webp = fname.replace(".png", ".webp")
    dst = os.path.join(IMG_DIR, webp)
    img = Image.open(src).convert("RGB")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    img.save(dst, "WEBP", quality=82, method=6)
    orig = os.path.getsize(src)
    new  = os.path.getsize(dst)
    print(f"{fname:20s}  {orig//1024:>5} KB  ->  {new//1024:>4} KB  ({webp})")
