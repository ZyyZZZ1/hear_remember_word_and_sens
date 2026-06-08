"""
conftest.py —— 自动化测试公共工具
提供：进程启动/停止、按键注入、stdout 读取、断言函数
"""

import subprocess
import sys
import os
import time
import threading
import glob as globmod

PROGRAM = os.path.join(os.path.dirname(__file__), "main.py")
TIMEOUT = 10  # 等待 stdout 的超时秒数

# ── 教材预期值（来自总计划 §1.5）──────────────────────────
EXPECTED_VOCAB = [
    "Ricardo", "Rosa", "nuestra", "lengua", "universidad",
    "este", "país", "del", "González", "ahora", "Enseño", "vuestra",
]
EXPECTED_GRAMMAR = [
    "介词 DE",
    "介词 EN",
]
EXPECTED_MENU_ITEMS = ["1", "2", "3", "4", "5", "G", "Q"]


class ProgramRunner:
    """管理被测程序子进程的启动、输入、输出读取和停止"""

    def __init__(self):
        self.proc = None
        self.output_lines = []
        self._lock = threading.Lock()
        self._running = False
        self._reader_thread = None

    def start(self):
        """启动程序子进程，开始后台读取 stdout"""
        self.output_lines = []
        # 设置子进程 UTF-8 编码环境，避免特殊字符丢失
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, "-u", PROGRAM],  # -u 无缓冲模式
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",      # 必须显式指定，text=True 在 Windows 上默认用 GBK
            bufsize=1,
            cwd=os.path.dirname(PROGRAM),
            env=env,
        )
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self):
        """后台线程：逐行读取 stdout"""
        try:
            for line in self.proc.stdout:
                with self._lock:
                    self.output_lines.append(line)
        except Exception:
            pass
        finally:
            self._running = False

    def send(self, text):
        """向程序 stdin 发送文本"""
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(text + "\n")
                self.proc.stdin.flush()
            except Exception:
                pass

    def send_key(self, key):
        """发送单个按键"""
        self.send(key)

    def get_output(self):
        """获取当前所有 stdout 行"""
        with self._lock:
            return "".join(self.output_lines)

    def get_lines(self):
        """获取当前所有 stdout 行（列表）"""
        with self._lock:
            return list(self.output_lines)

    def wait_for_text(self, text, timeout=TIMEOUT):
        """等待 stdout 中出现特定文字，返回 True 如果等到"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            output = self.get_output()
            if text in output:
                return True
            time.sleep(0.15)
        return False

    def wait_for_any(self, texts, timeout=TIMEOUT):
        """等待 stdout 中出现任意一个文字，返回匹配的文本或 None"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            output = self.get_output()
            for t in texts:
                if t in output:
                    return t
            time.sleep(0.15)
        return None

    def count_occurrences(self, text):
        """统计 stdout 中某文字出现次数"""
        return self.get_output().count(text)

    def select_textbook_and_wait_menu(self, index=1):
        """处理教材选择：如果有选择菜单则选第 index 本，然后等待主菜单"""
        # 等教材选择界面出现（程序需要解析教材文件，需要更长时间）
        self.wait_for_any(["请选择教材", "西班牙语陪练"], timeout=10)
        out = self.get_output()
        if "请选择教材" in out:
            self.send(str(index))
            time.sleep(0.5)
        # 等待主菜单
        self.wait_for_text("西班牙语陪练", timeout=5)

    def stop(self):
        """停止子进程"""
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        self._running = False

    @property
    def is_running(self):
        """进程是否仍在运行"""
        return self.proc is not None and self.proc.poll() is None


def assert_contains(output, text, doc_ref):
    """断言 output 包含 text。doc_ref 标注来自测试用例的哪一条"""
    assert text in output, f"[{doc_ref}] 期望 stdout 包含 '{text}'，但未找到"


def assert_not_contains(output, text, doc_ref):
    """断言 output 不包含 text"""
    assert text not in output, f"[{doc_ref}] 期望 stdout 不包含 '{text}'，但找到了"


def scan_audio_files(directory):
    """扫描目录中的音频文件，返回文件路径列表"""
    patterns = ["*.wav", "*.mp3", "*.flac", "*.ogg"]
    files = []
    for p in patterns:
        files.extend(globmod.glob(os.path.join(directory, p)))
    return files


def extract_words_from_output(output):
    """从输出中提取模式 3 的当前单词列表。
    查找所有 '当前单词：XXX' 模式的文本"""
    import re
    matches = re.findall(r'当前单词：(\S+)', output)
    return matches
