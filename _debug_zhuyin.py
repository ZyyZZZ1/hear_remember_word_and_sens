# -*- coding: utf-8 -*-
"""Debug zhuyin matching between pypinyin and tokenizer vocab"""
import json, sys
sys.path.insert(0, ".")

# 1. Check tokenizer vocab for all zhuyin characters
with open(r"kokoro_models\tokenizer_v1.1.json", "r", encoding="utf-8") as f:
    d = json.load(f)
vocab = d["model"]["vocab"]

# Zhuyin characters are in Unicode block U+3100-U+312F
print("=== Zhuyin chars in tokenizer ===")
zhuyin_in_vocab = {}
for k, v in vocab.items():
    if '\u3100' <= k <= '\u312f':
        zhuyin_in_vocab[k] = v
        print(f"  U+{ord(k):04X} {k} -> {v}")
print(f"Total zhuyin entries: {len(zhuyin_in_vocab)}")

# 2. Check pypinyin output
print("\n=== pypinyin BOPOMOFO output ===")
from pypinyin import pinyin, Style

tests = ["你好", "带上", "世界", "中国", "英语", "父亲", "医生"]
for t in tests:
    py = pinyin(t, style=Style.BOPOMOFO)
    zhuyin = "".join(p[0] for p in py)
    chars = [f"U+{ord(c):04X}({c})" for c in zhuyin]
    in_vocab = [c for c in zhuyin if c in vocab]
    not_in = [c for c in zhuyin if c not in vocab]
    print(f"  {t} -> {zhuyin}")
    print(f"    Chars: {' '.join(chars)}")
    print(f"    In vocab: {len(in_vocab)}  Missing: {len(not_in)} {not_in}")

# 3. Also check the first tone mark issue
# pypinyin might include tone marks or not
print("\n=== Tones check ===")
for t in ["妈", "麻", "马", "骂", "吗"]:
    py = pinyin(t, style=Style.BOPOMOFO)
    print(f"  {t} -> {repr(py)}")
