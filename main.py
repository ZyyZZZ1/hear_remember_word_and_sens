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
import re
import ctypes
from collections import deque

# -- 依赖检测 ----------------------------------------------
HAS_TTS = False
HAS_AUDIO = False
TTS_VOICE_ES = None   # 西语语音（SAPI fallback）
TTS_VOICE_ZH = None   # 中文语音（SAPI fallback）
TTS_LOCK = threading.Lock()
PIPER_VOICES = []          # Piper 西语模型池（随机抽签）
PIPER_MODEL_DIR = os.path.join(os.path.dirname(__file__), "piper_models")
FAVORITES_FILE = os.path.join(os.path.dirname(__file__), "favorites.json")

_PIPER_ES_MODEL_NAMES = [
    "es_ES-davefx-medium",
    "es_ES-sharvard-medium",
    "es_MX-claude-high",
    "es_AR-daniela-high",
]

_PIPER_WORD_SAFE = {"es_ES-davefx-medium", "es_AR-daniela-high"}

_PIPER_BY_NAME = {}

# --- Piper TTS（本地神经网络，自然度优于 SAPI）---
try:
    import numpy as np
    from piper.voice import PiperVoice
    for name in _PIPER_ES_MODEL_NAMES:
        model_path = os.path.join(PIPER_MODEL_DIR, f"{name}.onnx")
        config_path = os.path.join(PIPER_MODEL_DIR, f"{name}.onnx.json")
        if os.path.exists(model_path) and os.path.exists(config_path):
            try:
                voice = PiperVoice.load(model_path, config_path=config_path, use_cuda=False)
                _PIPER_BY_NAME[name] = voice
                PIPER_VOICES.append(voice)
                print(f"[TTS] Piper 西语语音已加载：{name}", flush=True)
                HAS_TTS = True
            except Exception as e:
                print(f"[TTS] Piper {name} 加载失败：{e}", flush=True)
    if not PIPER_VOICES:
        print(f"[TTS] Piper 模型未下载，请运行 download_piper_model.py", flush=True)
except ImportError:
    print(f"[TTS] Piper 未安装，使用 SAPI 后备", flush=True)
except Exception as e:
    print(f"[TTS] Piper 加载失败：{e}", flush=True)

# --- Kokoro TTS（已禁用：太慢）---
KOKORO_PIPELINE = None
_KOKORO_VOICE_DIR = None
print(f"[TTS] Kokoro 已禁用（太慢），中文 TTS 降级为 SAPI", flush=True)


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
        elif not PIPER_VOICES and ("sabina" in name.lower() or "español" in name.lower()):
            TTS_VOICE_ES = v
            print(f"[TTS] 西语语音(SAPI)：{name}", flush=True)
    if not PIPER_VOICES and TTS_VOICE_ES is None and _voices.Count > 0:
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
    result = {"name": name, "vocab": [], "sentences": [], "grammar": [], "vocab_note": ""}

    with open(filepath, "r", encoding="utf-8-sig") as f:
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
            # 格式：西语 中文 —— 以第一个非拉丁/空格字符为界（支持多词短语）
            m = re.match(r'^([a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]+?)\s*([^a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s].*)$', line)
            if m:
                result["vocab"].append({"es": m.group(1).strip(), "zh": m.group(2).strip()})
            else:
                # fallback：按第一个空格分
                parts = line.split(None, 1)
                if len(parts) == 2:
                    result["vocab"].append({"es": parts[0], "zh": parts[1]})
                else:
                    # 非生词行（如"（本课无新增生词）"）→ 保存为备注
                    if result["vocab_note"]:
                        result["vocab_note"] += " " + line
                    else:
                        result["vocab_note"] = line

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


def _build_favorites_textbook():
    """用所有教材的收藏词构建虚拟教材"""
    fav = _load_favorites()
    all_textbooks = scan_textbooks()
    vocab = []
    seen = set()
    for tb in all_textbooks:
        for es_word in fav.get(tb["name"], []):
            for v in tb["vocab"]:
                if v["es"] == es_word and es_word not in seen:
                    entry = dict(v)
                    entry["source_textbook"] = tb["name"]
                    vocab.append(entry)
                    seen.add(es_word)
                    break
    return {
        "name": "收藏集",
        "vocab": vocab,
        "sentences": [],
        "grammar": [],
    }


def _vocab_display(tb):
    """生词展示文本：0个生词时若有备注则用备注替代"""
    n = len(tb["vocab"])
    if n == 0 and tb.get("vocab_note"):
        return tb["vocab_note"]
    return f"{n}个生词"


def select_textbook():
    """教材选择菜单，返回用户选择的教材或 None（退出）"""
    textbooks = scan_textbooks()

    if not textbooks:
        print("\n教材目录为空，请先在 教材/ 下放入 .txt 文件。")
        print("教材格式参见 教材管理-交互设计.md\n")
        return None

    # 构建收藏集
    fav_textbook = _build_favorites_textbook()
    has_fav = len(fav_textbook["vocab"]) > 0

    if len(textbooks) == 1 and not has_fav:
        tb = textbooks[0]
        vocab_str = _vocab_display(tb)
        print(f"\n自动加载教材：{tb['name']}（{vocab_str} / {len(tb['sentences'])}条例句 / {len(tb['grammar'])}个语法点）\n")
        return tb

    # 教材选择
    print("\n" + "=" * 36)
    print("          西班牙语陪练")
    print("=" * 36)
    print("  请选择教材：\n")
    if has_fav:
        print(f"  [*] 收藏集（{len(fav_textbook['vocab'])} 个收藏词）")
    for i, tb in enumerate(textbooks, 1):
        n_grammar = len(tb["grammar"])
        grammar_str = f"{n_grammar}个语法点" if n_grammar > 0 else "无语法点"
        vocab_str = _vocab_display(tb)
        print(f"  [{i}] {tb['name']}（{vocab_str} / {len(tb['sentences'])}条例句 / {grammar_str}）")
    print("\n  [Q] 退出")
    print("=" * 36)

    while True:
        choice = _wait_line_voice(
            _VP_INPUT,
            "请选择（输入教材代码，如 01-16-A；*=收藏集；Q=退出） > ",
        )
        if choice == "Q":
            return None
        if choice == "*" and has_fav:
            return fav_textbook
        for tb in textbooks:
            if tb["name"].upper() == choice:
                return tb
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


_last_voice = None

def _piper_pick(for_sentence=False):
    """选 Piper 模型：句子全用，单词避开 sharvard/claude，避免连续重复"""
    global _last_voice
    if for_sentence:
        pool = list(PIPER_VOICES)
    else:
        safe = [v for n, v in _PIPER_BY_NAME.items() if n in _PIPER_WORD_SAFE]
        pool = list(safe) if safe else list(PIPER_VOICES)
    if len(pool) > 1 and _last_voice is not None:
        pool = [v for v in pool if v is not _last_voice]
    voice = random.choice(pool)
    _last_voice = voice
    return voice


def tts_speak(text, is_sentence=False):
    """西语 TTS 朗读（随机抽 Piper 模型，回退 SAPI）"""
    if PIPER_VOICES:
        voice = _piper_pick(for_sentence=is_sentence)
        try:
            with TTS_LOCK:
                chunks = []
                sr = 16000
                for chunk in voice.synthesize(text):
                    chunks.append(chunk.audio_int16_bytes)
                    sr = chunk.sample_rate
                if chunks and HAS_AUDIO:
                    audio = b"".join(chunks)
                    audio_np = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32767.0
                    pad = int(sr * 0.2)
                    audio_np = np.concatenate([np.zeros(pad, dtype=np.float32), audio_np, np.zeros(pad, dtype=np.float32)])
                    sd.play(audio_np, samplerate=sr)
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


# 持久化 SAPI 中文语音对象（用于打断）
_SP_ZH = None
_SP_ZH_LOCK = threading.Lock()


def _get_sp_zh():
    """获取/初始化 SAPI 中文语音对象（共享，可被外部 purge）"""
    global _SP_ZH
    with _SP_ZH_LOCK:
        if _SP_ZH is None:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            _SP_ZH = win32com.client.Dispatch("SAPI.SpVoice")
            _SP_ZH.Voice = TTS_VOICE_ZH
            _SP_ZH.Rate = 1
            _SP_ZH.Volume = 100
        return _SP_ZH


def _stop_audio():
    """立即停止所有正在播放的 TTS（sounddevice + SAPI purge）"""
    try:
        sd.stop()
    except Exception:
        pass
    try:
        if _SP_ZH is not None:
            _SP_ZH.Speak("", 3)  # SPF_PURGEBEFORESPEAK
    except Exception:
        pass


def _safe_kbhit():
    """安全的 msvcrt.kbhit（无控制台时返回 False）"""
    try:
        return msvcrt.kbhit()
    except Exception:
        return False


def _speak_zh_no_poll(text):
    """朗读中文（不轮询按键，调用方负责打断）。阻塞直到朗读完成或被外部 purge。"""
    use_kokoro = KOKORO_PIPELINE and _KOKORO_VOICE_DIR and not _is_pure_chinese(text)
    if use_kokoro:
        voice_files = [f for f in os.listdir(_KOKORO_VOICE_DIR)
                       if f.startswith('z') and f.endswith('.pt')]
        if voice_files:
            voice_path = os.path.join(_KOKORO_VOICE_DIR, random.choice(voice_files))
            try:
                with TTS_LOCK:
                    for _, _, audio in KOKORO_PIPELINE(text, voice=voice_path, speed=1.0):
                        if audio is not None:
                            audio_np = audio.numpy() if hasattr(audio, 'numpy') else np.array(audio)
                            pad = int(24000 * 0.2)
                            audio_np = np.concatenate([np.zeros(pad, dtype=audio_np.dtype), audio_np, np.zeros(pad, dtype=audio_np.dtype)])
                            sd.play(audio_np, samplerate=24000)
                            sd.wait()
                            return
            except Exception as e:
                print(f"[TTS Kokoro] 朗读失败：{e}", flush=True)
    if not TTS_VOICE_ZH:
        return
    try:
        sp = _get_sp_zh()
        sp.Speak(text, 1)  # SPF_ASYNC: 不阻塞线程，允许跨线程 purge
        while True:
            try:
                if sp.Status.RunningState == 1:  # SRSEDone
                    break
            except Exception:
                break
            time.sleep(0.05)
    except Exception:
        pass


def tts_speak_zh(text):
    """中文 TTS 朗读（带打断支持）
    - 纯中文 → SAPI（Kokoro 不参与，避开自回归慢路径）
    - 中英混合 → Kokoro，失败再回退 SAPI
    """
    done = threading.Event()
    def _speak():
        try:
            _speak_zh_no_poll(text)
        except Exception:
            pass
        finally:
            done.set()
    t = threading.Thread(target=_speak, daemon=True)
    t.start()
    print("  （按任意键跳过中文朗读）", end="", flush=True)
    while not done.is_set():
        if _safe_kbhit():
            msvcrt.getch()
            _stop_audio()
            break
        time.sleep(0.1)
    print("\r" + " " * 36 + "\r", end="", flush=True)


