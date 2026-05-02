"""
压缩图片（JPEG/PNG/WebP）。

用法：
  python3 scripts/img_compress.py photo.jpg                    # 默认 quality=80
  python3 scripts/img_compress.py photo.jpg --quality 60
  python3 scripts/img_compress.py photo.jpg --max-width 1600   # 同时缩长边
  python3 scripts/img_compress.py *.jpg --inplace              # 原地覆盖（危险）
"""

import argparse
from pathlib import Path

from PIL import Image


def _compress_one(src: Path, quality: int, max_width: int | None, inplace: bool) -> Path:
    img = Image.open(src)
    if img.mode in ("RGBA", "P") and src.suffix.lower() in (".jpg", ".jpeg"):
        img = img.convert("RGB")

    if max_width and img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    if inplace:
        dst = src
    else:
        dst = src.with_name(f"{src.stem}_compressed{src.suffix}")

    save_kwargs = {"optimize": True}
    if src.suffix.lower() in (".jpg", ".jpeg", ".webp"):
        save_kwargs["quality"] = quality
    img.save(dst, **save_kwargs)
    return dst


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def main() -> None:
    parser = argparse.ArgumentParser(description="批量压缩图片")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--quality", type=int, default=80, help="JPEG/WebP 质量 1-100，默认 80")
    parser.add_argument("--max-width", type=int, help="长边最大宽度（像素）")
    parser.add_argument("--inplace", action="store_true", help="原地覆盖，谨慎")
    args = parser.parse_args()

    for src in args.inputs:
        if not src.exists():
            print(f"跳过：{src}（不存在）")
            continue
        before = src.stat().st_size
        try:
            dst = _compress_one(src, args.quality, args.max_width, args.inplace)
        except Exception as e:
            print(f"失败：{src}：{e}")
            continue
        after = dst.stat().st_size
        ratio = (1 - after / before) * 100
        print(f"{src.name} → {dst.name}  {_human(before)} → {_human(after)}  -{ratio:.0f}%")


if __name__ == "__main__":
    main()
