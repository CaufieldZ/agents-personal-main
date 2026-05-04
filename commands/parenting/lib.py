#!/usr/bin/env python3
"""
查素材库(绘本 / 童谣 / 食谱)。

用法:
    python commands/parenting/lib.py books [--status owned|read|wishlist] [--age 1-2y]
    python commands/parenting/lib.py songs [--language zh|en]
    python commands/parenting/lib.py recipes
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "parenting" / "library"


def cmd_books(args: argparse.Namespace) -> None:
    items = json.loads((LIB / "books.json").read_text(encoding="utf-8")).get("items", [])
    if args.status:
        items = [i for i in items if i.get("status") == args.status]
    if args.age:
        items = [i for i in items if args.age in (i.get("age_range") or "")]
    if not items:
        print("(空)添加项: 编辑 parenting/library/books.json,新书必须带 source 字段")
        return
    for i in items:
        print(f"- {i.get('title')} / {i.get('author', '?')}  [{i.get('status', '?')}] "
              f"年龄 {i.get('age_range', '?')}  ★{i.get('rating', '-')}")
        if i.get("notes"):
            print(f"    {i['notes']}")


def cmd_songs(args: argparse.Namespace) -> None:
    items = json.loads((LIB / "songs.json").read_text(encoding="utf-8")).get("items", [])
    if args.language:
        items = [i for i in items if i.get("language") == args.language]
    if not items:
        print("(空)添加项: 编辑 parenting/library/songs.json")
        return
    for i in items:
        print(f"- {i.get('title')}  [{i.get('language', '?')}]  {i.get('occasion', '')}")


def cmd_recipes(args: argparse.Namespace) -> None:
    recipes_dir = LIB / "recipes"
    files = sorted(p for p in recipes_dir.glob("*.md") if p.name != "README.md")
    if not files:
        print(f"(空)添加食谱: 在 {recipes_dir} 新建 .md 文件,见 README.md 模板")
        return
    for p in files:
        print(f"- {p.stem}  ({p})")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="kind", required=True)

    b = sub.add_parser("books")
    b.add_argument("--status", choices=["wishlist", "owned", "read"])
    b.add_argument("--age")
    b.set_defaults(func=cmd_books)

    s = sub.add_parser("songs")
    s.add_argument("--language", choices=["zh", "en"])
    s.set_defaults(func=cmd_songs)

    r = sub.add_parser("recipes")
    r.set_defaults(func=cmd_recipes)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