def tts_speak_async(text, is_sentence=False):
    """西语 TTS 朗读（后台线程）"""
    if PIPER_VOICES or TTS_VOICE_ES:
        t = threading.Thread(target=tts_speak, args=(text, is_sentence), daemon=True)
        t.start()


def tts_speak_zh_async(text):
    """中文 TTS 朗读（后台线程，不轮询按键）"""
    if KOKORO_PIPELINE or TTS_VOICE_ZH:
        t = threading.Thread(target=_speak_zh_no_poll, args=(text,), daemon=True)
        t.start()


def _speak_zh_async_silent(text):
    """后台朗读中文（不轮询按键、不打印提示）。返回 Thread 对象。"""
    t = threading.Thread(target=_speak_zh_no_poll, args=(text,), daemon=True)
    t.start()
    return t


def _tts_speak_es_interruptible(es_text):
    """西语 TTS 播放，期间任意键打断"""
    done = threading.Event()
    def _play():
        try:
            tts_speak(es_text)  # is_sentence=False → 只用单词安全模型
        except Exception:
            pass
        finally:
            done.set()
    t = threading.Thread(target=_play, daemon=True)
    t.start()
    while not done.is_set():
        if msvcrt.kbhit():
            msvcrt.getch()
            sd.stop()
            return True  # 被打断
        time.sleep(0.1)
    return False  # 正常播完


def _minimize_window():
    """最小化当前终端窗口"""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    except Exception:
        pass


def _memory_import_loop(es_text, zh_text):
    """记忆导入：固定 8 遍（2次西语+1次中文），任意键可打断"""
    print(f"    （按任意键跳过当前词）", end="", flush=True)
    interrupted = False
    for i in range(1, 9):
        print(f"\n    [{i}/8] {es_text}")
        sys.stdout.flush()
        # 西语第1遍
        if _tts_speak_es_interruptible(es_text):
            interrupted = True
            break
        time.sleep(0.15)
        if msvcrt.kbhit():
            msvcrt.getch()
            interrupted = True
            break
        # 西语第2遍
        if _tts_speak_es_interruptible(es_text):
            interrupted = True
            break
        time.sleep(0.2)
        if msvcrt.kbhit():
            msvcrt.getch()
            interrupted = True
            break
        # 中文1遍
        tts_speak_zh(zh_text)
        time.sleep(0.3)
        if msvcrt.kbhit():
            msvcrt.getch()
            interrupted = True
            break
        # 第一次完整播放后，最小化窗口，让用户只专注听
        if i == 1:
            _minimize_window()
    print()
    if interrupted:
        print("    （已跳过）")
    sys.stdout.flush()


def _spelling_quiz_phase(es_text, zh_text):
    """记忆导入打字测验：8遍循环结束后，让用户输入拼写和中文。
    非阻塞设计——输错不阻止过题，2次错误后展示答案并给抄写机会。
    按R重听当前词，按Enter跳过，按Q退出。"""
    import re

    # ── 提示音：用中文TTS唤醒用户注意力 ──
    print(f"\n  {'─' * 30}")
    print(f"  🔔 请准备打字！")
    sys.stdout.flush()
    tts_speak_zh_async("请准备输入西语")
    time.sleep(0.15)

    # ── 拼写测验 ──
    spelling_attempts = 0
    spelling_done = False
    while spelling_attempts < 2 and not spelling_done:
        print(f"  请输入单词拼写（按R重听 / 按Enter跳过 / 按Q退出）:")
        sys.stdout.flush()
        user_input = _wait_line_voice("请输入单词拼写", "  > ")
        cmd = user_input.strip()

        if cmd.upper() == "Q":
            return "quit"
        if cmd.upper() == "R":
            print(f"  [重听] {es_text}")
            sys.stdout.flush()
            tts_speak(es_text)
            time.sleep(0.15)
            continue
        if cmd == "":
            print(f"  （已跳过拼写）")
            sys.stdout.flush()
            spelling_done = True
            break

        if _strip_accents(cmd.lower()) == _strip_accents(es_text.lower()):
            print(f"  {_COLOR_GREEN}✓ 拼写正确！{_COLOR_RESET}")
            sys.stdout.flush()
            spelling_done = True
        else:
            spelling_attempts += 1
            if spelling_attempts == 1:
                print(f"  {_COLOR_RED}✗ 不对，再试试？{_COLOR_RESET}")
                sys.stdout.flush()
            else:
                # 第2次还错：展示正确答案（错/漏字符标红），让用户抄一遍
                colored = _highlight_char_diff(es_text, cmd)
                print(f"  你的输入：{cmd}")
                print(f"  正确拼写：{colored}")
                print(f"  （{_COLOR_GREEN}绿色{_COLOR_RESET}=正确  {_COLOR_RED}红色{_COLOR_RESET}=错漏）")
                print(f"  请照着输入一遍：")
                sys.stdout.flush()
                tts_speak(es_text)
                copy_input = _wait_line_voice("请照着输入正确拼写", "  > ").strip()
                if copy_input.upper() == "Q":
                    return "quit"
                if _strip_accents(copy_input.lower()) == _strip_accents(es_text.lower()):
                    print(f"  ✓ 好的！")
                else:
                    colored2 = _highlight_char_diff(es_text, copy_input)
                    print(f"  没关系，正确的拼写是：{colored2}")
                sys.stdout.flush()
                spelling_done = True

    time.sleep(0.2)

    # ── 中文释义测验 ──
    zh_attempts = 0
    zh_done = False
    zh_variants = [v.strip() for v in re.split(r'[,，、；;]', zh_text) if v.strip()]
    zh_first = zh_variants[0] if zh_variants else zh_text

    while zh_attempts < 2 and not zh_done:
        print(f"  请输入中文意思（按R重听 / 按Enter跳过 / 按Q退出）:")
        sys.stdout.flush()
        user_input = _wait_line_voice("请输入中文意思", "  > ")
        cmd = user_input.strip()

        if cmd.upper() == "Q":
            return "quit"
        if cmd.upper() == "R":
            tts_speak(es_text)
            time.sleep(0.15)
            tts_speak_zh(zh_first)
            continue
        if cmd == "":
            print(f"  （已跳过中文）")
            sys.stdout.flush()
            zh_done = True
            break

        # 模糊匹配：精确命中 或 用户输入包含在释义中 或 释义包含在用户输入中
        matched = any(
            cmd == v or v in cmd or cmd in v
            for v in zh_variants
        )
        if not matched:
            # 字符重叠度检测（处理"美丽" vs "美丽的"这种情况）
            common = set(cmd) & set(zh_text.replace(",", "").replace("，", "").replace(" ", ""))
            total = set(zh_text.replace(",", "").replace("，", "").replace(" ", ""))
            if total and len(common) >= len(total) * 0.5:
                matched = True

        if matched:
            print(f"  {_COLOR_GREEN}✓ 中文正确！{_COLOR_RESET}")
            sys.stdout.flush()
            zh_done = True
        else:
            zh_attempts += 1
            if zh_attempts == 1:
                print(f"  {_COLOR_RED}✗ 不对，再试试？{_COLOR_RESET}")
                sys.stdout.flush()
            else:
                print(f"  中文答案：{_COLOR_GREEN}{zh_text}{_COLOR_RESET}")
                print(f"  请照着输入一遍：")
                sys.stdout.flush()
                tts_speak_zh(zh_first)
                copy_input = _wait_line_voice("请照着输入中文意思", "  > ").strip()
                if copy_input.upper() == "Q":
                    return "quit"
                if copy_input == zh_text or any(copy_input == v for v in zh_variants):
                    print(f"  ✓ 好的！")
                else:
                    print(f"  没关系，记住即可：{zh_text}")
                sys.stdout.flush()
                zh_done = True

    print()
    sys.stdout.flush()
    return None


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
                rec_pad = int(SAMPLE_RATE * 0.2)
                recording = np.concatenate([np.zeros(rec_pad, dtype=recording.dtype), recording, np.zeros(rec_pad, dtype=recording.dtype)])
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
        """当前词通过，返回 True 表示绕回起点"""
        self._passed.add(self._key(self.current))
        self._history.append(self._pos)
        return self._advance()

    def keep_current(self):
        """保留稍后：不标记通过，仅前进。返回 True 表示绕回起点"""
        self._history.append(self._pos)
        return self._advance()

    def _advance(self):
        """移动到下一个非 passed 的词，支持绕回。返回 True 表示已绕回"""
        old_pos = self._pos
        for _ in range(len(self.items)):
            self._pos = (self._pos + 1) % len(self.items)
            if self._key(self.items[self._pos]) not in self._passed:
                return self._pos <= old_pos
        return False

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

    def reset_all(self):
        """重置所有词为未通过状态，回到第一个词"""
        self._passed.clear()
        self._pos = 0


# -- UI 工具 -----------------------------------------------

# -- 收藏夹 -----------------------------------------------

def _load_favorites():
    """加载收藏夹（按教材名分组的西语单词列表）"""
    import json
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_favorites(fav):
    """保存收藏夹"""
    import json
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(fav, f, ensure_ascii=False, indent=2)


def _get_favorites():
    """获取当前教材的收藏列表（西语单词 str 列表）"""
    if TEXTBOOK is None:
        return []
    fav = _load_favorites()
    return fav.get(TEXTBOOK["name"], [])


def _toggle_favorite(es_text):
    """切换收藏状态，返回 True=已收藏, False=已取消"""
    if TEXTBOOK is None:
        return False
    fav = _load_favorites()

    # 收藏集是虚拟教材，实际收藏保存在原始教材的 key 下
    key = TEXTBOOK["name"]
    if key == "收藏集":
        source = None
        for v in TEXTBOOK.get("vocab", []):
            if v["es"] == es_text:
                source = v.get("source_textbook")
                break
        if source is None:
            return False
        key = source

    if key not in fav:
        fav[key] = []
    if es_text in fav[key]:
        fav[key].remove(es_text)
        _save_favorites(fav)
        return False
    else:
        fav[key].append(es_text)
        _save_favorites(fav)
        return True


# -- 句子实词收藏 ------------------------------------------

_ALL_VOCAB = None  # 全部教材词汇缓存（含屈折变化展开）


def _vocab_morph_expand(word):
    """将教材词汇展开为多种词形，存入索引。"""
    forms = {word}
    # 代词式动词：bañarse → 额外存 bañar（去-se）
    if word.endswith('se') and len(word) > 3:
        forms.add(word[:-2])
    # 动词：bañar → 额外存词干 bañ（匹配变位形 baña, baño, bañe 等）
    for v_end in ('ar', 'er', 'ir'):
        if word.endswith(v_end) and len(word) > len(v_end) + 1:
            forms.add(word[:-len(v_end)])
    # 名词/形容词复数还原：hermanos→hermano, dientes→diente, papeles→papel
    if word.endswith('s') and len(word) > 3:
        forms.add(word[:-1])                     # 元音+s：casas→casa, dientes→diente
    if word.endswith('es') and len(word) > 4:
        forms.add(word[:-2])                     # 辅音+es：papeles→papel
    return forms


