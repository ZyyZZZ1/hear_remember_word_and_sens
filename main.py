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
import difflib
import msvcrt
from collections import deque

# -- 依赖检测 ----------------------------------------------
HAS_TTS = False
HAS_AUDIO = False
TTS_VOICE_ES = None   # 西语语音（SAPI fallback）
TTS_VOICE_ZH = None   # 中文语音（SAPI）
TTS_LOCK = threading.Lock()
PIPER_VOICE_ES = None  # Piper 西语模型（优先使用）
PIPER_MODEL_DIR = os.path.join(os.path.dirname(__file__), "piper_models")

# --- Piper TTS（本地神经网络，自然度优于 SAPI）---
try:
    import numpy as np
    from piper.voice import PiperVoice
    _piper_model = os.path.join(PIPER_MODEL_DIR, "es_ES-carlfm-x_low.onnx")
    _piper_config = os.path.join(PIPER_MODEL_DIR, "es_ES-carlfm-x_low.onnx.json")
    if os.path.exists(_piper_model) and os.path.exists(_piper_config):
        PIPER_VOICE_ES = PiperVoice.load(_piper_model, config_path=_piper_config, use_cuda=False)
        print(f"[TTS] Piper 西语语音：es_ES-carlfm-x_low", flush=True)
        HAS_TTS = True
    else:
        print(f"[TTS] Piper 模型未下载，请运行 download_piper_model.py", flush=True)
except ImportError:
    print(f"[TTS] Piper 未安装，使用 SAPI 后备", flush=True)
except Exception as e:
    print(f"[TTS] Piper 加载失败：{e}", flush=True)

# --- SAPI TTS（后备方案，中文语音）---
try:
    import win32com.client
    _sapi = win32com.client.Dispatch("SAPI.SpVoice")
    _voices = _sapi.GetVoices()
    for i in range(_voices.Count):
        v = _voices.Item(i)
        name = v.GetDescription()
        lang = v.GetAttribute("Language")
        if "huihui" in name.lower() or (lang and "804" in str(lang)):
            TTS_VOICE_ZH = v
            print(f"[TTS] 中文语音：{name}", flush=True)
        elif PIPER_VOICE_ES is None and ("sabina" in name.lower() or "español" in name.lower()):
            TTS_VOICE_ES = v
            print(f"[TTS] 西语语音(SAPI)：{name}", flush=True)
    if PIPER_VOICE_ES is None and TTS_VOICE_ES is None and _voices.Count > 0:
        TTS_VOICE_ES = _voices.Item(0)
        print(f"[TTS] 西语使用默认语音(SAPI)：{TTS_VOICE_ES.GetDescription()}", flush=True)
    HAS_TTS = True
except Exception as e:
    print(f"[TTS] SAPI 初始化失败：{e}", flush=True)

try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO = True
except Exception:
    pass

# 终端颜色
_COLOR_GREEN = '\033[92m'
_COLOR_RED = '\033[91m'
_COLOR_RESET = '\033[0m'

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
    """西语 TTS 朗读（优先 Piper，回退 SAPI）"""
    if PIPER_VOICE_ES:
        try:
            with TTS_LOCK:
                audio = b""
                for chunk in PIPER_VOICE_ES.synthesize_stream_raw(text):
                    audio += chunk
                if HAS_AUDIO and audio:
                    import io
                    import wave
                    import sounddevice as sd
                    audio_np = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32767.0
                    sd.play(audio_np, samplerate=22050)
                    sd.wait()
        except Exception as e:
            print(f"[TTS Piper] 朗读失败：{e}", flush=True)
            # fall through to SAPI
        else:
            return
    # SAPI fallback
    if not TTS_VOICE_ES:
        return
    _tts_speak_with_voice(text, TTS_VOICE_ES)


def tts_speak_zh(text):
    """中文 TTS 朗读"""
    if not TTS_VOICE_ZH:
        return
    _tts_speak_with_voice(text, TTS_VOICE_ZH)


