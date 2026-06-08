"""
西班牙语陪练程序
Terminal-based Spanish language drill program.
教材从 教材/ 目录下的 .txt 文件加载。不联网，不持久化。
"""

import sys
import os
import glob
import tempfile
import time
import threading
import random
from collections import deque

# -- 依赖检测 ----------------------------------------------
HAS_TTS = False
HAS_AUDIO = False
TTS_VOICE_ES = None   # 西语语音
TTS_VOICE_ZH = None   # 中文语音
TTS_LOCK = threading.Lock()

try:
    import win32com.client
    _sapi = win32com.client.Dispatch("SAPI.SpVoice")
    _voices = _sapi.GetVoices()
    for i in range(_voices.Count):
        v = _voices.Item(i)
        name = v.GetDescription()
        lang = v.GetAttribute("Language")
        if "sabina" in name.lower() or "español" in name.lower():
            TTS_VOICE_ES = v
            print(f"[TTS] 西语语音：{name}", flush=True)
        elif "huihui" in name.lower() or (lang and "804" in str(lang)):
            TTS_VOICE_ZH = v
            print(f"[TTS] 中文语音：{name}", flush=True)
    if TTS_VOICE_ES is None and _voices.Count > 0:
        TTS_VOICE_ES = _voices.Item(0)
        print(f"[TTS] 西语使用默认语音：{TTS_VOICE_ES.GetDescription()}", flush=True)
    HAS_TTS = True
except Exception as e:
    print(f"[TTS] 初始化失败：{e}", flush=True)

try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO = True
except Exception:
    pass

# 录音临时目录
TEMP_DIR = tempfile.mkdtemp(prefix='spanish_drill_')
SAMPLE_RATE = 22050
REC_CHUNKS = []          # 录音数据块列表
REC_STREAM = None        # 录音流

# -- 教材加载 ----------------------------------------------

TEXTBOOK_DIR = os.path.join(os.path.dirname(__file__), "教材")
TEXTBOOK = None   # 当前加载的教材数据：{"name": ..., "vocab": [...], "sentences": [...], "grammar": [...]}


