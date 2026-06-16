"""
把教材文件中 `[...]` 括号变位注释拆成独立的生词条目。
"""
import re, os, glob

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "教材")

# 人称代词映射
PRONOUNS = {
    0: ("yo", "我"),
    1: ("tú", "你"),
    2: ("él/ella/usted", "他/她"),
    3: ("nosotros", "我们"),
    4: ("vosotros", "你们"),
    5: ("ellos/ellas/ustedes", "他们/她们"),
}

def is_reflexive(verb):
    """判断是否是自复动词（以 -se 结尾）"""
    return verb.strip().endswith("se")

def unpack_verb_line(verb, meaning, forms):
    """把一个动词条目拆成 1个原形 + 6个变位 共7行"""
    lines = []

    # 原形行保持不变
    lines.append((verb, meaning))

    # 清理变位格式
    clean_forms = [f.strip() for f in forms]

    # 提取中文核心含义（去掉变位模式说明）
    core_meaning = meaning
    # 去掉 "规则-ar" 等标注
    core_meaning = re.sub(r'\s*[\[（].*?[\]）]$', '', core_meaning)
    # 取括号前后的主要含义
    core_meaning = re.sub(r'\s*[（(].*?[)）]', '', core_meaning)
    core_meaning = core_meaning.strip()

    # 取第一个含义作为默认
    first_meaning = core_meaning.split("、")[0].split("，")[0].split("；")[0].strip()

    # 判断是否是自复动词
    is_ref = is_reflexive(verb)

    for i, form in enumerate(clean_forms):
        if i >= 6:
            break

        pronoun_cn = PRONOUNS[i][1]

        if is_ref:
            # 自复动词：me levanto → 我起床
            cn = f"{pronoun_cn}{first_meaning}"
        else:
            # 普通动词：hablo → 我说
            cn = f"{pronoun_cn}{first_meaning}"

        lines.append((form, cn))

    return lines


def process_file(filepath):
    """处理单个教材文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    new_lines = []
    modified = False

    for line in lines:
        # 匹配: 动词 中文翻译 [变位1, 变位2, ...]（分隔符可能是空格或Tab）
        m = re.match(r'^(\S+)\s+(.+?)\s*\[([^\]]+)\]\s*$', line)
        if m:
            verb = m.group(1)
            meaning = m.group(2)
            forms_str = m.group(3)
            forms = [f.strip() for f in forms_str.split(",")]

            if len(forms) == 6:
                # 拆成独立条目
                entries = unpack_verb_line(verb, meaning, forms)
                for entry_verb, entry_meaning in entries:
                    new_lines.append(f"{entry_verb}\t{entry_meaning}")
                modified = True
                continue

        new_lines.append(line)

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))
        return True
    return False


def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.txt")))
    total = 0
    for fp in files:
        fname = os.path.basename(fp)
        if process_file(fp):
            print(f"  ✓ {fname}")
            total += 1

    print(f"\nDone: {total} files modified.")


if __name__ == "__main__":
    main()