def tts_speak_async(text):
    """西语 TTS 朗读（后台线程）"""
    if PIPER_VOICE_ES or TTS_VOICE_ES:
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
    """停止录音，拼接并回放（按任意键打断，不影响测试管道）"""
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
                # 后台线程播放，主线程轮询按键打断
                playback_done = threading.Event()
                def _play():
                    try:
                        sd.play(recording, SAMPLE_RATE)
                        sd.wait()
                    except Exception:
                        pass
                    finally:
                        playback_done.set()
                t = threading.Thread(target=_play, daemon=True)
                t.start()
                print("  正在播放录音，按任意键跳过...", end="", flush=True)
                while not playback_done.is_set():
                    if msvcrt.kbhit():
                        msvcrt.getch()
                        sd.stop()
                        break
                    time.sleep(0.1)
                print("\r" + " " * 50 + "\r", end="", flush=True)  # 清除提示行
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

GROUP_SIZE = 5   # 每组 5 个词/句

class PracticeQueue:
    """管理一轮练习的词/句队列。答对即过，答错回队尾，跳过即过。"""

    def __init__(self, items):
        self._queue = deque(item for item in items)

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

    def mark_correct(self, _item=None):
        """答对：永久移除"""
        if self._queue:
            self._queue.popleft()

    def mark_wrong(self, _item=None):
        """答错：排到队尾"""
        if self._queue:
            item = self._queue.popleft()
            self._queue.append(item)

    def mark_skip(self, _item=None):
        """跳过：永久移出"""
        if self._queue:
            self._queue.popleft()


# -- 分组会话（模式 1 用）----------------------------------

class GroupSession:
    """管理一组练习的状态：当前位置、通过/保留、历史回退"""

    def __init__(self, items):
        self.items = list(items)           # 有序列表
        self._passed = set()               # 已通过的 item key
        self._pos = 0                      # 当前位置（index）
        self._history = []                 # 回退栈（index 列表）

    @staticmethod
    def _key(item):
        return item.get("es", str(item))

    @property
    def current(self):
        return self.items[self._pos]

    @property
    def current_index(self):
        """1-based 位置"""
        return self._pos + 1

    @property
    def total(self):
        return len(self.items)

    @property
    def all_passed(self):
        return len(self._passed) == len(self.items)

    @property
    def passed_count(self):
        return len(self._passed)

    def is_passed(self, item=None):
        if item is None:
            item = self.current
        return self._key(item) in self._passed

    def pass_current(self):
        """当前词通过"""
        self._passed.add(self._key(self.current))
        self._history.append(self._pos)
        self._advance()

    def keep_current(self):
        """保留稍后：不标记通过，仅前进（绕回时还会遇到）"""
        self._history.append(self._pos)
        self._advance()

    def _advance(self):
        """移动到下一个非 passed 的词，支持绕回"""
        for _ in range(len(self.items)):
            self._pos = (self._pos + 1) % len(self.items)
            if self._key(self.items[self._pos]) not in self._passed:
                return
        # 全部 passed，pos 留在原地

    def go_back(self):
        """回到上一词。返回 (item, was_passed)；无历史返回 (None, False)"""
        if not self._history:
            return None, False
        prev_pos = self._history.pop()
        prev_item = self.items[prev_pos]
        was_passed = self._key(prev_item) in self._passed
        self._pos = prev_pos
        return prev_item, was_passed

    def unpass(self):
        """把当前词从 passed 中移除，拉回来重练"""
        self._passed.discard(self._key(self.current))


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
    """模式 1：听西语说中文 —— 子菜单选择单词/句子"""
    while True:
        print()
        print("=" * 36)
        print("          [模式1] 听西语说中文")
        print("=" * 36)
        print("  [1] 单词")
        print("  [2] 句子")
        print("  [Q] 返回主菜单")
        print("=" * 36)
        sys.stdout.flush()

        choice = wait_key("请选择 > ")
        if choice == "1":
            _mode_es_to_zh_words()
        elif choice == "2":
            _mode_es_to_zh_sentences()
        elif choice == "Q":
            return
        else:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _mode_es_to_zh_words():
    """听西语说中文——单词池，组菜单 + GroupSession"""
    items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    _run_group_menu_es_to_zh("单词", groups)