def _token_match(token, vocab):
    """判断句中 token 是否命中词汇表（支持去复数 + 去变位词尾）。"""
    if token in vocab:
        return True
    # 去复数候选：dientes→diente, hermanos→hermano, papeles→papel
    if token.endswith('s') and len(token) > 3 and token[:-1] in vocab:
        return True
    if token.endswith('es') and len(token) > 4 and token[:-2] in vocab:
        return True
    # 去变位词尾：baña→bañ(ar), come→com(er), vive→viv(ir)
    if token.endswith(('a', 'e', 'o')) and len(token) > 2:
        stem = token[:-1]
        for suf in ('ar', 'er', 'ir', 'arse', 'erse', 'irse'):
            if stem + suf in vocab:
                return True
    return False


def _token_to_lemma(token, vocab):
    """将句中 token 还原为词汇表中的原形；如果找不到原形则返回 token 本身。"""
    if token in vocab:
        return token
    if token.endswith('s') and len(token) > 3 and token[:-1] in vocab:
        return token[:-1]
    if token.endswith('es') and len(token) > 4 and token[:-2] in vocab:
        return token[:-2]
    if token.endswith(('a', 'e', 'o')) and len(token) > 2:
        stem = token[:-1]
        for suf in ('ar', 'er', 'ir', 'arse', 'erse', 'irse'):
            if stem + suf in vocab:
                return stem + suf
    return token


def _favorite_words_from_sentence(es_text):
    """从单个句子里提取可收藏单词。"""
    import re

    global _ALL_VOCAB
    if _ALL_VOCAB is None:
        _ALL_VOCAB = set()
        for tb in scan_textbooks():
            for v in tb.get("vocab", []):
                for t in re.findall(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]+", v.get("es", "")):
                    t = t.lower()
                    if len(t) > 1:
                        _ALL_VOCAB |= _vocab_morph_expand(t)

    already_fav = set(_get_favorites())
    words = []
    seen = set()
    for t in re.findall(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]+", es_text):
        t = t.lower()
        if len(t) <= 1 or t in seen:
            continue
        seen.add(t)
        if _token_match(t, _ALL_VOCAB):
            lemma = _token_to_lemma(t, _ALL_VOCAB)
            if lemma not in already_fav and lemma not in seen:
                words.append(lemma)

    if not words:
        print("  本句中无可收藏的单词。")
        sys.stdout.flush()
        return 0

    n = len(words)
    print(f"  本句生词（共 {n} 个）：")
    for i, w in enumerate(words):
        print(f"    [{i+1}] {w}")

    print(f"  [0] 全选  [Enter] 跳过")
    sys.stdout.flush()

    choice = _wait_line_voice(
        f"本句有{n}个生词，输入编号，空格分隔，0全选，回车跳过",
        "  输入编号（空格分隔）> ",
    )
    if not choice.strip():
        return 0

    selected = set()
    if choice.strip() == '0':
        selected = set(range(n))
    else:
        for part in choice.split():
            try:
                idx = int(part) - 1
                if 0 <= idx < n:
                    selected.add(idx)
            except ValueError:
                pass

    if not selected:
        return 0

    fav = _load_favorites()
    key = TEXTBOOK['name']
    if key not in fav:
        fav[key] = []

    added = 0
    for idx in sorted(selected):
        word = words[idx]
        if word not in fav[key]:
            fav[key].append(word)
            added += 1

    _save_favorites(fav)
    print(f"  ★ 已收藏 {added} 个单词")
    sys.stdout.flush()
    return added


def print_menu():
    """打印主菜单（stdout 约定 A）"""
    print()
    print("=" * 36)
    print("          西班牙语陪练  ")
    print("=" * 36)
    print("  [0] 记忆导入")
    print("  [1] 听西语说中文")
    print("  [2] 听中文说西语")
    print("  [3] 听写")
    print("  [4] 跟读")
    print("  [5] 混着来")
    print("  [G] 语法讲解")
    print("  [T] 选教材")
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


# -- 语音提醒机制 ----------------------------------------------

# 是否启用语音提醒。非交互环境（stdin 被重定向，例如测试）自动关闭。
VOICE_REMINDER_ENABLED = sys.stdin.isatty() and HAS_TTS

# 等待时长与重试次数（可用环境变量调节）
# 间隔故意放久一点（20s），避免频繁打扰；重念次数保持 4 次不变
VOICE_REMINDER_INTERVAL = int(os.environ.get("VOICE_REMINDER_INTERVAL", "20"))
VOICE_REMINDER_MAX = int(os.environ.get("VOICE_REMINDER_MAX", "4"))

# 测试标记：环境变量 TEST_MARKER=1 时打印 [TTS START]/[TTS STOP]/[KEY]/[ECHO]/[DISCARD]/[CMD] 等观察行
_TEST_MARKER_ON = os.environ.get("TEST_MARKER", "").lower() in ("1", "true", "yes", "on")


def _marker(kind, detail=""):
    if not _TEST_MARKER_ON:
        return
    if detail:
        print(f"[{kind}] {detail}", flush=True)
    else:
        print(f"[{kind}]", flush=True)


# 语音提示词常量（短促版：只提示"该做什么"，不念菜单选项）
_VP_PROMPT = "请选择菜单"           # 通用菜单提示
_VP_INPUT = "请输入"                 # 通用输入提示
_VP_GRAMMAR_INPUT = "请选择语法点"   # 语法点列表
_VP_RECORDING = "请按回车结束录音"   # 录音中提示


def _clear_line(width=80):
    """清除当前行（屏幕底部倒计时用）"""
    print("\r" + " " * width + "\r", end="", flush=True)


def _wait_key_voice(voice_text, screen_prompt="> ", max_attempts=None, interval=None):
    """等待单键输入，同时播放短促语音提醒。
    - 按键立即停语音、立即返回（大写）
    - 单独按 Enter → 返回空串 = 默认动作
    - interval 秒 × max_attempts 次没动 → 之后静默等，不再念
    - 在非交互环境（stdin PIPE）自动 fallback 到普通 readline
    """
    if max_attempts is None:
        max_attempts = VOICE_REMINDER_MAX
    if interval is None:
        interval = VOICE_REMINDER_INTERVAL

    print(screen_prompt, end="", flush=True)
    sys.stdout.flush()

    if not VOICE_REMINDER_ENABLED or not voice_text:
        try:
            return sys.stdin.readline().strip().upper()
        except (EOFError, KeyboardInterrupt):
            return "Q"

    while _safe_kbhit():
        _r = msvcrt.getch().decode('utf-8', errors='ignore')
        _marker("DISCARD", _r if _r and _r not in ('\r', '\n') else "(Enter)")

    for attempt in range(1, max_attempts + 1):
        _speak_zh_async_silent(voice_text)
        _marker("TTS START", voice_text)

        deadline = time.time() + interval
        while time.time() < deadline:
            if _safe_kbhit():
                ch = msvcrt.getch().decode('utf-8', errors='ignore')
                if ch in ('\r', '\n'):
                    ch = ''
                _marker("KEY", ch if ch else "(Enter)")
                _stop_audio()
                _marker("TTS STOP")
                if ch:
                    print(ch, end="", flush=True)
                    _marker("ECHO", ch)
                time.sleep(0.05)
                while _safe_kbhit():
                    extra = msvcrt.getch().decode('utf-8', errors='ignore')
                    if extra and extra not in ('\r', '\n'):
                        print(extra, end="", flush=True)
                        _marker("ECHO", extra)
                    _marker("DISCARD", extra if extra and extra not in ('\r', '\n') else "(Enter)")
                return ch.upper()
            time.sleep(0.01)

        _stop_audio()
        _marker("TTS STOP")

    while not _safe_kbhit():
        time.sleep(0.01)
    ch = msvcrt.getch().decode('utf-8', errors='ignore')
    if ch in ('\r', '\n'):
        ch = ''
    _marker("KEY", ch if ch else "(Enter)")
    if ch:
        print(ch, end="", flush=True)
        _marker("ECHO", ch)
    time.sleep(0.05)
    while _safe_kbhit():
        extra = msvcrt.getch().decode('utf-8', errors='ignore')
        if extra and extra not in ('\r', '\n'):
            print(extra, end="", flush=True)
            _marker("ECHO", extra)
        _marker("DISCARD", extra if extra and extra not in ('\r', '\n') else "(Enter)")
    return ch.upper()


def _wait_line_voice(voice_text, screen_prompt="> ", max_attempts=None, interval=None):
    """等待一行输入，同时播放短促语音提醒。
    - 用户开始输入后语音立即停止，不再重念
    - interval 秒 × max_attempts 次没动 → 之后静默等
    - 非交互环境自动 fallback 到 readline
    - 关键：不消费任何按键，所有输入都交给 sys.stdin.readline()
    """
    if max_attempts is None:
        max_attempts = VOICE_REMINDER_MAX
    if interval is None:
        interval = VOICE_REMINDER_INTERVAL

    print(screen_prompt, end="", flush=True)
    sys.stdout.flush()

    if not VOICE_REMINDER_ENABLED or not voice_text:
        try:
            return sys.stdin.readline().strip()
        except (EOFError, KeyboardInterrupt):
            return "Q"

    stop_event = threading.Event()
    user_active = [False]

    def _monitor():
        """只检测键盘活动（peek，不消费），检测到就停语音"""
        while not stop_event.is_set():
            if _safe_kbhit():
                if not user_active[0]:
                    _marker("TTS STOP")
                user_active[0] = True
                _stop_audio()
            time.sleep(0.05)

    def _voice_loop():
        for attempt in range(1, max_attempts + 1):
            if stop_event.is_set() or user_active[0]:
                return
            try:
                _speak_zh_async_silent(voice_text)
                _marker("TTS START", voice_text)
            except Exception:
                pass

            # 等候 interval，每 50ms 检查用户是否开始输入
            for _ in range(int(interval * 20)):
                if stop_event.is_set() or user_active[0]:
                    return
                time.sleep(0.05)

    threading.Thread(target=_monitor, daemon=True).start()
    threading.Thread(target=_voice_loop, daemon=True).start()

    try:
        line = sys.stdin.readline().strip()
    except (EOFError, KeyboardInterrupt):
        line = "Q"

    stop_event.set()
    _stop_audio()
    return line


def _speak_once(voice_text):
    """念一次语音（不轮询、不重念）。用于"正在录音"等不需要重念的场景。"""
    if not VOICE_REMINDER_ENABLED or not voice_text:
        return
    try:
        _speak_zh_async_silent(voice_text)
    except Exception:
        pass


# -- 模式实现 ----------------------------------------------

# -- 模式 0：记忆导入 ----------------------------------------

def mode_0_memory_import():
    """模式 0：记忆导入 —— 每词循环 8 遍西语+中文，建立初步记忆"""
    items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    _run_group_menu_memory_import("单词", groups)


