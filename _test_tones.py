# -*- coding: utf-8 -*-
"""Test zhuyin with tone numbers vs tone marks"""
from pypinyin import pinyin, Style

tests = ["你好", "带上", "父亲", "中国", "英语"]

# Check all BOPOMOFO styles
for style_name in ['BOPOMOFO', 'BOPOMOFO_FIRST']:
    style = getattr(Style, style_name)
    print(f"\n=== Style.{style_name} ===")
    for t in tests:
        py = pinyin(t, style=style)
        raw = "".join(p[0] for p in py)
        chars = [f"U+{ord(c):04X}({c})" for c in raw]
        print(f"  {t} -> {raw}")
        print(f"    {' '.join(chars)}")

# Now try to convert to tone number format
print("\n=== Tone mark → tone number conversion ===")
tone_map = {
    '\u02c9': '1',  # macron ˉ = first tone
    '\u02ca': '2',  # acute ˊ = second tone
    '\u02c7': '3',  # caron ˇ = third tone
    '\u02cb': '4',  # grave ˋ = fourth tone
    '\u02d9': '5',  # dot ˙ = neutral tone
}
for t in tests:
    py = pinyin(t, style=Style.BOPOMOFO_FIRST)
    raw = "".join(p[0] for p in py)
    # Replace tone marks with numbers
    converted = ""
    for c in raw:
        if c in tone_map:
            converted += tone_map[c]
        else:
            converted += c
    print(f"  {t} -> {converted}")

# Also check TONE3 style (pinyin with numbers)
print("\n=== Style.TONE3 (pinyin, not zhuyin) ===")
for t in tests:
    py = pinyin(t, style=Style.TONE3)
    print(f"  {t} -> {py}")
