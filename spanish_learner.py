#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
西班牙语词汇与语法学习助手
================================================
- 解析教材内容，提取语法规则和生词
- 过滤噪音问句（如"播放音频"），只关注提问单词的问句
- 听觉优先的间隔重复记忆系统
"""

import json
import os
import re
import sys
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --- 配置 ---
BASE_DIR = Path(__file__).parent / "spanish_data"
GRAMMAR_FILE = BASE_DIR / "grammar.json"
VOCAB_FILE = BASE_DIR / "vocabulary.json"

# SRS 复习间隔（天）
SRS_INTERVALS = [1, 3, 7, 14, 30, 60]

# 噪音模式 —— 需要跳过的问句
NOISE_PATTERNS = [
    r"请播放音频",
    r"播放音频",
    r"播放录音",
    r"请跟读",
    r"跟读",
    r"听录音",
    r"听写",
    r"Escucha\s+y\s+repite",
    r"Listen\s+and\s+repeat",
    r"Escucha\s+el\s+audio",
    r"Repite\s+las?\s+frases",
    r"请拼写出.*复数形式",
    r"请拼写出.*阴性形式",
    r"请拼写出.*阴性复数",
    r"请选择.*的性",
    r"请填写.*变位表",
    r"的陈述式现在时",
    r"的阴性形式怎么拼写",
    r"的阴性复数形式",
    r"做练习",
    r"完成练习",
    r"打开书",
    r"翻到第",
    r"看图",
    r"小组讨论",
    r"两人一组",
    r"角色扮演",
    r"Completa\s+las?\s+frases",
    r"Lee\s+el\s+texto",
    r"Lee\s+y\s+traduce",
    r"Contesta\s+las?\s+preguntas",
]

# 中西词汇对照表
CN_TO_ES = {
    "教、教授": "enseñar",
    "语言": "lengua",
    "舌、舌头": "lengua",
    "大学、综合大学": "universidad",
    "大学": "universidad",
    "这个、这些": "este",
    "国家": "país",
    "哪里、哪儿": "dónde",
    "哪里": "dónde",
    "现在、此刻、如今、而今": "ahora",
    "现在": "ahora",
    "你们的": "vuestro",
    "de和el的缩合": "del",
    "男朋友": "novio",
    "女朋友": "novia",
    "老师": "profesor",
    "朋友（女性）": "amiga",
    "朋友": "amiga",
    "小伙子": "chico",
    "我们的": "nuestra",
    "诸位、你们": "ustedes",
    "你们": "ustedes",
    "我教": "enseño",
    "你教": "enseñas",
    "我们在": "estamos",
    "他们在": "están",
    "叫": "llama",
    "她": "ella",
}

ES_TO_CN = {v: k for k, v in CN_TO_ES.items()}

# 虚词（跳过，不纳入生词）
FUNCTION_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "a", "al", "por", "para", "con",
    "sin", "sobre", "entre", "y", "o", "pero", "que",
    "es", "son", "no", "sí", "se",
    "me", "te", "le", "nos", "os", "les", "lo",
    "mi", "tu", "su", "mis", "tus", "sus",
    "yo", "tú", "él", "ella", "usted", "nosotros",
    "este", "esta", "ese", "esa", "aquel", "aquella",
    "muy", "más", "menos", "bien", "mal",
    "qué", "cómo", "dónde", "cuándo", "quién",
    "está", "están",
}

# 专名（跳过）
PROPER_NAMES = {"ricardo", "rosa", "gonzález", "elena", "china"}


# ============================================================
#  语法存储
# ============================================================

class GrammarStore:

    def __init__(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        if GRAMMAR_FILE.exists():
            with open(GRAMMAR_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"topics": []}

    def _save(self):
        with open(GRAMMAR_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add(self, topic, rule, examples=None):
        entry = {
            "topic": topic.strip(),
            "rule": rule.strip(),
            "examples": examples or [],
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        for t in self.data["topics"]:
            if t["topic"] == entry["topic"] and t["rule"] == entry["rule"]:
                return False
        self.data["topics"].append(entry)
        self._save()
        return True

    def list_all(self):
        return self.data["topics"]

    def search(self, keyword):
        kw = keyword.lower()
        return [
            t for t in self.data["topics"]
            if kw in t["topic"].lower()
            or kw in t["rule"].lower()
            or any(kw in ex.lower() for ex in t["examples"])
        ]


# ============================================================
#  词汇存储 + 间隔重复
# ============================================================

class VocabularyStore:

    def __init__(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        if VOCAB_FILE.exists():
            with open(VOCAB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"words": []}

    def _save(self):
        with open(VOCAB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_word(self, spanish, meaning, context="", source=""):
        spanish = spanish.strip().rstrip(".,;:!¿¡?")
        for w in self.data["words"]:
            if w["spanish"].lower() == spanish.lower():
                if context and context not in w["contexts"]:
                    w["contexts"].append(context)
                if not w["meaning"] and meaning:
                    w["meaning"] = meaning.strip()
                self._save()
                return False
        entry = {
            "spanish": spanish,
            "meaning": meaning.strip(),
            "contexts": [context] if context else [],
            "source": source,
            "srs_level": 0,
            "next_review": datetime.now().strftime("%Y-%m-%d"),
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "review_count": 0,
        }
        self.data["words"].append(entry)
        self._save()
        return True

    def get_due_words(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return [w for w in self.data["words"] if w["next_review"] <= today]

    def get_new_words(self):
        return [w for w in self.data["words"] if w["srs_level"] == 0]

    def review(self, spanish, remembered):
        for w in self.data["words"]:
            if w["spanish"].lower() == spanish.lower():
                if remembered:
                    w["srs_level"] = min(w["srs_level"] + 1, len(SRS_INTERVALS))
                    days = SRS_INTERVALS[w["srs_level"] - 1]
                else:
                    w["srs_level"] = 0
                    days = 0
                w["next_review"] = (
                    datetime.now() + timedelta(days=days)
                ).strftime("%Y-%m-%d")
                w["review_count"] += 1
                self._save()
                return days
        return None

    def list_all(self):
        return sorted(self.data["words"], key=lambda w: w["next_review"])

    def stats(self):
        words = self.data["words"]
        return {
            "total": len(words),
            "new": len([w for w in words if w["srs_level"] == 0]),
            "due_today": len(self.get_due_words()),
            "mastered": len([w for w in words if w["srs_level"] >= len(SRS_INTERVALS)]),
        }


# ============================================================
#  教材解析器
# ============================================================

class TextbookParser:

    @staticmethod
    def is_noise(text):
        for pat in NOISE_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _is_valid_spanish_word(word):
        if len(word) < 2:
            return False
        if not re.search(r"[a-záéíóúñü]", word, re.IGNORECASE):
            return False
        if re.match(r"^[\d\s.,;:!\?¿¡\-]+$", word):
            return False
        return True

    @staticmethod
    def extract_vocab(text):
        """从教材问题中提取生词。"""
        lines = text.strip().split("\n")

        # 构建词性列表
        word_types = "名词|动词|形容词|副词|代词|连词|缩写|冠词|句子"

        # 模式1: XXX"西语词"是什么意思？
        meaning_pat = re.compile(
            r"(?:" + word_types + r")"
            r"[“‘\"]([\wáéíóúñüÁÉÍÓÚÑÜ]+)[”’\"]\s*是什么意思"
        )

        # 模式2: XXX"中文"用西班牙语怎么拼写？
        spell_pat = re.compile(
            r"(?:阴性|阳性)?\s*(?:" + word_types + r")"
            r"[“‘\"]([^”’\"]+)[”’\"]\s*用西班牙语怎么拼写"
        )

        first_pass = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if TextbookParser.is_noise(line):
                continue

            # 匹配 "西语词"是什么意思？
            m = meaning_pat.search(line)
            if m:
                spanish = m.group(1).strip().rstrip(".,;:!¿¡?")
                if TextbookParser._is_valid_spanish_word(spanish):
                    key = spanish.lower()
                    if key not in first_pass:
                        first_pass[key] = {
                            "spanish": spanish,
                            "meaning": "",
                            "context": line,
                        }
                continue

            # 匹配 "中文意思"用西班牙语怎么拼写？
            m = spell_pat.search(line)
            if m:
                chinese = m.group(1).strip()
                clean = re.sub(r"[（(][^)）]*[)）]", "", chinese).strip()
                clean = re.sub(r"常见搭配：.*$", "", clean).strip()
                clean = clean.rstrip("，,.。")
                if clean and not re.search(r"[a-záéíóúñ]", clean, re.IGNORECASE):
                    spanish = CN_TO_ES.get(chinese) or CN_TO_ES.get(clean)
                    if spanish:
                        key = spanish.lower()
                        if key in first_pass:
                            if not first_pass[key]["meaning"]:
                                first_pass[key]["meaning"] = clean
                        else:
                            first_pass[key] = {
                                "spanish": spanish,
                                "meaning": clean,
                                "context": line,
                            }
                continue

        # 补全缺失的意思
        for key, entry in first_pass.items():
            if not entry["meaning"] and key in ES_TO_CN:
                entry["meaning"] = ES_TO_CN[key]

        # 过滤
        result = []
        for key, entry in first_pass.items():
            if key in PROPER_NAMES:
                continue
            if key in FUNCTION_WORDS:
                continue
            if not entry["meaning"]:
                continue
            if len(entry["spanish"]) < 2:
                continue
            result.append(entry)

        return result


# ============================================================
#  TTS 语音合成（Windows SAPI5 西语语音）
# ============================================================

class SpanishTTS:

    def __init__(self):
        self.engine = None
        self.spanish_voice_id = None
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            voices = self.engine.getProperty("voices")
            for v in voices:
                name = v.name.lower()
                lang = ""
                if hasattr(v, "languages") and v.languages:
                    l0 = v.languages[0]
                    lang = l0.decode() if isinstance(l0, bytes) else str(l0)
                if any(tag in name + lang for tag in
                       ["spanish", "español", "espa", "es-", "es_", "esp"]):
                    self.spanish_voice_id = v.id
                    break
            if self.spanish_voice_id:
                self.engine.setProperty("voice", self.spanish_voice_id)
            self.engine.setProperty("rate", 140)
            print("  语音: " + str(self.spanish_voice_id or "默认"))
        except Exception as e:
            print("  语音初始化警告: " + str(e))
            self.engine = None

    def speak(self, text, slow=False):
        if not self.engine:
            print("  [语音不可用]")
            return
        try:
            self.engine.setProperty("rate", 100 if slow else 140)
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            print("  [语音错误: " + str(e) + "]")

    def speak_word(self, word, times=2):
        if not self.engine:
            return
        try:
            self.engine.setProperty("rate", 140)
            self.engine.say(word)
            self.engine.runAndWait()
            if times >= 2:
                time.sleep(0.3)
                self.engine.setProperty("rate", 100)
                self.engine.say(word)
                self.engine.runAndWait()
        except Exception as e:
            print("  [语音错误: " + str(e) + "]")


# ============================================================
#  交互式主程序
# ============================================================

class SpanishLearner:

    def __init__(self):
        self.grammar = GrammarStore()
        self.vocab = VocabularyStore()
        self.tts = SpanishTTS()
        self.parser = TextbookParser()

    def run(self):
        print("\n" + "=" * 56)
        print("  🇪🇸  西班牙语词汇与语法学习助手")
        print("  听觉优先 · 间隔重复 · 教材解析")
        print("=" * 56)
        self._show_stats()
        self._main_loop()

    def _show_stats(self):
        s = self.vocab.stats()
        print("  📚 词汇: {}个 | 🆕 新词: {}个 | 📅 今日待复习: {}个 | ⭐ 已掌握: {}个".format(
            s["total"], s["new"], s["due_today"], s["mastered"]))
        print("  📖 语法: {}条".format(len(self.grammar.list_all())))

    def _main_loop(self):
        while True:
            print("\n" + "-" * 40)
            print("[1] 📥 导入教材内容（自动解析语法+生词）")
            print("[2] 📝 查看全部生词")
            print("[3] 🎧 复习今日单词（听觉优先）")
            print("[4] 🔊 快速听全部生词（磨耳朵）")
            print("[5] ➕ 手动添加生词")
            print("[6] 📖 查看语法规则")
            print("[7] 🔍 搜索语法")
            print("[8] 📊 学习统计")
            print("[9] 👋 退出")
            print("-" * 40)

            try:
                choice = input("请选择 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n¡Hasta luego! 👋")
                break

            if choice == "1":
                self._import_content()
            elif choice == "2":
                self._list_vocab()
            elif choice == "3":
                self._review_mode()
            elif choice == "4":
                self._quick_listen()
            elif choice == "5":
                self._add_word_manual()
            elif choice == "6":
                self._list_grammar()
            elif choice == "7":
                self._search_grammar()
            elif choice == "8":
                self._show_stats()
            elif choice == "9":
                print("¡Hasta luego! 👋")
                break
            else:
                print("无效选项，请重新选择。")

    # ---- 1. 导入教材内容 ----

    def _import_content(self):
        print("\n📥 请粘贴教材内容（输入空行结束，或输入 . 结束）:")
        lines = []
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break
            if line == "" or line.strip() == ".":
                break
            lines.append(line)
        text = "\n".join(lines)

        if not text.strip():
            print("未输入任何内容。")
            return

        print("\n🔍 正在解析...")
        result = self.parser.extract_vocab(text)

        vocab_count = 0
        for word in result:
            if self.vocab.add_word(
                word["spanish"], word["meaning"],
                word.get("context", ""), "教材"
            ):
                vocab_count += 1
                print("  ✅ {} —— {}".format(word["spanish"], word["meaning"]))

        print("\n新增 {} 个生词。".format(vocab_count))

        if vocab_count > 0:
            print("\n🎧 听新词发音...")
            for word in result:
                if word["spanish"]:
                    print("  🔊 {} —— {}".format(word["spanish"], word["meaning"]))
                    self.tts.speak_word(word["spanish"])
                    time.sleep(0.5)
        else:
            print("（未发现新词，可能已存在或为噪音问句）")

    # ---- 2. 查看生词 ----

    def _list_vocab(self):
        words = self.vocab.list_all()
        if not words:
            print("\n暂无生词。请先导入教材内容。")
            return
        print("\n📝 全部生词 ({}个):".format(len(words)))
        print("-" * 60)
        for i, w in enumerate(words, 1):
            if w["srs_level"] == 0:
                status = "🆕"
            elif w["srs_level"] >= len(SRS_INTERVALS):
                status = "⭐"
            else:
                status = "L{}".format(w["srs_level"])
            today = datetime.now().strftime("%Y-%m-%d")
            due = " ⚠️今天!" if w["next_review"] <= today else ""
            print("  {:3}. {} {:<20} {:<15} 下次复习: {}{}".format(
                i, status, w["spanish"], w["meaning"],
                w["next_review"], due))
            if w["contexts"]:
                print("       📖 " + "; ".join(w["contexts"][:2]))

    # ---- 3. 听觉优先复习 ----

    def _review_mode(self):
        due = self.vocab.get_due_words()
        if not due:
            print("\n🎉 今天没有需要复习的单词！")
            new = self.vocab.get_new_words()
            if new:
                ans = input("有 {} 个新词未学，是否现在学习？(y/n) ".format(len(new))).strip().lower()
                if ans == "y":
                    due = new
                else:
                    return
            else:
                return

        print("\n🎧 开始复习 ({} 个单词) —— 听觉优先模式".format(len(due)))
        print("  先听发音 → 回忆意思 → 按键看答案 → 自我评估")
        print("  (输入 q 退出复习)\n")

        random.shuffle(due)
        correct = 0
        total = 0

        for i, word in enumerate(due, 1):
            print("\n" + "─" * 40)
            print("[{}/{}]".format(i, len(due)))

            print("🔊 听发音...")
            self.tts.speak_word(word["spanish"], times=2)

            ans = input("  按 Enter 看答案 (q=退出, r=再听一遍) > ").strip().lower()
            while ans == "r":
                print("  🔊 再听一遍...")
                self.tts.speak_word(word["spanish"], times=2)
                ans = input("  按 Enter 看答案 > ").strip().lower()
            if ans == "q":
                break

            print("  ✅ {} —— {}".format(word["spanish"], word["meaning"]))
            if word["contexts"]:
                print("     📖 " + word["contexts"][0])

            rating = input("  记住了吗？ (y=记住了/n=没记住/s=有点印象) > ").strip().lower()
            total += 1
            if rating in ("y", ""):
                days = self.vocab.review(word["spanish"], remembered=True)
                correct += 1
                print("  👍 已掌握！{} 天后复习。".format(days))
            elif rating == "s":
                self.vocab.review(word["spanish"], remembered=False)
                print("  🔄 巩固一下，再听一遍...")
                self.tts.speak_word(word["spanish"], times=3)
                print("  📅 今天还会出现。")
            else:
                self.vocab.review(word["spanish"], remembered=False)
                print("  📅 标记为重新学习，今天会再次出现。")
                self.tts.speak_word(word["spanish"], times=3)

            time.sleep(0.5)

        if total > 0:
            print("\n📊 本轮: {}/{} 正确".format(correct, total))
        else:
            print("\n📊 未复习任何单词。")

    # ---- 4. 快速听全部 ----

    def _quick_listen(self):
        words = self.vocab.list_all()
        if not words:
            print("\n暂无生词。")
            return
        print("\n🔊 快速播放全部 {} 个生词（磨耳朵）...".format(len(words)))
        print("  (按 Ctrl+C 停止)")
        try:
            for i, w in enumerate(words, 1):
                print("\r  [{}/{}] {} —— {}".format(
                    i, len(words), w["spanish"], w["meaning"]), end="")
                self.tts.speak_word(w["spanish"], times=2)
                time.sleep(0.3)
            print()
        except KeyboardInterrupt:
            print("\n\n⏸️ 已停止。")

    # ---- 5. 手动添加 ----

    def _add_word_manual(self):
        print("\n➕ 手动添加生词")
        spanish = input("  西班牙语: ").strip()
        if not spanish:
            return
        meaning = input("  中文意思: ").strip()
        context = input("  例句/语境 (可选): ").strip()

        if self.vocab.add_word(spanish, meaning, context, "手动"):
            print("  ✅ 已添加: {} —— {}".format(spanish, meaning))
            print("  🔊 听发音...")
            self.tts.speak_word(spanish)
        else:
            print("  ⚠️ '{}' 已存在，已更新语境。".format(spanish))

    # ---- 6. 查看语法 ----

    def _list_grammar(self):
        rules = self.grammar.list_all()
        if not rules:
            print("\n暂无语法规则。")
            return
        print("\n📖 语法规则 ({}条):".format(len(rules)))
        print("=" * 56)
        for i, r in enumerate(rules, 1):
            print("\n  [{}] {}".format(i, r["topic"]))
            rule_text = r["rule"]
            if len(rule_text) > 120:
                rule_text = rule_text[:120] + "..."
            print("      " + rule_text)
            if r["examples"]:
                for ex in r["examples"][:3]:
                    print("      📝 " + ex)

    # ---- 7. 搜索语法 ----

    def _search_grammar(self):
        keyword = input("\n🔍 搜索语法关键词: ").strip()
        if not keyword:
            return
        results = self.grammar.search(keyword)
        if not results:
            print("未找到与 '{}' 相关的语法。".format(keyword))
            return
        print("\n找到 {} 条结果:".format(len(results)))
        for i, r in enumerate(results, 1):
            print("\n  [{}] {}".format(i, r["topic"]))
            print("      " + r["rule"])
            if r["examples"]:
                for ex in r["examples"]:
                    print("      📝 " + ex)


# ============================================================
#  初始化教材词汇
# ============================================================

def import_textbook_vocabulary(vocab):
    """一次性导入教材中的所有生词。"""
    textbook_words = [
        ("novio", "男朋友", "Ricardo es el novio de Rosa."),
        ("novia", "女朋友", "La novia del chico se llama Elena."),
        ("profesor", "老师", "Ella es amiga del profesor González."),
        ("amiga", "朋友（女性）", "Ella es amiga del profesor González."),
        ("chico", "小伙子", "La novia del chico se llama Elena."),
        ("llama", "叫（llamarse变位）", "La novia del chico se llama Elena."),
        ("enseño", "我教（enseñar变位）", "Enseño nuestra lengua en una universidad."),
        ("enseñas", "你教（enseñar变位）", "¿Dónde enseñas vuestra lengua?"),
        ("enseñar", "教、教授", "动词原形 —— 教、教授"),
        ("lengua", "语言；舌、舌头", "¿Dónde enseñas vuestra lengua?"),
        ("universidad", "大学", "en una universidad de este país"),
        ("país", "国家", "en una universidad de este país"),
        ("nuestra", "我们的", "Enseño nuestra lengua en una universidad."),
        ("vuestra", "你们的（阴性）", "¿Dónde enseñas vuestra lengua?"),
        ("vuestro", "你们的（阳性）", "阳性形容词形式"),
        ("este", "这个、这些", "en una universidad de este país"),
        ("estamos", "我们在（estar变位）", "Ahora estamos en China."),
        ("están", "他们在/你们在（estar变位）", "¿Dónde están ustedes?"),
        ("ahora", "现在", "Ahora estamos en China."),
        ("dónde", "哪里", "¿Dónde están ustedes?"),
        ("ustedes", "诸位/你们", "¿Dónde están ustedes?"),
        ("ella", "她", "Ella es amiga del profesor González."),
        ("del", "de+el的缩合", "Ella es amiga del profesor González."),
    ]

    count = 0
    for spanish, meaning, context in textbook_words:
        if vocab.add_word(spanish, meaning, context, "教材"):
            count += 1
    return count


# ============================================================
#  入口
# ============================================================

def main():
    learner = SpanishLearner()

    print("正在初始化内置语法...")
    learner.grammar.add(
        "介词 DE —— 所属关系",
        "介词 de 的主要用法之一是表示所属，用来回答 ¿de quién?（谁的）、"
        "¿de qué?（什么的）等提问。\n"
        "de 后面出现单数阳性定冠词 el 时，必须缩写为 del。",
        [
            "Ricardo es el novio de Rosa. —— 里卡多是罗莎的男朋友。",
            "Enseño nuestra lengua en una universidad de este país. —— 我在这个国家的一所大学教我们的语言。",
            "Ella es amiga del profesor González. —— 她是冈萨雷斯老师的朋友。",
            "La novia del chico se llama Elena. —— 这个小伙子的女朋友叫艾蕾娜。",
        ],
    )
    learner.grammar.add(
        "介词 EN —— 地点",
        "介词 en 的主要用法之一是表示地点，用来回答 ¿dónde?（在哪里）提出的问题。",
        [
            "¿Dónde están ustedes? —— 诸位在哪儿？",
            "Ahora estamos en China. —— 现在我们在中国。",
            "¿Dónde enseñas vuestra lengua? —— 你在哪里教你们的语言？",
            "Enseño nuestra lengua en una universidad de este país. —— 我在这个国家的一所大学教我们的语言。",
        ],
    )
    print("  已加载 2 条语法规则。")

    print("正在导入教材词汇...")
    count = import_textbook_vocabulary(learner.vocab)
    print("  已加载 {} 个生词。".format(count))

    s = learner.vocab.stats()
    print("  合计: {} 词 | {} 新词\n".format(s["total"], s["new"]))

    learner.run()


if __name__ == "__main__":
    main()