def _run_group_menu_memory_import(kind, groups):
    """组菜单：列出每组词，用户选组进入记忆导入"""
    all_items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    while True:
        fav_words = _get_favorites()
        print()
        print("=" * 36)
        print(f"          [记忆导入-{kind}] 共 {len(groups)} 组")
        print("=" * 36)
        print(f"  [R] 随机组（{len(all_items)} 个词，乱序）")
        if fav_words:
            print(f"  [*] 收藏组（{len(fav_words)} 个词）")
        for gi, group in enumerate(groups, 1):
            words = ", ".join(item["es"] for item in group)
            print(f"  [{gi}] 第 {gi} 组：{words}")
        print("  [B] 返回")
        print("=" * 36)
        sys.stdout.flush()

        choice = _wait_line_voice(_VP_PROMPT, "请选择 > ").upper()
        if choice == "B":
            return
        if choice == "R":
            shuffled = list(all_items)
            random.shuffle(shuffled)
            _run_one_group_memory_import([shuffled], 0)
            continue
        if choice == "*" and fav_words:
            fav_items = [it for it in all_items if it["es"] in fav_words]
            if fav_items:
                _run_one_group_memory_import([fav_items], 0)
            else:
                print("  收藏的词不在当前教材中。")
                sys.stdout.flush()
            continue
        try:
            gi = int(choice) - 1
            if 0 <= gi < len(groups):
                _run_one_group_memory_import(groups, gi)
        except ValueError:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _run_one_group_memory_import(groups, gi):
    """单组记忆导入：GroupSession 驱动，每词 8 遍循环"""
    import re
    group = groups[gi]
    total_groups = len(groups)
    gs = GroupSession(group)

    skip_group = False
    restart_group = False
    while not gs.all_passed and not skip_group and not restart_group:
        item = gs.current
        es_text = item["es"]
        zh_first = re.split(r'[,，、]', item["zh"])[0].strip()

        print(f"\n{'─' * 36}")
        print(f"  记忆导入 · 第 {gi+1}/{total_groups} 组 · 第 {gs.current_index}/{gs.total} 词")
        print(f"{'─' * 36}")
        print(f"  {es_text} — {zh_first}\n")
        sys.stdout.flush()

        _memory_import_loop(es_text, zh_first)

        # 打字测验：拼写 + 中文（非阻塞，输错不影响过题）
        if _spelling_quiz_phase(es_text, item["zh"]) == "quit":
            print()
            sys.stdout.flush()
            return

        # P/N/B/R/G/F/Q 决策（最后一项时扩展 [S]重练本组）
        is_last = (gs.passed_count == gs.total - 1)
        s_menu = "  [S]重练本组" if is_last else ""
        while True:
            choice = _wait_key_voice(
                _VP_PROMPT,
                f"  [Enter/P]通过  [N]保留  [B]上词  [R]重听{s_menu}  [G]下组  [F]收藏  [Q]退出 > ",
            )
            if not choice or choice == "P":
                gs.pass_current()
                break
            elif choice == "N":
                gs.keep_current()
                break
            elif choice == "R":
                print(f"\n  [重听] {es_text}")
                sys.stdout.flush()
                _memory_import_loop(es_text, zh_first)
            elif choice == "B":
                prev_item, was_passed = gs.go_back()
                if prev_item is not None:
                    print(f"\n  [回退] {prev_item['es']}")
                    sys.stdout.flush()
                    zh_first = re.split(r'[,，、]', prev_item['zh'])[0].strip()
                    _memory_import_loop(prev_item['es'], zh_first)
                break
            elif choice == "F":
                added = _toggle_favorite(es_text)
                print(f"    {'★ 已收藏' if added else '☆ 已取消收藏'}")
                sys.stdout.flush()
                continue
            elif choice == "S" and is_last:
                gs.reset_all()
                tts_speak_zh("从头开始")
                restart_group = True
                break
            elif choice == "G":
                skip_group = True
                break
            elif choice == "Q":
                print()
                sys.stdout.flush()
                return
            else:
                gs.keep_current()
                break

    if restart_group:
        _run_one_group_memory_import(groups, gi)
        return

    if skip_group:
        if gi + 1 < total_groups:
            _run_one_group_memory_import(groups, gi + 1)
        return

    print(f"\n── 第 {gi+1} 组通关 ──\n")
    sys.stdout.flush()
    if gi + 1 < total_groups:
        _run_one_group_memory_import(groups, gi + 1)


# -- 模式 1：听西语说中文 ------------------------------------

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

        choice = _wait_key_voice(_VP_PROMPT, "请选择 > ")
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
    """听西语说中文——句子池：先选难度，再组菜单 + GroupSession"""
    while True:
        print()
        print("=" * 36)
        print("          [模式1-句子] 选难度")
        print("=" * 36)
        print("  [1] 听写抓词   —— 连听后敲出抓到的词")
        print("  [2] 纯听       —— 只听 + 自判")
        print("  [Q] 返回")
        print("=" * 36)
        sys.stdout.flush()
        choice = _wait_key_voice(_VP_PROMPT, "请选择 > ")
        if choice == "1":
            items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
            groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
            _run_group_menu_es_to_zh("句子", groups, difficulty="catch")
            return
        if choice == "2":
            items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
            groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
            _run_group_menu_es_to_zh("句子", groups, difficulty="listen")
            return
        if choice == "Q":
            return
        print("  无效选项，请重新选择。")
        sys.stdout.flush()