def parse_textbook(filepath):
    """解析教材文件，返回 {name, vocab, sentences, grammar}"""
    name = os.path.splitext(os.path.basename(filepath))[0]
    result = {"name": name, "vocab": [], "sentences": [], "grammar": []}

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    section = None
    grammar_entries = []  # 暂存正在构建的语法点

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 区段标记
        if line.startswith("# 生词"):
            section = "vocab"
            continue
        elif line.startswith("# 例句"):
            section = "sentence"
            continue
        elif line.startswith("# 语法点"):
            section = "grammar"
            continue
        elif line.startswith("#"):
            continue  # 注释行跳过

        if section == "vocab":
            # 格式：西语 中文（第一个空格分隔）
            parts = line.split(None, 1)
            if len(parts) == 2:
                result["vocab"].append({"es": parts[0], "zh": parts[1]})

        elif section == "sentence":
            # 格式：西语句子 中文翻译
            # 用 ". " 或 "? " 或 "! " 作为西语句子结束标记来分割
            sep_idx = -1
            for sep in [". ", "? ", "! ", ".\" ", ".\t", "?\t", "!\t", "\t", "  "]:
                idx = line.find(sep)
                if idx > 5:  # 确保分隔符不在开头
                    sep_idx = idx + len(sep) - 1
                    break
            if sep_idx == -1:
                # fallback: 第一个句号后的空格
                dot = line.find(". ")
                if dot > 5:
                    sep_idx = dot + 1

            if sep_idx > 5:
                es_text = line[:sep_idx].strip()
                zh_text = line[sep_idx:].strip()
                result["sentences"].append({"es": es_text, "zh": zh_text})

        elif section == "grammar":
            # 两种格式：
            #   01-08: 标题行 → 说明行 → 例句序号行 → 下一个标题行
            #   01-09: ## 标题行 → 多行说明 → 对应例句：X
            if line.startswith("## "):
                grammar_entries.append({"title": line[3:].strip(), "desc_lines": [], "examples_str": ""})
            elif line.startswith("对应例句：") or line.startswith("对应例句:"):
                if grammar_entries:
                    grammar_entries[-1]["examples_str"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif not grammar_entries:
                grammar_entries.append({"title": line, "desc_lines": [], "examples_str": ""})
            else:
                last = grammar_entries[-1]
                stripped = line.replace("，", ",").replace("、", ",")
                is_index_line = all(p.strip().isdigit() for p in stripped.split(",") if p.strip())
                # 如果已有 examples_str，且当前行不是 ##、不是数字行 → 新语法点开始（01-08 格式）
                if last.get("examples_str") and not is_index_line:
                    grammar_entries.append({"title": line, "desc_lines": [], "examples_str": ""})
                elif is_index_line:
                    last["examples_str"] = stripped
                else:
                    if last.get("desc_lines") is not None:
                        last.setdefault("desc_lines", []).append(line)
                    else:
                        last["desc"] = last.get("desc", "") + line + "\n"

    # 解析语法点例句序号
    for g in grammar_entries:
        indices = []
        examples_str = g.get("examples_str", "")
        if g.get("desc_lines"):
            g["desc"] = "\n".join(g["desc_lines"])
        examples_str = examples_str.replace("，", ",").replace("、", ",")
        for part in examples_str.split(","):
            part = part.strip()
            if part.isdigit():
                indices.append(int(part) - 1)  # 转为 0-based
        result["grammar"].append({
            "title": g["title"],
            "desc": g.get("desc", ""),
            "examples": indices,
        })

    return result


def scan_textbooks():
    """扫描教材目录，返回按文件名排序的教材列表"""
    if not os.path.isdir(TEXTBOOK_DIR):
        return []
    files = glob.glob(os.path.join(TEXTBOOK_DIR, "*.txt"))
    files.sort()
    textbooks = []
    for fp in files:
        try:
            tb = parse_textbook(fp)
            textbooks.append(tb)
        except Exception as e:
            print(f"[警告] 跳过 {os.path.basename(fp)}：{e}", flush=True)
    return textbooks


def select_textbook():
    """教材选择菜单，返回用户选择的教材或 None（退出）"""
    textbooks = scan_textbooks()

    if not textbooks:
        print("\n教材目录为空，请先在 教材/ 下放入 .txt 文件。")
        print("教材格式参见 教材管理-交互设计.md\n")
        return None

    if len(textbooks) == 1:
        tb = textbooks[0]
        print(f"\n自动加载教材：{tb['name']}（{len(tb['vocab'])}个生词 / {len(tb['sentences'])}条例句 / {len(tb['grammar'])}个语法点）\n")
        return tb

    # 多教材选择
    print("\n" + "=" * 36)
    print("          西班牙语陪练")
    print("=" * 36)
    print("  请选择教材：\n")
    for i, tb in enumerate(textbooks, 1):
        n_grammar = len(tb["grammar"])
        grammar_str = f"{n_grammar}个语法点" if n_grammar > 0 else "无语法点"
        print(f"  [{i}] {tb['name']}（{len(tb['vocab'])}个生词 / {len(tb['sentences'])}条例句 / {grammar_str}）")
    print("\n  [Q] 退出")
    print("=" * 36)

    while True:
        choice = wait_key("请选择 > ")
        if choice == "Q":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(textbooks):
                return textbooks[idx]
        except ValueError:
            pass
        print("  无效选项，请重新选择。")


# -- 音频工具 ----------------------------------------------

def _tts_speak_with_voice(text, voice):
    """用指定语音朗读（加锁，支持多线程）"""
    if not HAS_TTS:
        return
    try:
        # 子线程需要先初始化 COM
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        with TTS_LOCK:
            sp = win32com.client.Dispatch("SAPI.SpVoice")
            sp.Voice = voice
            sp.Rate = 1
            sp.Volume = 100
            sp.Speak(text, 0)
    except Exception as e:
        print(f"[TTS] 朗读失败：{e}", flush=True)


def tts_speak(text):
    """西语 TTS 朗读"""
    if not TTS_VOICE_ES:
        return
    _tts_speak_with_voice(text, TTS_VOICE_ES)


def tts_speak_zh(text):
    """中文 TTS 朗读"""
    if not TTS_VOICE_ZH:
        # 无中文语音时静默跳过（模式 2 屏幕已有中文显示）
        return
    _tts_speak_with_voice(text, TTS_VOICE_ZH)


def tts_speak_async(text):
    """西语 TTS 朗读（后台线程）"""
    if not TTS_VOICE_ES:
        return
    t = threading.Thread(target=tts_speak, args=(text,), daemon=True)
    t.start()


def tts_speak_zh_async(text):
    """中文 TTS 朗读（后台线程）"""
    if not TTS_VOICE_ZH:
        return
    t = threading.Thread(target=tts_speak_zh, args=(text,), daemon=True)
    t.start()


def _audio_callback(indata, frames, time_info, status):
    """InputStream 回调：累积录音数据"""
    if status:
        return
    REC_CHUNKS.append(indata.copy())


def start_recording():
    """开始录音：打开 InputStream 持续录制"""
    global REC_CHUNKS, REC_STREAM
    if not HAS_AUDIO:
        return None
    REC_CHUNKS = []
    try:
        REC_STREAM = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='float32',
            callback=_audio_callback)
        REC_STREAM.start()
    except Exception:
        REC_STREAM = None
    return REC_STREAM