def _mode_es_to_zh_sentences():
    """听西语说中文——句子池，组菜单 + GroupSession"""
    items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    _run_group_menu_es_to_zh("句子", groups)


def _run_group_menu_es_to_zh(kind, groups):
    """组菜单：列出每组词/句，用户选组进入练习"""
    while True:
        print()
        print("=" * 36)
        print(f"          [模式1-{kind}] 共 {len(groups)} 组")
        print("=" * 36)
        for gi, group in enumerate(groups, 1):
            words = ", ".join(item["es"] for item in group)
            print(f"  [{gi}] 第 {gi} 组：{words}")
        print("  [B] 返回")
        print("=" * 36)
        sys.stdout.flush()

        choice = wait_key("请选择 > ")
        if choice == "B":
            return
        try:
            gi = int(choice) - 1
            if 0 <= gi < len(groups):
                _run_one_group_es_to_zh(groups, gi, kind)
        except ValueError:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _run_one_group_es_to_zh(groups, gi, kind):
    """单组练习：GroupSession 驱动。groups 是全部组列表，gi 是当前组索引"""
    group = groups[gi]
    total_groups = len(groups)
    gs = GroupSession(group)

    while not gs.all_passed:
        item = gs.current
        es_text = item["es"]
        zh_text = item["zh"]
        passed_info = f"  ✓{gs.passed_count}/{gs.total}" if gs.passed_count > 0 else ""

        # ── 展示 ──
        print(f"\n{'─' * 36}")
        print(f"  第 {gi+1}/{total_groups} 组 · 第 {gs.current_index}/{gs.total} 词  {passed_info}")
        print(f"{'─' * 36}")
        print(f"\n  {es_text}\n")
        sys.stdout.flush()

        # ── TTS 两遍 ──
        print(f"  听原音（第1遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text)
        time.sleep(0.3)
        print(f"  听原音（第2遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text)
        time.sleep(0.3)

        # ── 录音阶段 ──
        qq = _record_phase(es_text)
        if qq == "quit":
            return

        # ── 回放 + 原音对比 + 答案 ──
        stop_and_playback()
        print("  -- 原音对比 --")
        sys.stdout.flush()
        tts_speak(es_text)

        print(f"\n  [答案] {es_text} → {zh_text}\n")
        sys.stdout.flush()
        tts_speak_zh(zh_text)  # 单词用中文语音读出中文释义

        # ── 决策 ──
        result = _decision_pnbr(gs, es_text)
        if result == "quit":
            return

    # 本组通关
    print(f"\n-- 第 {gi+1} 组通关！--")
    sys.stdout.flush()
    time.sleep(0.5)

    # 下一组？
    if gi + 1 < total_groups:
        nxt = wait_key(f"  [Enter] 继续第 {gi+2} 组  [B] 回组菜单  [Q] 退出 > ")
        if nxt == "Q":
            return
        if nxt != "B":
            _run_one_group_es_to_zh(groups, gi + 1, kind)


def _record_phase(es_text):
    """录音阶段：等待用户说完按 Enter。支持 R 重听、Q 退出。
    返回 "quit" 表示退出，否则返回 None。"""
    print("  请说出中文意思，说完按 Enter…")
    sys.stdout.flush()
    start_recording()
    user_input = wait_line("  > ")
    cmd = user_input.strip().upper() if user_input else ""

    if cmd == "Q":
        stop_and_playback()
        return "quit"
    if cmd == "R":
        stop_and_playback()
        tts_speak(es_text)
        time.sleep(0.3)
        tts_speak(es_text)
        start_recording()
        user_input = wait_line("  > ")
        cmd = user_input.strip().upper() if user_input else ""
        if cmd == "Q":
            stop_and_playback()
            return "quit"
    return None


def _decision_pnbr(gs, es_text):
    """P/N/B/R/Q 决策循环。返回 "quit" 表示 Q 退出。"""
    while True:
        choice = wait_key("  [P]通过  [N]保留稍后  [B]上一词  [R]重听  [Q]退出 > ")
        if choice == "P":
            gs.pass_current()
            return None
        elif choice == "N":
            gs.keep_current()
            return None
        elif choice == "R":
            tts_speak(es_text)
            time.sleep(0.3)
            tts_speak(es_text)
            print()
            sys.stdout.flush()
            continue
        elif choice == "B":
            # 回退链：一直退到非 passed 或用户确认
            while True:
                prev_item, was_passed = gs.go_back()
                if prev_item is None:
                    print("  已经是第一个词了")
                    sys.stdout.flush()
                    return None
                if not was_passed:
                    return None  # 外层循环会展示这个词
                sub = wait_key(
                    f"  [上一词] 「{prev_item['es']}」已通关。"
                    f"[Y] 拉回来重新练习  [N] 跳过，继续往前退 > "
                )
                if sub == "Y":
                    gs.unpass()
                    return None
                # N → continue loop, go further back
        elif choice == "Q":
            return "quit"
        else:
            # 按 Enter 或其他键默认 = N（保留稍后）
            gs.keep_current()
            return None


def mode_2_listen_zh_say_es():
    """模式 2：听中文说西语 —— 子菜单选择单词/句子"""
    while True:
        print()
        print("=" * 36)
        print("          [模式2] 听中文说西语")
        print("=" * 36)
        print("  [1] 单词")
        print("  [2] 句子")
        print("  [Q] 返回主菜单")
        print("=" * 36)
        sys.stdout.flush()

        choice = wait_key("请选择 > ")
        if choice == "1":
            _mode_zh_to_es_words()
        elif choice == "2":
            _mode_zh_to_es_sentences()
        elif choice == "Q":
            return
        else:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _mode_zh_to_es_words():
    """听中文说西语——单词池，5个一组"""
    items = [{"type": "word", "es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    for gi, group in enumerate(groups, 1):
        print(f"\n[模式2-单词] 第 {gi}/{len(groups)} 组 — S=跳过  R=重听  Q=退出\n")
        sys.stdout.flush()
        pq = PracticeQueue(group)
        while not pq.empty:
            item = pq.next()
            result = _run_zh_to_es_item(item, pq)
            if result == "quit":
                return
        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部单词通关！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


def _mode_zh_to_es_sentences():
    """听中文说西语——句子池，5句一组"""
    items = [{"type": "sentence", "es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    for gi, group in enumerate(groups, 1):
        print(f"\n[模式2-句子] 第 {gi}/{len(groups)} 组 — S=跳过  R=重听  Q=退出\n")
        sys.stdout.flush()
        pq = PracticeQueue(group)
        while not pq.empty:
            item = pq.next()
            result = _run_zh_to_es_item(item, pq)
            if result == "quit":
                return
        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部句子通关！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


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
    elif judge == "S":
        pq.mark_skip(item)
    elif judge == "Y":
        pq.mark_correct(item)
    else:
        # 按 Enter 或任意键默认 = 错，必须明确按 Y 才算对
        pq.mark_wrong(item)
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
    elif judge == "S":
        pq.mark_skip(item)
    elif judge == "Y":
        pq.mark_correct(item)
    else:
        # 按 Enter 或任意键默认 = 错，必须明确按 Y 才算对
        pq.mark_wrong(item)
    print(f"  剩余：{pq.remaining} 题\n")
    sys.stdout.flush()


# -- 模式 3：听写（子菜单 → 单词/句子）-----------------------

def mode_3_dictation():
    """模式 3：听写子菜单——选择单词听写或句子听写"""
    while True:
        print()
        print("=" * 36)
        print("          [听写模式]")
        print("=" * 36)
        print("  [1] 听写单词")
        print("  [2] 听写句子")
        print("  [Q] 返回主菜单")
        print("=" * 36)
        sys.stdout.flush()

        choice = wait_key("请选择 > ")
        if choice == "1":
            _mode_dictation_words()
        elif choice == "2":
            _mode_dictation_sentences()
        elif choice == "Q":
            return
        else:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _mode_dictation_words():
    """听写单词：5个一组，程序念西语单词，用户键盘拼写，自动判罚"""
    items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    for gi, group in enumerate(groups, 1):
        print(f"\n[听写-单词] 第 {gi}/{len(groups)} 组 — 按S跳过 按Q返回")
        print("-" * 36 + "\n")
        sys.stdout.flush()

        pq = PracticeQueue(group)
        while not pq.empty:
            item = pq.next()
            es_text = item["es"]

            print(f"当前单词：{es_text}")
            sys.stdout.flush()
            tts_speak_async(es_text)

            user_input = wait_line("> ")
            cmd = user_input.strip()

            if cmd.upper() == "Q":
                print()
                sys.stdout.flush()
                return
            if cmd.upper() == "S":
                pq.mark_skip()
                print(f"  已跳过，剩余：{pq.remaining} 题\n")
                sys.stdout.flush()
                continue

            if cmd.strip() == es_text:
                pq.mark_correct()
                print(f"[OK] 正确！")
                print(f"  剩余：{pq.remaining} 题\n")
                sys.stdout.flush()
            else:
                pq.mark_wrong()
                print(f"[NG] 错误，正确拼写：{es_text}")
                print(f"  剩余：{pq.remaining} 题\n")
                sys.stdout.flush()
                tts_speak_async(es_text)

        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部单词通关！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


def _normalize_sentence(text):
    """规范化句子用于比较：去掉所有标点、统一大小写、合并空白"""
    import re
    cleaned = text.strip()
    # 去掉所有标点符号（保留字母、数字、空格）
    cleaned = re.sub(r'[.,:;!?¿¡\-—"\'«»()]', '', cleaned)
    # 合并空白、转小写
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
    return cleaned


def _highlight_diff(original, user_input):
    """逐词对比用户输入和原句，返回带 ANSI 颜色的 (colored_user, colored_original)"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'

    orig_words = original.split()
    user_words = user_input.split()
    orig_norm = [_normalize_sentence(w) for w in orig_words]
    user_norm = [_normalize_sentence(w) for w in user_words]

    sm = difflib.SequenceMatcher(None, orig_norm, user_norm)

    colored_orig_parts = []
    colored_user_parts = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            colored_orig_parts.append(GREEN + ' '.join(orig_words[i1:i2]) + RESET)
            colored_user_parts.append(GREEN + ' '.join(user_words[j1:j2]) + RESET)
        elif tag == 'replace':
            colored_orig_parts.append(RED + ' '.join(orig_words[i1:i2]) + RESET)
            colored_user_parts.append(RED + ' '.join(user_words[j1:j2]) + RESET)
        elif tag == 'delete':
            colored_orig_parts.append(RED + ' '.join(orig_words[i1:i2]) + RESET)
        elif tag == 'insert':
            colored_user_parts.append(RED + ' '.join(user_words[j1:j2]) + RESET)

    colored_orig = ' '.join(colored_orig_parts)
    colored_user = ' '.join(colored_user_parts)
    return colored_user, colored_orig


def _mode_dictation_sentences():
    """听写句子：5句一组，程序念西语句子，用户键盘输入完整句子，自动判罚"""
    items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    for gi, group in enumerate(groups, 1):
        print(f"\n[听写-句子] 第 {gi}/{len(groups)} 组 — 按S跳过 按Q返回")
        print("-" * 36 + "\n")
        sys.stdout.flush()

        pq = PracticeQueue(group)
        while not pq.empty:
            item = pq.next()
            es_text = item["es"]
            zh_text = item["zh"]

            print(f"  中文：{zh_text}")
            sys.stdout.flush()

            tts_speak(es_text)
            time.sleep(0.3)
            tts_speak(es_text)

            user_input = wait_line("> ")
            cmd = user_input.strip()

            if cmd.upper() == "Q":
                print()
                sys.stdout.flush()
                return
            if cmd.upper() == "S":
                pq.mark_skip()
                print(f"  已跳过，剩余：{pq.remaining} 句\n")
                sys.stdout.flush()
                continue
            if cmd.upper() == "R":
                tts_speak(es_text)
                time.sleep(0.3)
                tts_speak(es_text)
                user_input = wait_line("> ")
                cmd = user_input.strip()
                if cmd.upper() == "Q":
                    print()
                    sys.stdout.flush()
                    return
                if cmd.upper() == "S":
                    pq.mark_skip()
                    print(f"  已跳过，剩余：{pq.remaining} 句\n")
                    sys.stdout.flush()
                    continue

            if _normalize_sentence(cmd) == _normalize_sentence(es_text):
                pq.mark_correct()
                print(f"[OK] 正确！")
                print(f"  剩余：{pq.remaining} 句\n")
                sys.stdout.flush()
            else:
                pq.mark_wrong()
                colored_user, colored_orig = _highlight_diff(es_text, cmd)
                print(f"[NG] 错误！")
                print(f"  你的：{colored_user}")
                print(f"  原句：{colored_orig}")
                print(f"  （{_COLOR_GREEN}绿色{_COLOR_RESET}=正确  {_COLOR_RED}红色{_COLOR_RESET}=错误/遗漏）")
                print(f"  剩余：{pq.remaining} 句\n")
                sys.stdout.flush()
                tts_speak_async(es_text)

        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部句子通关！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


# -- 模式 4：跟读 ------------------------------------------

def mode_4_shadowing():
    """模式 4：跟读。5句一组，念西语句子 → 用户跟读 → 交替播放对比"""
    items = [{"type": "sentence", "es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    for gi, group in enumerate(groups, 1):
        print(f"\n[跟读模式] 第 {gi}/{len(groups)} 组 — 按S跳过 按Q退出\n")
        sys.stdout.flush()

        pq = PracticeQueue(group)
        while not pq.empty:
            item = pq.next()
            es_text = item["es"]
            result = _shadow_one(es_text, item, pq)
            if result == "quit":
                return
        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部句子通关！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


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
    """模式 5：5题一组，随机混合模式 1、2、3 的题型（含单词和句子听写）"""
    items = [{"es": v["es"], "zh": v["zh"], "type": "word"} for v in TEXTBOOK["vocab"]]
    items += [{"es": s["es"], "zh": s["zh"], "type": "sentence"} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]

    modes = ["es→zh", "zh→es", "dictation"]

    for gi, group in enumerate(groups, 1):
        print(f"\n[混着来模式] 第 {gi}/{len(groups)} 组 — 随机混合\n")
        sys.stdout.flush()

        pq = PracticeQueue(group)
        while not pq.empty:
            item = pq.next()
            mode = random.choice(modes)
            is_sentence = item.get("type") == "sentence"

            if mode == "dictation":
                es_text = item["es"]
                zh_text = item["zh"]

                if is_sentence:
                    print(f"[听写-句子] 中文：{zh_text}")
                    sys.stdout.flush()
                    tts_speak(es_text)
                    time.sleep(0.3)
                    tts_speak(es_text)
                else:
                    print(f"[听写-单词] 当前单词：{es_text}")
                    sys.stdout.flush()
                    tts_speak_async(es_text)
                user_input = wait_line("> ")
                cmd = user_input.strip()
                if cmd.upper() == "Q":
                    print()
                    return
                if cmd.upper() == "S":
                    pq.mark_skip()
                    print(f"  已跳过，剩余：{pq.remaining} 题\n")
                    sys.stdout.flush()
                    continue

                if is_sentence:
                    correct = _normalize_sentence(cmd) == _normalize_sentence(es_text)
                else:
                    correct = cmd == es_text

                if correct:
                    pq.mark_correct()
                    print(f"[OK] 正确！剩余：{pq.remaining} 题\n")
                    sys.stdout.flush()
                else:
                    pq.mark_wrong()
                    if is_sentence:
                        colored_user, colored_orig = _highlight_diff(es_text, cmd)
                        print(f"[NG] 错误！")
                        print(f"  你的：{colored_user}")
                        print(f"  原句：{colored_orig}")
                        print(f"  （{_COLOR_GREEN}绿色{_COLOR_RESET}=正确  {_COLOR_RED}红色{_COLOR_RESET}=错误/遗漏）")
                    else:
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

        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部混着来通关！--\n")
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