def _run_group_menu_es_to_zh(kind, groups, difficulty=None):
    """组菜单：列出每组词/句，用户选组进入练习
    difficulty=None   原行为（单词或句子默认走原流程）
    difficulty="catch" / "listen"  仅对句子路径生效，走新流程"""
    is_word = (kind == "单词")
    all_items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    use_new = (kind == "句子") and (difficulty in ("catch", "listen"))
    while True:
        fav_words = _get_favorites() if is_word else []
        print()
        print("=" * 36)
        title = f"[模式1-{kind}] 共 {len(groups)} 组"
        if use_new:
            title = f"[模式1-句子·{'听写抓词' if difficulty=='catch' else '纯听'}] 共 {len(groups)} 组"
        print(f"          {title}")
        print("=" * 36)
        if is_word:
            print(f"  [R] 随机组（{len(all_items)} 个词，乱序）")
        if fav_words:
            print(f"  [*] 收藏组（{len(fav_words)} 个词）")
        for gi, group in enumerate(groups, 1):
            words = ", ".join(item["es"] for item in group)
            print(f"  [{gi}] 第 {gi} 组：{words}")
        print("  [B] 返回")
        print("=" * 36)
        sys.stdout.flush()

        choice = _wait_line_voice(_VP_PROMPT, "请选择 > ").upper()
        if choice == "B":
            return
        if choice == "R" and is_word:
            shuffled = list(all_items)
            random.shuffle(shuffled)
            _run_one_group_es_to_zh([shuffled], 0, "单词")
            continue
        if choice == "*" and fav_words:
            fav_items = [it for it in all_items if it["es"] in fav_words]
            if fav_items:
                _run_one_group_es_to_zh([fav_items], 0, "单词")
            continue
        try:
            gi = int(choice) - 1
            if 0 <= gi < len(groups):
                _run_one_group_es_to_zh(groups, gi, kind, difficulty)
        except ValueError:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _run_one_group_es_to_zh(groups, gi, kind, difficulty=None):
    """单组练习：GroupSession 驱动。groups 是全部组列表，gi 是当前组索引
    句子 + difficulty 非空时走新流程（听写抓词/纯听），否则走原流程。"""
    group = groups[gi]
    total_groups = len(groups)
    gs = GroupSession(group)
    is_sent = (kind == "句子")
    use_new = is_sent and (difficulty in ("catch", "listen"))

    if use_new:
        _run_one_group_es_to_zh_linkage(groups, gi, kind, difficulty)
        return


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
        tts_speak(es_text, is_sentence=is_sent)
        time.sleep(0.3)
        print(f"  听原音（第2遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text, is_sentence=is_sent)
        time.sleep(0.3)

        # ── 录音阶段 ──
        qq = _record_phase(es_text, is_sentence=is_sent)
        if qq == "quit":
            return

        # ── 回放 + 原音对比 + 答案 ──
        stop_and_playback()
        print("  -- 原音对比 --")
        sys.stdout.flush()
        tts_speak(es_text, is_sentence=is_sent)

        print(f"\n  [答案] {es_text} → {zh_text}\n")
        sys.stdout.flush()
        tts_speak_zh(zh_text)  # 单词用中文语音读出中文释义

        # ── 决策 ──
        result = _decision_pnbr(gs, es_text,
                                allow_favorite=(kind == "单词"),
                                sentence_fav=(kind == "句子"),
                                is_sentence=is_sent)
        if result == "quit":
            return
        if result == "completed":
            print(f"\n── 第 {gi+1} 组通关 ──\n")
            sys.stdout.flush()
            if gi + 1 < total_groups:
                _run_one_group_es_to_zh(groups, gi + 1, kind)
            return
        if result == "restart":
            _run_one_group_es_to_zh(groups, gi, kind)
            return
        if result == "goto_next":
            if gi + 1 < total_groups:
                _run_one_group_es_to_zh(groups, gi + 1, kind)
            return

    print(f"\n── 第 {gi+1} 组通关 ──\n")
    sys.stdout.flush()
    if gi + 1 < total_groups:
        _run_one_group_es_to_zh(groups, gi + 1, kind)


def _prompt_record(prompt="按 Enter 开始录音", extra_hint="", voice_prompt=None, recording_voice=None):
    """两段式录音：先提示按 Enter 开始，再提示按 Enter 结束。
    录音数据留在 REC_CHUNKS 中，由调用者通过 stop_and_playback() 播放。
    返回用户输入的命令（大写），空字符串表示录音完成。

    voice_prompt: 启动录音前的语音提示文本（None = 静默）
    recording_voice: 进入录音后的语音提示文本（None = 静默，只念一次）
    """
    if not HAS_AUDIO:
        return ""

    if voice_prompt:
        user_input = _wait_line_voice(voice_prompt, f"  {prompt}{extra_hint}")
    else:
        user_input = wait_line(f"  {prompt}{extra_hint}")
    cmd = user_input.strip().upper() if user_input else ""
    if cmd:
        return cmd

    start_recording()

    # 再次清空：防止启动录音前瞬间有残留回车混入
    while msvcrt.kbhit():
        msvcrt.getch()

    print("  正在录音... 按 Enter 结束录音", end="", flush=True)
    # 录音中只念一次（不重念，避免盖过用户声音）
    _speak_once(recording_voice or _VP_RECORDING)
    wait_line("")
    print()
    # 停止录音流，但不播放（由调用者决定何时播放）
    global REC_STREAM
    if REC_STREAM:
        try:
            REC_STREAM.stop()
            REC_STREAM.close()
            REC_STREAM = None
        except Exception:
            pass
    return ""


def _record_phase(es_text, is_sentence=False):
    """录音阶段：按 Enter 开始录音，再按 Enter 结束。支持 R 重听、Q 退出。
    返回 "quit" 表示退出，否则返回 None。"""
    while True:
        cmd = _prompt_record(
            "按 Enter 开始录音",
            "  [R]重听 [Q]退出 > ",
            voice_prompt=_VP_PROMPT,
        )
        if cmd == "Q":
            return "quit"
        if cmd == "R":
            tts_speak(es_text, is_sentence=is_sentence)
            time.sleep(0.3)
            tts_speak(es_text, is_sentence=is_sentence)
            continue
        # 正常录音完成（空字符串）
        return None


def _record_phase_zh(zh_text):
    """录音阶段（模式2）：按 Enter 开始录音，再按 Enter 结束。支持 R 重听中文、Q 退出。"""
    while True:
        cmd = _prompt_record(
            "按 Enter 开始录音",
            "  [R]重听 [Q]退出 > ",
            voice_prompt=_VP_PROMPT,
        )
        if cmd == "Q":
            return "quit"
        if cmd == "R":
            tts_speak_zh(zh_text)
            continue
        return None


def _record_phase_shadow(es_text, is_sentence=True):
    """录音阶段（跟读）：按 Enter 开始跟读，再按 Enter 结束。支持 S 跳过、Q 退出。"""
    while True:
        cmd = _prompt_record(
            "按 Enter 开始跟读",
            "  [S]跳过 [Q]退出 > ",
            voice_prompt=_VP_PROMPT,
        )
        if cmd == "Q":
            return "quit"
        if cmd == "S":
            return "skip"
        return None


def _run_one_group_es_to_zh_linkage(groups, gi, kind, difficulty):
    """模式1句子新流程：听写抓词 / 纯听，含词界标注 + 拆听。"""
    group = groups[gi]
    total_groups = len(groups)
    gs = GroupSession(group)

    restart_group = False
    while not gs.all_passed and not restart_group:
        item = gs.current
        es_text = item["es"]
        zh_text = item["zh"]
        passed_info = f"  ✓{gs.passed_count}/{gs.total}" if gs.passed_count > 0 else ""

        print(f"\n{'─' * 36}")
        print(f"  第 {gi+1}/{total_groups} 组 · 第 {gs.current_index}/{gs.total} 句  {passed_info}")
        print(f"{'─' * 36}")
        print(f"  （按 V 切词界版 · W 拆听）")
        sys.stdout.flush()

        for k in (1, 2):
            print(f"  听原句（第{k}遍）：{es_text}")
            sys.stdout.flush()
            tts_speak(es_text, is_sentence=True)
            time.sleep(0.3)

        if difficulty == "catch":
            user_input = _wait_line_voice(_VP_INPUT, "  敲入你听到的词（空格分隔） > ")
            if user_input.strip().upper() == "Q":
                return
            if user_input.strip().upper() == "S":
                gs.keep_current()
                continue
            res = _compare_caught_words(user_input, es_text)
            print()
            print(f"  ── 抓词结果 ──")
            print(f"  ✓ 抓到 ({res['score']})：{', '.join(res['caught']) if res['caught'] else '—'}")
            print(f"  ✗ 漏掉 ({len(res['missing'])})：{', '.join(res['missing']) if res['missing'] else '—'}")
            print(f"  ✗ 多打 ({len(res['extra'])})：{', '.join(res['extra']) if res['extra'] else '—'}")
            print(f"  得分：{res['score']}/{res['total']} 词")
            sys.stdout.flush()

            print()
            print(f"  [答案] {es_text} → {zh_text}")
            sys.stdout.flush()
            tts_speak_zh(zh_text)
            show = False
            while True:
                _print_sentence_with_linkage(es_text, show_linkage=show)
                print("  [V]切词界  [R]重听  [W]拆听  [其他键继续] > ", end="", flush=True)
                ch = _wait_key_voice(_VP_PROMPT, "")
                if ch == "V":
                    show = not show
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                if ch == "R":
                    tts_speak(es_text, is_sentence=True)
                    time.sleep(0.3)
                    tts_speak(es_text, is_sentence=True)
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                if ch == "W":
                    print("  [拆听] ", end="", flush=True)
                    _play_word_by_word(es_text)
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                sys.stdout.write("\r\033[2K")
                sys.stdout.flush()
                break

            print(f"  再听一遍：{es_text}")
            sys.stdout.flush()
            tts_speak(es_text, is_sentence=True)

            if res["perfect"]:
                gs.pass_current()
                print("  ✓ 全对，自动通过。")
                sys.stdout.flush()
            else:
                gs.keep_current()
                print("  ✗ 有漏/多，已保留待重练。")
                sys.stdout.flush()
            if gs.all_passed:
                print(f"\n── 第 {gi+1} 组通关 ──\n")
                sys.stdout.flush()
                if gi + 1 < total_groups:
                    _run_one_group_es_to_zh_linkage(groups, gi + 1, kind, difficulty)
                return
        else:
            show = False
            while True:
                _print_sentence_with_linkage(es_text, show_linkage=show)
                print("  [V]切词界  [R]重听  [W]拆听  [其他键继续] > ", end="", flush=True)
                ch = _wait_key_voice(_VP_PROMPT, "")
                if ch == "V":
                    show = not show
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                if ch == "R":
                    tts_speak(es_text, is_sentence=True)
                    time.sleep(0.3)
                    tts_speak(es_text, is_sentence=True)
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                if ch == "W":
                    print("  [拆听] ", end="", flush=True)
                    _play_word_by_word(es_text)
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                sys.stdout.write("\r\033[2K")
                sys.stdout.flush()
                break
            print(f"  [答案] {es_text} → {zh_text}")
            sys.stdout.flush()
            tts_speak_zh(zh_text)

            print(f"  再听一遍：{es_text}")
            sys.stdout.flush()
            tts_speak(es_text, is_sentence=True)

            is_last = (gs.passed_count == gs.total - 1)
            s_menu = "  [S]重练本组" if is_last else ""
            while True:
                choice = _wait_key_voice(
                    _VP_PROMPT,
                    f"  [Enter/P]通过  [N]保留  [R]重听  [W]拆听{s_menu}  [F]收藏  [Q]退出 > ",
                )
                if not choice or choice == "P":
                    gs.pass_current()
                    break
                if choice == "N":
                    gs.keep_current()
                    break
                if choice == "R":
                    tts_speak(es_text, is_sentence=True)
                    time.sleep(0.3)
                    tts_speak(es_text, is_sentence=True)
                    continue
                if choice == "W":
                    print("  [拆听] ", end="", flush=True)
                    _play_word_by_word(es_text)
                    continue
                if choice == "S" and is_last:
                    gs.reset_all()
                    tts_speak_zh("从头开始")
                    restart_group = True
                    break
                if choice == "F":
                    _favorite_words_from_sentence(es_text)
                    continue
                if choice == "Q":
                    return

    if restart_group:
        _run_one_group_es_to_zh_linkage(groups, gi, kind, difficulty)
        return

    print(f"\n── 第 {gi+1} 组通关 ──\n")
    sys.stdout.flush()
    if gi + 1 < total_groups:
        _run_one_group_es_to_zh_linkage(groups, gi + 1, kind, difficulty)


def _decision_pnbr(gs, es_text, allow_favorite=False, sentence_fav=False, is_sentence=False):
    """P/N/B/R/G/Q/(F) 决策循环。
    返回 "quit"/"goto_next"/"completed"/"restart" 或 None。
    最后一项时菜单扩展 [S]重练本组。
    allow_favorite: [F]收藏整个单词（单词模式）
    sentence_fav:   [F]收藏本句所含生词（句子模式）"""
    fav_menu = ""
    if allow_favorite:
        fav_menu = "  [F]收藏"
    elif sentence_fav:
        fav_menu = "  [F]收藏句中单词"
    is_last = (gs.passed_count == gs.total - 1)
    s_menu = "  [S]重练本组" if is_last else ""
    while True:
        choice = _wait_key_voice(
            _VP_PROMPT,
            f"  [Enter/P]通过  [N]保留  [B]上词  [R]重听{s_menu}  [G]下组{fav_menu}  [Q]退出 > ",
        )
        if not choice or choice == "P":
            gs.pass_current()
            if is_last:
                return "completed"
            return None
        elif choice == "N":
            gs.keep_current()
            return None
        elif choice == "R":
            tts_speak(es_text, is_sentence=is_sentence)
            time.sleep(0.3)
            tts_speak(es_text, is_sentence=is_sentence)
            print()
            sys.stdout.flush()
            continue
        elif choice == "B":
            while True:
                prev_item, was_passed = gs.go_back()
                if prev_item is None:
                    print("  已经是第一个词了")
                    sys.stdout.flush()
                    return None
                if not was_passed:
                    return None
                sub = wait_key(
                    f"  [上一词] 「{prev_item['es']}」已通关。"
                    f"[Y] 拉回来重新练习  [N] 跳过，继续往前退 > "
                )
                if sub == "Y":
                    gs.unpass()
                    return None
        elif choice == "G":
            return "goto_next"
        elif choice == "S" and is_last:
            gs.reset_all()
            tts_speak_zh("从头开始")
            return "restart"
        elif choice == "F" and allow_favorite:
            added = _toggle_favorite(es_text)
            print(f"    {'★ 已收藏' if added else '☆ 已取消收藏'}")
            sys.stdout.flush()
            continue
        elif choice == "F" and sentence_fav:
            _favorite_words_from_sentence(es_text)
            continue
        elif choice == "Q":
            return "quit"
        else:
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

        choice = _wait_key_voice(_VP_PROMPT, "请选择 > ")
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
    """听中文说西语——单词池，组菜单 + GroupSession"""
    items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    _run_group_menu_zh_to_es("单词", groups)


def _mode_zh_to_es_sentences():
    """听中文说西语——句子池，组菜单 + GroupSession"""
    items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
    _run_group_menu_zh_to_es("句子", groups)


def _run_group_menu_zh_to_es(kind, groups):
    """组菜单：列出每组词/句，用户选组进入练习"""
    is_word = (kind == "单词")
    all_items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
    while True:
        fav_words = _get_favorites() if is_word else []
        print()
        print("=" * 36)
        print(f"          [模式2-{kind}] 共 {len(groups)} 组")
        print("=" * 36)
        if is_word:
            print(f"  [R] 随机组（{len(all_items)} 个词，乱序）")
        if fav_words:
            print(f"  [*] 收藏组（{len(fav_words)} 个词）")
        for gi, group in enumerate(groups, 1):
            words = ", ".join(item["es"] for item in group)
            print(f"  [{gi}] 第 {gi} 组：{words}")
        print("  [B] 返回")
        print("=" * 36)
        sys.stdout.flush()

        choice = _wait_line_voice(_VP_PROMPT, "请选择 > ").upper()
        if choice == "B":
            return
        if choice == "R" and is_word:
            shuffled = list(all_items)
            random.shuffle(shuffled)
            _run_one_group_zh_to_es([shuffled], 0, "单词")
            continue
        if choice == "*" and fav_words:
            fav_items = [it for it in all_items if it["es"] in fav_words]
            if fav_items:
                _run_one_group_zh_to_es([fav_items], 0, "单词")
            continue
        try:
            gi = int(choice) - 1
            if 0 <= gi < len(groups):
                _run_one_group_zh_to_es(groups, gi, kind)
        except ValueError:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _run_one_group_zh_to_es(groups, gi, kind):
    """单组练习（模式2）：GroupSession 驱动"""
    group = groups[gi]
    total_groups = len(groups)
    gs = GroupSession(group)
    is_sent = (kind == "句子")

    while not gs.all_passed:
        item = gs.current
        es_text = item["es"]
        zh_text = item["zh"]
        passed_info = f"  ✓{gs.passed_count}/{gs.total}" if gs.passed_count > 0 else ""

        # ── 展示中文 ──
        print(f"\n{'─' * 36}")
        print(f"  第 {gi+1}/{total_groups} 组 · 第 {gs.current_index}/{gs.total} 词  {passed_info}")
        print(f"{'─' * 36}")
        print(f"\n  {zh_text}\n")
        sys.stdout.flush()

        # ── TTS 中文朗读（可打断）──
        tts_speak_zh(zh_text)

        # ── 录音：用户说西语 ──
        qq = _record_phase_zh(zh_text)
        if qq == "quit":
            return

        # ── 回放 + 原音对比 + 答案 ──
        stop_and_playback()
        print("  -- 原音对比 --")
        sys.stdout.flush()
        tts_speak(es_text, is_sentence=is_sent)

        print(f"\n  [答案] {zh_text} → {es_text}\n")
        sys.stdout.flush()

# ── 决策 ──
        result = _decision_pnbr(gs, es_text,
                                allow_favorite=(kind == "单词"),
                                sentence_fav=(kind == "句子"),
                                is_sentence=is_sent)
        if result == "quit":
            return
        if result == "completed":
            print(f"\n── 第 {gi+1} 组通关 ──\n")
            sys.stdout.flush()
            if gi + 1 < total_groups:
                _run_one_group_zh_to_es(groups, gi + 1, kind)
            return
        if result == "restart":
            _run_one_group_zh_to_es(groups, gi, kind)
            return
        if result == "goto_next":
            if gi + 1 < total_groups:
                _run_one_group_zh_to_es(groups, gi + 1, kind)
            return

    print(f"\n── 第 {gi+1} 组通关 ──\n")
    sys.stdout.flush()
    if gi + 1 < total_groups:
        _run_one_group_zh_to_es(groups, gi + 1, kind)


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

    # 录音（两段式：按 Enter 开始，再按 Enter 结束）
    while True:
        cmd = _prompt_record(
            "按 Enter 开始录音",
            "  [R]重听 [S]跳过 [Q]退出 > ",
            voice_prompt=_VP_PROMPT,
        )
        if cmd == "Q":
            return "quit"
        if cmd == "S":
            pq.mark_skip(item)
            return
        if cmd == "R":
            tts_speak(es_text)
            continue
        # 正常录音完成（空字符串）
        break

    # 回放录音
    stop_and_playback()
    print("   你的录音回放完毕")
    sys.stdout.flush()

    # 播正确答案
    print(f"  [OK] 正确答案：{es_text} → {zh_text}")
    sys.stdout.flush()
    tts_speak(es_text)

    # 自判
    judge = _wait_key_voice(
        "Y通过，N错，S跳过，Q退出",
        "  答对了吗？[Y=对 / N=错 / S=别再问我 / Q=退出] > ",
    )
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

    # 录音（两段式：按 Enter 开始，再按 Enter 结束）
    while True:
        cmd = _prompt_record(
            "按 Enter 开始录音",
            "  [R]重听 [S]跳过 [Q]退出 > ",
            voice_prompt=_VP_PROMPT,
        )
        if cmd == "Q":
            return "quit"
        if cmd == "S":
            pq.mark_skip(item)
            return
        if cmd == "R":
            tts_speak_zh(zh_text)
            continue
        # 正常录音完成（空字符串）
        break

    # 回放
    stop_and_playback()
    print("   你的录音回放完毕")
    sys.stdout.flush()

    # 正确答案
    print(f"  [OK] 正确答案：{es_text}")
    sys.stdout.flush()
    tts_speak(es_text)

    # 自判
    judge = _wait_key_voice(
        "Y通过，N错，S跳过，Q退出",
        "  答对了吗？[Y=对 / N=错 / S=别再问我 / Q=退出] > ",
    )
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

        choice = _wait_key_voice(_VP_PROMPT, "请选择 > ")
        if choice == "1":
            items = [{"es": v["es"], "zh": v["zh"]} for v in TEXTBOOK["vocab"]]
            groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]
            _run_group_menu_dictation_word(groups)
        elif choice == "2":
            _mode_dictation_sentences()
        elif choice == "Q":
            return
        else:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _run_group_menu_dictation_word(groups):
    """组菜单：列出每组单词，用户选组进入听写"""
    while True:
        print()
        print("=" * 36)
        print(f"          [听写-单词] 共 {len(groups)} 组")
        print("=" * 36)
        for gi, group in enumerate(groups, 1):
            words = ", ".join(item["es"] for item in group)
            print(f"  [{gi}] 第 {gi} 组：{words}")
        print("  [B] 返回")
        print("=" * 36)
        sys.stdout.flush()

        choice = _wait_line_voice(_VP_PROMPT, "请选择 > ").upper()
        if choice == "B":
            return
        try:
            gi = int(choice) - 1
            if 0 <= gi < len(groups):
                _run_one_group_dictation_word(groups, gi)
        except ValueError:
            print("  无效选项，请重新选择。")
            sys.stdout.flush()