def stop_and_playback(_unused=None):
    """停止录音，拼接并回放"""
    global REC_CHUNKS, REC_STREAM
    if not HAS_AUDIO:
        return
    try:
        if REC_STREAM:
            REC_STREAM.stop()
            REC_STREAM.close()
            REC_STREAM = None
    except Exception:
        pass
    if REC_CHUNKS:
        try:
            recording = np.concatenate(REC_CHUNKS)
            if len(recording) > 0:
                sd.play(recording, SAMPLE_RATE)
                sd.wait()
        except Exception:
            pass
    REC_CHUNKS = []


def cleanup_temp_files():
    """清理录音临时目录"""
    try:
        remaining = os.listdir(TEMP_DIR)
        for f in remaining:
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except Exception:
                pass
        os.rmdir(TEMP_DIR)
    except Exception:
        pass


# -- 练习队列管理 ------------------------------------------

class PracticeQueue:
    """管理一轮练习的词/句队列和正确计数"""

    def __init__(self, items, key_fn=lambda x: x["es"]):
        self._items = {key_fn(item): {"data": item, "streak": 0} for item in items}
        self._queue = deque(item for item in items)
        self._key_fn = key_fn

    @property
    def empty(self):
        return len(self._queue) == 0

    @property
    def remaining(self):
        return len(self._queue)

    def next(self):
        """取出队首项"""
        if self._queue:
            return self._queue[0]
        return None

    def advance(self):
        """队首项出队（通过后调用）"""
        if self._queue:
            self._queue.popleft()

    def mark_correct(self, item):
        """标记答对一次。连续两次对则移除，否则排到队尾"""
        key = self._key_fn(item)
        entry = self._items[key]
        entry["streak"] += 1
        self._queue.popleft()  # 从队首移除
        if entry["streak"] < 2:
            self._queue.append(item)  # 排到队尾巩固
        # streak >= 2: 永久移除（不再 append）

    def mark_wrong(self, item):
        """答错：重置计数，排到队尾"""
        key = self._key_fn(item)
        self._items[key]["streak"] = 0
        self._queue.popleft()
        self._queue.append(item)

    def mark_skip(self, item):
        """跳过：永久移出本轮练习，不再出现"""
        key = self._key_fn(item)
        self._items[key]["streak"] = 0
        self._queue.popleft()
        # 不再 append——永久移除

    def snapshot_passed(self):
        """返回当前已通过（streak>=2）的所有词/句的 key"""
        return {k for k, v in self._items.items() if v["streak"] >= 2}


# -- UI 工具 -----------------------------------------------

def print_menu():
    """打印主菜单（stdout 约定 A）"""
    print()
    print("=" * 36)
    print("          西班牙语陪练  ")
    print("=" * 36)
    print("  [1] 听西语说中文")
    print("  [2] 听中文说西语")
    print("  [3] 听写")
    print("  [4] 跟读")
    print("  [5] 混着来")
    print("  [G] 语法讲解")
    print("  [Q] 退出")
    print("=" * 36)
    sys.stdout.flush()


def wait_key(prompt="> "):
    """等待单字符输入，返回大写"""
    print(prompt, end="", flush=True)
    try:
        ch = sys.stdin.readline().strip().upper()
        return ch
    except (EOFError, KeyboardInterrupt):
        return "Q"


def wait_line(prompt="> "):
    """等待一行输入"""
    print(prompt, end="", flush=True)
    try:
        line = sys.stdin.readline().strip()
        return line
    except (EOFError, KeyboardInterrupt):
        return "Q"


# -- 模式实现 ----------------------------------------------