def _run_one_group_dictation_word(groups, gi):
    """单组单词听写：PracticeQueue 驱动"""
    group = groups[gi]
    total_groups = len(groups)

    print(f"\n[听写-单词] 第 {gi+1}/{total_groups} 组 — 按S跳过 按Q返回")
    print("-" * 36 + "\n")
    sys.stdout.flush()

    pq = PracticeQueue(group)
    last_announced = False
    while not pq.empty:
        item = pq.next()
        es_text = item["es"]

        if pq.remaining == 1 and not last_announced:
            tts_speak_zh("这是最后一个了")
            last_announced = True

        print(f"当前单词：{es_text}")
        sys.stdout.flush()
        tts_speak_async(es_text)

        user_input = _wait_line_voice(_VP_INPUT, "> ")
        cmd = user_input.strip()

        if cmd.upper() == "Q":
            print()
            sys.stdout.flush()
            return
        if cmd.upper() == "S":
            pq.mark_skip()
            last_announced = False
            print(f"  已跳过，剩余：{pq.remaining} 题\n")
            sys.stdout.flush()
            continue

        if _strip_accents(cmd.strip().lower()) == _strip_accents(es_text.lower()):
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

    print(f"\n── 第 {gi+1} 组通关 ──\n")
    sys.stdout.flush()
    nxt = _wait_key_voice(
        _VP_PROMPT,
        "  [Enter] 继续下一组  [B] 回组菜单  [S] 重练本组  [Q] 退出 > ",
    )
    if nxt == "Q":
        return
    if nxt == "B":
        return
    if nxt == "S":
        _run_one_group_dictation_word(groups, gi)
        return
    if gi + 1 < total_groups:
        _run_one_group_dictation_word(groups, gi + 1)


def _strip_accents(s):
    """去掉西班牙语重音符号（áéíóú），保留 ñ/ü 不变。"""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    return s


def _normalize_sentence(text):
    """规范化句子用于比较：去标点、去重音、统一大小写、合并空白"""
    cleaned = text.strip()
    # 去掉所有标点符号（保留字母、数字、空格）
    cleaned = re.sub(r'[.,:;!?¿¡\-—"\'«»()]', '', cleaned)
    # 去重音
    cleaned = _strip_accents(cleaned)
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


def _highlight_char_diff(correct, user_input):
    """逐字符对比用户输入和正确拼写，返回正确拼写的 ANSI 颜色版本。
    用户打对的部分 → 绿色，漏打/错打的部分 → 红色。"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'

    sm = difflib.SequenceMatcher(None, user_input.lower(), correct.lower())

    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            parts.append(GREEN + correct[j1:j2] + RESET)
        elif tag in ('insert', 'replace'):
            parts.append(RED + correct[j1:j2] + RESET)
        # 'delete': user has extra chars not in correct → nothing to show in correct

    return ''.join(parts)


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

            tts_speak(es_text, is_sentence=True)
            time.sleep(0.3)
            tts_speak(es_text, is_sentence=True)

            user_input = _wait_line_voice(_VP_INPUT, "> ")
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
                tts_speak(es_text, is_sentence=True)
                time.sleep(0.3)
                tts_speak(es_text, is_sentence=True)
                user_input = _wait_line_voice(_VP_INPUT, "> ")
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
                tts_speak_async(es_text, is_sentence=True)

            # 提示收藏本句生词
            ch = _wait_key_voice(_VP_PROMPT, "  收藏本句生词？[F]收藏 [Enter]继续 > ")
            if ch == "F":
                _favorite_words_from_sentence(es_text)

        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部句子通关！--\n")
    sys.stdout.flush()
    time.sleep(0.5)


# -- 词界连读工具（v4 方案） ------------------------------------------

_VOWELS = set("aeiouáéíóúüAEIOUÁÉÍÓÚÜ")
_PUNCT_STRIP = ".,;:¿¡!?""«»()[]{}-—…"


def _is_vowel_char(ch):
    return ch in _VOWELS


def _strip_punct(token):
    """去掉 token 两侧的标点，返回 (display, last_char, first_char)。
    display 保留原大小写/重音（用于屏幕显示）；
    last_char / first_char 取小写最后一个/第一个字母（用于连读规则判定）。
    若 cleaned 为空返回 None。"""
    s = token.strip().strip(_PUNCT_STRIP)
    if not s:
        return None
    s_lower = s.lower()
    return s, s_lower[-1], s_lower[0]


def _classify_boundary(w1_last, w2_first):
    """根据前一词尾字符 + 后一词首字符返回连读类型。
    返回 None 表示不连（保留空格），否则返回 'link'（连读，合一）。"""
    if not w1_last or not w2_first:
        return None
    v1, v2 = _is_vowel_char(w1_last), _is_vowel_char(w2_first)
    if v1 and v2:
        return "link"  # 合音（异元）或吞音（同元），均合一
    if (not v1) and v2:
        return "link"  # 连链
    if (not v1) and (not v2):
        return "link"  # 邻接
    return None  # 元→辅，不连


def _is_pure_chinese(text):
    """文本不含任何英文字母则视为纯中文。
    数字、中文标点、空白允许。
    检测到 a-z/A-Z 视为混合语种，走 Kokoro。"""
    return not re.search(r'[a-zA-Z]', text)


def _tokenize_es_sentence(es_text):
    """分词 + 去标点。返回 [(display, last, first), ...]（display 保留原大小写重音）。"""
    out = []
    for tok in es_text.split():
        info = _strip_punct(tok)
        if info is None:
            continue
        out.append(info)
    return out


def _build_linkage_blocks(tokens):
    """tokens: list of (display, last, first)。
    返回 [(start_idx, end_idx_exclusive), ...] 表示连读块的索引范围（连续合并）。"""
    if not tokens:
        return []
    blocks = []
    cur_start = 0
    for i in range(len(tokens) - 1):
        typ = _classify_boundary(tokens[i][1], tokens[i + 1][2])
        if typ is None:
            # 边界不连：结束当前块（如果长度 > 1）
            if cur_start < i:
                blocks.append((cur_start, i + 1))
            cur_start = i + 1
    # 收尾
    if cur_start < len(tokens):
        blocks.append((cur_start, len(tokens)))
    # 单元素块不画（无意义）
    return [b for b in blocks if b[1] - b[0] >= 2]


def _format_sentence_with_linkage(es_text, show_linkage=False, color_blocks=True):
    """打印一句西语。
    show_linkage=False: 原样打印。
    show_linkage=True: 连读块内单词用 ANSI 颜色交替区分（绿/黄），块间正常空格。
    color_blocks=False 且 show_linkage=True: 块内去空格相连，块间空格（无颜色）。
    返回打印的字符串。display 保留原大小写/重音。"""
    if not show_linkage:
        return f"  {es_text}"
    tokens = _tokenize_es_sentence(es_text)
    if not tokens:
        return f"  {es_text}"
    blocks = _build_linkage_blocks(tokens)
    display_list = [t[0] for t in tokens]
    out_parts = []
    block_set = set()
    for s, e in blocks:
        for k in range(s, e):
            block_set.add(k)
    i = 0
    while i < len(display_list):
        if i in block_set:
            j = i
            while j + 1 < len(display_list) and (j + 1) in block_set:
                j += 1
            block = display_list[i:j + 1]
            if color_blocks:
                colored = []
                for k, w in enumerate(block):
                    if k % 2 == 0:
                        colored.append(f"{_COLOR_GREEN}{w}{_COLOR_RESET}")
                    else:
                        colored.append(f"{_COLOR_YELLOW}{w}{_COLOR_RESET}")
                out_parts.append("".join(colored))
            else:
                out_parts.append("".join(block))
            i = j + 1
        else:
            out_parts.append(display_list[i])
            i += 1
    trailing = ""
    if es_text and not es_text[-1].isalpha() and not es_text[-1].isspace():
        trailing = es_text[-1]
    line = "  " + " ".join(out_parts) + (trailing if trailing else "")
    return line


def _print_sentence_with_linkage(es_text, show_linkage):
    """打印一行：正常版或词界版（带颜色）。"""
    line = _format_sentence_with_linkage(es_text, show_linkage=show_linkage, color_blocks=show_linkage)
    print(line, flush=True)


def _play_word_by_word(es_text, gap=0.3):
    """逐词朗读（用单词安全模型），词间插 gap 秒静音。"""
    tokens = _tokenize_es_sentence(es_text)
    if not tokens:
        return
    for idx, (cleaned, _, _) in enumerate(tokens):
        tts_speak(cleaned, is_sentence=False)
        if idx < len(tokens) - 1:
            time.sleep(gap)


def _parse_caught_input(user_input):
    """把用户输入拆成词集合（去空、去标点、小写）。返回 set of cleaned words。"""
    out = set()
    for tok in user_input.split():
        info = _strip_punct(tok)
        if info is None:
            continue
        out.add(info[0])
    return out


def _compare_caught_words(user_input, es_text, fuzzy_threshold=0.8):
    """宽松匹配比对。
    返回 dict: {caught: [...], missing: [...], extra: [...], total, score, perfect}
    规则：
      1. 原句 cleaned 词列表（lowercase 用于规则判定，display 用于显示）
      2. 用户输入 cleaned 集合（lowercase）
      3. 对每个 user 词：
         a. 若 user 长度明显大于平均 target 长度（> avg*1.5 且 ≥ 6 字符），
            视为"连读块合并输入"——在未匹配 target 中按长度从大到小贪心找
            "target 是否是 user 的子串"，命中的全部标为抓到。
         b. 否则在未匹配 target 中找 difflib ratio 最佳（>= 阈值），命中标抓到。
         c. 都没命中：user 算多打。
      4. target 中未匹配的词 = 漏掉
    """
    token_info = _tokenize_es_sentence(es_text)
    target_display = [t[0] for t in token_info]
    target_lower = [t[0].lower() for t in token_info]
    user_set = _parse_caught_input(user_input)
    matched_target = [False] * len(target_lower)
    caught = []
    extra = []
    avg_len = (sum(len(t) for t in target_lower) / len(target_lower)) if target_lower else 0
    for uw in user_set:
        # a) 长 user_word → 子串贪心
        if len(uw) >= 6 and len(uw) > avg_len * 1.5:
            sub_hits = []
            for ti, tw in enumerate(target_lower):
                if matched_target[ti]:
                    continue
                if tw and tw in uw:
                    sub_hits.append(ti)
            if sub_hits:
                sub_hits.sort(key=lambda i: len(target_lower[i]), reverse=True)
                for ti in sub_hits:
                    matched_target[ti] = True
                    caught.append(target_display[ti])
                continue
        # b) ratio 匹配
        best_idx = -1
        best_ratio = 0.0
        for ti, tw in enumerate(target_lower):
            if matched_target[ti]:
                continue
            r = difflib.SequenceMatcher(None, uw, tw).ratio()
            if r > best_ratio:
                best_ratio = r
                best_idx = ti
        if best_idx >= 0 and best_ratio >= fuzzy_threshold:
            matched_target[best_idx] = True
            caught.append(target_display[best_idx])
        else:
            # c) 子串兜底：短 user_word 是某 target 的子串也算（容忍小笔误）
            for ti, tw in enumerate(target_lower):
                if matched_target[ti]:
                    continue
                if len(tw) >= 4 and len(uw) >= 3 and uw in tw:
                    matched_target[ti] = True
                    caught.append(target_display[ti])
                    break
            else:
                extra.append(uw)
    missing = [target_display[i] for i, m in enumerate(matched_target) if not m]
    total = len(target_display)
    score = len(caught)
    return {
        "caught": caught,
        "missing": missing,
        "extra": extra,
        "total": total,
        "score": score,
        "perfect": (total > 0 and not missing and not extra),
    }


def _prompt_linkage_view(es_text):
    """揭示阶段：循环按 V 切换词界版 / 正常版，按其他键退出循环返回按键。"""
    show = False
    while True:
        _print_sentence_with_linkage(es_text, show_linkage=show)
        print("  [V]切换词界版  [其他键继续] > ", end="", flush=True)
        ch = _wait_key_voice("V切换词界版，其他键继续", "")
        if ch == "V":
            show = not show
            # 简单清屏（ANSI 上移当前行 + 清除），避免堆叠
            sys.stdout.write("\033[1A\033[2K")
            sys.stdout.flush()
            continue
        # 任何其他键：清理本行（V 提示），返回该键
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()
        return ch


def _post_judgment_menu_pnbr(gs, es_text, sentence_fav=True):
    """模式1句子：揭示后判定菜单（自动判 + P/N 强制 / B/G/F/Q）。
    返回 quit/goto_next/completed/restart 或 None。"""
    is_last = (gs.passed_count == gs.total - 1)
    s_menu = "  [S]重练本组" if is_last else ""
    while True:
        choice = _wait_key_voice(
            _VP_PROMPT,
            f"  [Enter/P]通过  [N]保留  [B]上词  [R]重听{s_menu}  [G]下组  [F]收藏句中单词  [Q]退出 > ",
        )
        if not choice or choice == "P":
            gs.pass_current()
            if is_last:
                return "completed"
            return None
        if choice == "N":
            gs.keep_current()
            return None
        if choice == "R":
            tts_speak(es_text, is_sentence=True)
            time.sleep(0.3)
            tts_speak(es_text, is_sentence=True)
            continue
        if choice == "B":
            while True:
                prev_item, was_passed = gs.go_back()
                if prev_item is None:
                    print("  已经是第一个词了")
                    sys.stdout.flush()
                    return None
                if not was_passed:
                    return None
                sub = wait_key(
                    f"  [上一词] 「{prev_item['es']}」已通关。"
                    f"[Y] 拉回来重新练习  [N] 跳过，继续往前退 > "
                )
                if sub == "Y":
                    gs.unpass()
                    return None
        if choice == "G":
            return "goto_next"
        if choice == "S" and is_last:
            gs.reset_all()
            tts_speak_zh("从头开始")
            return "restart"
        if choice == "F" and sentence_fav:
            _favorite_words_from_sentence(es_text)
            continue
        if choice == "Q":
            return "quit"


def _post_judgment_menu_ynsfq(gs, es_text, pq=None):
    """模式4跟读：揭示后判定菜单（Y/N/S/F/Q）。返回 quit 或 None。"""
    while True:
        judge = _wait_key_voice(
            _VP_PROMPT,
            "  [Y=过 / N=留 / S=跳过 / F=收藏句中单词 / Q=退出] > ",
        )
        if judge == "Q":
            return "quit"
        if judge == "S":
            if pq is not None:
                pq.mark_skip({"es": es_text})
            return "skip"
        if judge == "F":
            _favorite_words_from_sentence(es_text)
            continue
        if judge == "N":
            if gs is not None:
                gs.keep_current()
            return "keep"
        # 默认 = Y (过)
        if gs is not None:
            gs.pass_current()
        return "pass"


# 暴露 ANSI 黄（方案里要用，原文件只有绿/红）
_COLOR_YELLOW = '\033[33m'


# -- 模式 4：跟读 ------------------------------------------

def mode_4_shadowing():
    """模式 4：跟读。5句一组，念西语句子 → 用户跟读 → 交替播放对比。
    v4：先选难度（听写抓词 / 纯听），均含词界标注 + 拆听。"""
    while True:
        print()
        print("=" * 36)
        print("          [模式4-跟读] 选难度")
        print("=" * 36)
        print("  [1] 听写抓词   —— 连听后敲出抓到的词")
        print("  [2] 纯听       —— 只听 + 自判")
        print("  [Q] 返回")
        print("=" * 36)
        sys.stdout.flush()
        choice = _wait_key_voice(_VP_PROMPT, "请选择 > ")
        if choice == "1":
            _run_shadowing_catch()
            return
        if choice == "2":
            _run_shadowing_listen()
            return
        if choice == "Q":
            return
        print("  无效选项，请重新选择。")
        sys.stdout.flush()


def _run_shadowing_catch():
    """模式4 听写抓词：复用 GroupSession，含词界 + 拆听。"""
    items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]

    for gi, group in enumerate(groups, 1):
        gs = GroupSession(group)
        print(f"\n[跟读-听写抓词] 第 {gi}/{len(groups)} 组 — 按 V 切词界 · W 拆听 · Q 退出\n")
        sys.stdout.flush()
        while not gs.all_passed:
            item = gs.current
            es_text = item["es"]
            zh_text = item["zh"]
            passed_info = f"  ✓{gs.passed_count}/{gs.total}" if gs.passed_count > 0 else ""
            print(f"\n{'─' * 36}")
            print(f"  第 {gi}/{len(groups)} 组 · 第 {gs.current_index}/{gs.total} 句  {passed_info}")
            print(f"{'─' * 36}")
            sys.stdout.flush()
            for k in (1, 2):
                print(f"  听原句（第{k}遍）：{es_text}")
                sys.stdout.flush()
                tts_speak(es_text, is_sentence=True)
                time.sleep(0.3)
            user_input = _wait_line_voice(_VP_INPUT, "  敲入你听到的词（空格分隔） > ")
            if user_input.strip().upper() == "Q":
                return
            if user_input.strip().upper() == "S":
                gs.keep_current()
                continue
            res = _compare_caught_words(user_input, es_text)
            print()
            print(f"  ── 抓词结果 ──")
            print(f"  ✓ 抓到 ({res['score']})：{', '.join(res['caught']) if res['caught'] else '—'}")
            print(f"  ✗ 漏掉 ({len(res['missing'])})：{', '.join(res['missing']) if res['missing'] else '—'}")
            print(f"  ✗ 多打 ({len(res['extra'])})：{', '.join(res['extra']) if res['extra'] else '—'}")
            print(f"  得分：{res['score']}/{res['total']} 词")
            sys.stdout.flush()
            print(f"\n  [答案] {es_text} → {zh_text}")
            sys.stdout.flush()
            tts_speak_zh(zh_text)
            show = False
            while True:
                _print_sentence_with_linkage(es_text, show_linkage=show)
                print("  [V]切词界  [R]重听  [W]拆听  [其他键继续] > ", end="", flush=True)
                ch = _wait_key_voice(_VP_PROMPT, "")
                if ch == "V":
                    show = not show
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                if ch == "R":
                    tts_speak(es_text, is_sentence=True)
                    time.sleep(0.3)
                    tts_speak(es_text, is_sentence=True)
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                if ch == "W":
                    print("  [拆听] ", end="", flush=True)
                    _play_word_by_word(es_text)
                    sys.stdout.write("\033[1A\033[2K")
                    sys.stdout.flush()
                    continue
                sys.stdout.write("\r\033[2K")
                sys.stdout.flush()
                break
            print(f"  再听一遍：{es_text}")
            sys.stdout.flush()
            tts_speak(es_text, is_sentence=True)
            if res["perfect"]:
                gs.pass_current()
                print("  ✓ 全对，自动通过。")
            else:
                gs.keep_current()
                print("  ✗ 有漏/多，已保留待重练。")
            sys.stdout.flush()
        print(f"-- 第 {gi} 组通关！--\n")
        sys.stdout.flush()
        time.sleep(0.5)
    print("-- 全部句子通关！--\n")
    sys.stdout.flush()


def _run_shadowing_listen():
    """模式4 纯听：只听+自判，含词界 + 拆听。复用 GroupSession。"""
    items = [{"es": s["es"], "zh": s["zh"]} for s in TEXTBOOK["sentences"]]
    groups = [items[i:i + GROUP_SIZE] for i in range(0, len(items), GROUP_SIZE)]

    for gi, group in enumerate(groups, 1):
        while True:
            gs = GroupSession(group)
            print(f"\n[跟读-纯听] 第 {gi}/{len(groups)} 组 — 按 V 切词界 · W 拆听 · Q 退出\n")
            sys.stdout.flush()
            restart_group = False
            while not gs.all_passed and not restart_group:
                item = gs.current
                es_text = item["es"]
                zh_text = item["zh"]
                passed_info = f"  ✓{gs.passed_count}/{gs.total}" if gs.passed_count > 0 else ""
                print(f"\n{'─' * 36}")
                print(f"  第 {gi}/{len(groups)} 组 · 第 {gs.current_index}/{gs.total} 句  {passed_info}")
                print(f"{'─' * 36}")
                sys.stdout.flush()
                for k in (1, 2):
                    print(f"  听原句（第{k}遍）：{es_text}")
                    sys.stdout.flush()
                    tts_speak(es_text, is_sentence=True)
                    time.sleep(0.3)
                show = False
                while True:
                    _print_sentence_with_linkage(es_text, show_linkage=show)
                    print("  [V]切词界  [R]重听  [W]拆听  [其他键继续] > ", end="", flush=True)
                    ch = _wait_key_voice(_VP_PROMPT, "")
                    if ch == "V":
                        show = not show
                        sys.stdout.write("\033[1A\033[2K")
                        sys.stdout.flush()
                        continue
                    if ch == "R":
                        tts_speak(es_text, is_sentence=True)
                        time.sleep(0.3)
                        tts_speak(es_text, is_sentence=True)
                        sys.stdout.write("\033[1A\033[2K")
                        sys.stdout.flush()
                        continue
                    if ch == "W":
                        print("  [拆听] ", end="", flush=True)
                        _play_word_by_word(es_text)
                        sys.stdout.write("\033[1A\033[2K")
                        sys.stdout.flush()
                        continue
                    sys.stdout.write("\r\033[2K")
                    sys.stdout.flush()
                    break
                print(f"  [答案] {es_text} → {zh_text}")
                sys.stdout.flush()
                tts_speak_zh(zh_text)
                print(f"  再听一遍：{es_text}")
                sys.stdout.flush()
                tts_speak(es_text, is_sentence=True)
                is_last = (gs.passed_count == gs.total - 1)
                s_menu = "  [S]重练本组" if is_last else ""
                while True:
                    j = _wait_key_voice(
                        _VP_PROMPT,
                        f"  [Y]过  [N]留  [R]重听  [W]拆听{s_menu}  [F]收藏  [Q]退出 > ",
                    )
                    if j == "Q":
                        return
                    if j == "Y":
                        gs.pass_current()
                        break
                    if j == "N":
                        gs.keep_current()
                        break
                    if j == "S" and is_last:
                        gs.reset_all()
                        tts_speak_zh("从头开始")
                        restart_group = True
                        break
                    if j == "R":
                        tts_speak(es_text, is_sentence=True)
                        time.sleep(0.3)
                        tts_speak(es_text, is_sentence=True)
                        continue
                    if j == "W":
                        print("  [拆听] ", end="", flush=True)
                        _play_word_by_word(es_text)
                        continue
                    if j == "F":
                        _favorite_words_from_sentence(es_text)
                        continue
            if restart_group:
                continue
            print(f"-- 第 {gi} 组通关！--\n")
            sys.stdout.flush()
            time.sleep(0.5)
            break
    print("-- 全部句子通关！--\n")
    sys.stdout.flush()


def _shadow_one(es_text, item, pq):
    """跟读一句"""
    while True:
        # TTS 念两遍原句，让用户熟悉发音
        print(f"   请听原句（第1遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text, is_sentence=True)
        time.sleep(0.3)
        print(f"   请听原句（第2遍）：{es_text}")
        sys.stdout.flush()
        tts_speak(es_text, is_sentence=True)
        time.sleep(0.3)

        # 录音跟读（两段式：按 Enter 开始，再按 Enter 结束）
        cmd = _prompt_record(
            "按 Enter 开始跟读",
            "  [S]跳过 [Q]退出 > ",
            voice_prompt=_VP_PROMPT,
        )
        if cmd == "Q":
            return "quit"
        if cmd == "S":
            pq.mark_skip(item)
            return
        # 正常录音完成（空字符串）

        # 对比：先播你的录音，再播一遍原句
        print("  -- 你的录音 --")
        sys.stdout.flush()
        stop_and_playback()
        time.sleep(0.5)
        print("  -- 原句 --")
        sys.stdout.flush()
        tts_speak(es_text, is_sentence=True)

        # 自判
        while True:
            judge = _wait_key_voice(
                _VP_PROMPT,
                "  跟读满意吗？[Y=满意 / N=再来一次 / S=别再问我 / F=收藏句中单词 / Q=退出] > ",
            )
            if judge == "Q":
                return "quit"
            elif judge == "S":
                pq.mark_skip(item)
                return
            elif judge == "F":
                _favorite_words_from_sentence(es_text)
                continue
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
                    tts_speak(es_text, is_sentence=True)
                    time.sleep(0.3)
                    tts_speak(es_text, is_sentence=True)
                else:
                    print(f"[听写-单词] 当前单词：{es_text}")
                    sys.stdout.flush()
                    tts_speak_async(es_text)
                if is_sentence:
                    user_input = _wait_line_voice(_VP_INPUT, "> ")
                else:
                    user_input = _wait_line_voice(_VP_INPUT, "> ")
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
                    correct = _strip_accents(cmd.strip().lower()) == _strip_accents(es_text.lower())

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
                    tts_speak_async(es_text, is_sentence=is_sentence)

            # 句子模式下提示收藏本句生词
            if is_sentence:
                ch = _wait_key_voice(_VP_PROMPT, "  收藏本句生词？[F]收藏 [Enter]继续 > ")
                if ch == "F":
                    _favorite_words_from_sentence(es_text)

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
            _wait_key_voice("本教材没有语法点，按任意键返回", "> ")
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

        choice = _wait_key_voice(_VP_GRAMMAR_INPUT, "请选择语法点（输入编号）> ")
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
            tts_speak(sentences[ei]['es'], is_sentence=True)

    # 子菜单
    while True:
        cmd = _wait_key_voice(_VP_PROMPT, "[R] 重听例句  [Q] 返回语法列表 > ")
        if cmd == "Q":
            return
        elif cmd == "R":
            for ei in g['examples']:
                if ei < len(sentences):
                    tts_speak(sentences[ei]['es'], is_sentence=True)


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
            choice = _wait_key_voice(_VP_PROMPT, "请选择 > ")
            if choice == "0":
                _marker("CMD", "进入模式 0 记忆导入")
                mode_0_memory_import()
            elif choice == "1":
                _marker("CMD", "进入模式 1 听西语说中文")
                mode_1_listen_es_say_zh()
            elif choice == "2":
                _marker("CMD", "进入模式 2 听中文说西语")
                mode_2_listen_zh_say_es()
            elif choice == "3":
                _marker("CMD", "进入模式 3 听写")
                mode_3_dictation()
            elif choice == "4":
                _marker("CMD", "进入模式 4 跟读")
                mode_4_shadowing()
            elif choice == "5":
                _marker("CMD", "进入模式 5 混着来")
                mode_5_mixed()
            elif choice == "G":
                _marker("CMD", "进入语法讲解")
                mode_g_grammar()
            elif choice == "T":
                _marker("CMD", "选择教材")
                new_tb = select_textbook()
                if new_tb is not None:
                    TEXTBOOK = new_tb
            elif choice == "Q":
                _marker("CMD", "退出")
                print("\nAdiós! \n")
                break
            else:
                _marker("CMD", f"无效选项: {choice!r}")
                print("  无效选项，请重新选择。")
                sys.stdout.flush()
    finally:
        cleanup_temp_files()


if __name__ == "__main__":
    main()