def mode_1_listen_es_say_zh():
    """模式 1：听西语说中文"""
    print("\n[模式1] 听西语说中文 — S=别再问我  R=重听  Q=退出\n")
    sys.stdout.flush()

    # 合并生词和例句为一个池
    items = [{"type": "word", "es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    items += [{"type": "sentence", "es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    pq = PracticeQueue(items, key_fn=lambda x: x["es"])

    while not pq.empty:
        item = pq.next()
        _run_es_to_zh_item(item, pq)


def mode_2_listen_zh_say_es():
    """模式 2：听中文说西语"""
    print("\n[模式2] 听中文说西语 — S=别再问我  R=重听  Q=退出\n")
    sys.stdout.flush()

    items = [{"type": "word", "es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    items += [{"type": "sentence", "es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    pq = PracticeQueue(items, key_fn=lambda x: x["es"])

    while not pq.empty:
        item = pq.next()
        _run_zh_to_es_item(item, pq)


def _run_es_to_zh_item(item, pq):
    """模式 1 的单题循环：念西语 → 用户说中文 → 回放 → 播答案 → 自判"""
    es_text = item["es"]
    zh_text = item["zh"]

    # TTS 念两遍西语，让用户熟悉发音
    print(f"   听原音（第1遍）：{es_text}")
    sys.stdout.flush()
    tts_speak(es_text)
    time.sleep(0.3)
    print(f"   听原音（第2遍）：{es_text}")
    sys.stdout.flush()
    tts_speak(es_text)
    time.sleep(0.3)

    # 录音
    print("   请说出中文意思，说完按 Enter…")
    sys.stdout.flush()
    start_recording()
    user_input = wait_line("  > ")
    cmd = user_input.upper().strip() if user_input else ""

    if cmd == "Q":
        stop_and_playback()
        return "quit"
    if cmd == "S":
        stop_and_playback()
        pq.mark_skip(item)
        return
    if cmd == "R":
        stop_and_playback()
        tts_speak(es_text)
        start_recording()
        user_input = wait_line("  > ")
        cmd = user_input.upper().strip() if user_input else ""
        if cmd in ("Q", "S"):
            stop_and_playback()
            if cmd == "Q":
                return "quit"
            pq.mark_skip(item)
            return

    # 回放录音
    stop_and_playback()
    print("   你的录音回放完毕")
    sys.stdout.flush()

    # 播正确答案
    print(f"  [OK] 正确答案：{es_text} → {zh_text}")
    sys.stdout.flush()
    tts_speak(es_text)

    # 自判
    judge = wait_key("  答对了吗？[Y=对 / N=错 / S=别再问我 / Q=退出] > ")
    if judge == "Q":
        return "quit"
    elif judge == "N":
        pq.mark_wrong(item)
    elif judge == "S":
        pq.mark_skip(item)
    else:
        pq.mark_correct(item)
    print(f"  剩余：{pq.remaining} 题\n")
    sys.stdout.flush()


def _run_zh_to_es_item(item, pq):
    """模式 2 的单题循环：念中文 → 用户说西语 → 回放 → 播答案 → 自判"""
    es_text = item["es"]
    zh_text = item["zh"]

    # 朗读中文（用中文语音）
    print(f"   {zh_text}")
    sys.stdout.flush()
    tts_speak_zh(zh_text)

    # 录音
    print("   请说出对应的西语，说完按 Enter…")
    sys.stdout.flush()
    start_recording()
    user_input = wait_line("  > ")
    cmd = user_input.upper().strip() if user_input else ""

    if cmd == "Q":
        stop_and_playback()
        return "quit"
    if cmd == "S":
        stop_and_playback()
        pq.mark_skip(item)
        return
    if cmd == "R":
        stop_and_playback()
        tts_speak_zh(zh_text)
        start_recording()
        user_input = wait_line("  > ")
        cmd = user_input.upper().strip() if user_input else ""
        if cmd in ("Q", "S"):
            stop_and_playback()
            if cmd == "Q":
                return "quit"
            pq.mark_skip(item)
            return

    # 回放
    stop_and_playback()
    print("   你的录音回放完毕")
    sys.stdout.flush()

    # 正确答案
    print(f"  [OK] 正确答案：{es_text}")
    sys.stdout.flush()
    tts_speak(es_text)

    # 自判
    judge = wait_key("  答对了吗？[Y=对 / N=错 / S=别再问我 / Q=退出] > ")
    if judge == "Q":
        return "quit"
    elif judge == "N":
        pq.mark_wrong(item)
    elif judge == "S":
        pq.mark_skip(item)
    else:
        pq.mark_correct(item)
    print(f"  剩余：{pq.remaining} 题\n")
    sys.stdout.flush()


# -- 模式 3：听写（纯键盘，自动化测试的主要目标） ----------

def mode_3_dictation():
    """模式 3：听写。程序念西语单词，用户键盘拼写，自动判罚"""
    print("\n[听写模式] 请输入单词拼写，按S跳过，按Q返回菜单")
    print("-" * 36 + "\n")
    sys.stdout.flush()

    items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    pq = PracticeQueue(items, key_fn=lambda x: x["es"])

    while not pq.empty:
        item = pq.next()
        es_text = item["es"]

        # stdout 约定 C：展示当前单词
        print(f"当前单词：{es_text}")
        sys.stdout.flush()

        # TTS 朗读（后台，不阻塞输入）
        tts_speak_async(es_text)

        # 等待用户输入拼写
        user_input = wait_line("> ")
        cmd = user_input.strip()

        if cmd.upper() == "Q":
            print()  # 空行分隔
            sys.stdout.flush()
            return
        if cmd.upper() == "S":
            pq.mark_skip(item)
            print(f"  已跳过，剩余：{pq.remaining} 题\n")
            sys.stdout.flush()
            continue

        # 判罚拼写
        if cmd.strip() == es_text:
            # 正确 → stdout 约定 D
            pq.mark_correct(item)
            print(f"[OK] 正确！")
            print(f"  剩余：{pq.remaining} 题\n")
            sys.stdout.flush()
        else:
            # 错误 → stdout 约定 E：显示正确拼写
            pq.mark_wrong(item)
            print(f"[NG] 错误，正确拼写：{es_text}")
            print(f"  剩余：{pq.remaining} 题\n")
            sys.stdout.flush()
            tts_speak_async(es_text)

    # 本轮结束
    print("-- 本轮听写结束，所有单词已通过！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


# -- 模式 4：跟读 ------------------------------------------

def mode_4_shadowing():
    """模式 4：跟读。念西语句子 → 用户跟读 → 交替播放对比"""
    print("\n[跟读模式] 跟读西语句子，对比发音 — 按S跳过 按Q退出\n")
    sys.stdout.flush()

    items = [{"type": "sentence", "es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    pq = PracticeQueue(items, key_fn=lambda x: x["es"])

    while not pq.empty:
        item = pq.next()
        es_text = item["es"]

        _shadow_one(es_text, item, pq)


def _shadow_one(es_text, item, pq):
    """跟读一句"""
    while True:
        # TTS 念两遍原句，让用户熟悉发音
        print(f"   请听原句（第1遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text)
        time.sleep(0.3)
        print(f"   请听原句（第2遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text)
        time.sleep(0.3)

        # 录音跟读
        print("   请跟读… 说完按 Enter")
        sys.stdout.flush()
        start_recording()
        user_input = wait_line("  > ")
        cmd = user_input.upper().strip() if user_input else ""

        if cmd == "Q":
            stop_and_playback()
            return "quit"
        if cmd == "S":
            stop_and_playback()
            pq.mark_skip(item)
            return

        # 对比：先播你的录音，再播一遍原句
        print("  -- 你的录音 --")
        sys.stdout.flush()
        stop_and_playback()
        time.sleep(0.5)
        print("  -- 原句 --")
        sys.stdout.flush()
        tts_speak(es_text)

        # 自判
        judge = wait_key("  跟读满意吗？[Y=满意 / N=再来一次 / S=别再问我 / Q=退出] > ")
        if judge == "Q":
            return "quit"
        elif judge == "S":
            pq.mark_skip(item)
            return
        elif judge == "N":
            continue  # 立即重试同一句
        else:
            pq.mark_correct(item)
            print(f"  剩余：{pq.remaining} 句\n")
            sys.stdout.flush()
            return


# -- 模式 5：混着来 ------------------------------------------

def mode_5_mixed():
    """模式 5：随机混合模式 1、2、3 的题型"""
    print("\n[混着来模式] 随机混合听西说中、听中说西、听写\n")
    sys.stdout.flush()

    items = [{"es": v["es"], "zh": v["zh"], "type": "word"} for v in TEXTBOOK["vocab"]]
    items += [{"es": s["es"], "zh": s["zh"], "type": "sentence"} for s in TEXTBOOK["sentences"]]
    pq = PracticeQueue(items, key_fn=lambda x: x["es"])

    modes = ["es→zh", "zh→es", "dictation"]

    while not pq.empty:
        item = pq.next()
        mode = random.choice(modes)

        if mode == "dictation" and item.get("type") == "sentence":
            mode = random.choice(["es→zh", "zh→es"])

        if mode == "dictation":
            # 听写
            es_text = item["es"]
            print(f"[听写] 当前单词：{es_text}")
            sys.stdout.flush()
            tts_speak_async(es_text)
            user_input = wait_line("> ")
            cmd = user_input.strip()
            if cmd.upper() == "Q":
                print()
                return
            if cmd.upper() == "S":
                pq.mark_skip(item)
                print(f"  已跳过，剩余：{pq.remaining} 题\n")
                sys.stdout.flush()
                continue
            if cmd.strip() == es_text:
                pq.mark_correct(item)
                print(f"[OK] 正确！剩余：{pq.remaining} 题\n")
                sys.stdout.flush()
            else:
                pq.mark_wrong(item)
                print(f"[NG] 错误，正确拼写：{es_text}")
                print(f"  剩余：{pq.remaining} 题\n")
                sys.stdout.flush()
                tts_speak_async(es_text)
        elif mode == "es→zh":
            result = _run_es_to_zh_item(item, pq)
            if result == "quit":
                return
        else:
            result = _run_zh_to_es_item(item, pq)
            if result == "quit":
                return

    print("-- 本轮混着来结束！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


# -- 语法讲解 ----------------------------------------------

def mode_g_grammar():
    """语法讲解模式"""
    grammar = TEXTBOOK["grammar"]

    while True:
        # 无语法点
        if not grammar:
            print("\n" + "=" * 40)
            print("            语法讲解")
            print("=" * 40)
            print("  本教材没有语法点。")
            print("  [Q] 返回主菜单")
            print("=" * 40)
            sys.stdout.flush()
            wait_key("> ")
            return

        # stdout 约定 F：展示语法点列表（含编号）
        print("\n" + "=" * 40)
        print("            语法讲解")
        print("=" * 40)
        for i, g in enumerate(grammar, 1):
            print(f"  [{i}] {g['title']}")
        print("  [Q] 返回主菜单")
        print("=" * 40)
        sys.stdout.flush()

        choice = wait_key("请选择语法点（输入编号）> ")
        if choice == "Q":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(grammar):
                _show_grammar_detail(idx)
        except ValueError:
            pass


def _show_grammar_detail(idx):
    """展示单个语法点的详情和例句"""
    g = TEXTBOOK["grammar"][idx]
    sentences = TEXTBOOK["sentences"]
    print(f"\n-- {g['title']} --")
    print(g['desc'])
    print()
    print("例句：")
    for ei in g['examples']:
        if ei < len(sentences):
            s = sentences[ei]
            print(f"  - {s['es']}")
            print(f"    {s['zh']}")
            print()
    sys.stdout.flush()

    # 朗读例句
    for ei in g['examples']:
        if ei < len(sentences):
            tts_speak(sentences[ei]['es'])

    # 子菜单
    while True:
        cmd = wait_key("[R] 重听例句  [Q] 返回语法列表 > ")
        if cmd == "Q":
            return
        elif cmd == "R":
            for ei in g['examples']:
                if ei < len(sentences):
                    tts_speak(sentences[ei]['es'])


# -- 主循环 ------------------------------------------------

def main():
    global TEXTBOOK

    # 选择教材
    TEXTBOOK = select_textbook()
    if TEXTBOOK is None:
        print("\n退出。\n")
        return

    try:
        while True:
            print_menu()
            choice = wait_key("请选择 > ")
            if choice == "1":
                mode_1_listen_es_say_zh()
            elif choice == "2":
                mode_2_listen_zh_say_es()
            elif choice == "3":
                mode_3_dictation()
            elif choice == "4":
                mode_4_shadowing()
            elif choice == "5":
                mode_5_mixed()
            elif choice == "G":
                mode_g_grammar()
            elif choice == "Q":
                print("\nAdiós! \n")
                break
            else:
                print("  无效选项，请重新选择。")
                sys.stdout.flush()
    finally:
        cleanup_temp_files()


if __name__ == "__main__":
    main()
