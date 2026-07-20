"""Debug specific failures"""
import os, sys, time, re, subprocess, threading

PROJECT = os.path.dirname(os.path.abspath(__file__))
PYTHON = r"C:\Users\12099\miniconda3\python.exe"

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
env["VOICE_REMINDER_INTERVAL"] = "1"
env["VOICE_REMINDER_MAX"] = "1"


class H:
    def __init__(self):
        self.buf = ""
        self.proc = None
    def start(self):
        self.proc = subprocess.Popen(
            [PYTHON, "-u", "main.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", bufsize=1, cwd=PROJECT, env=env,
        )
        def reader():
            try:
                for line in self.proc.stdout:
                    self.buf += line
            except: pass
        threading.Thread(target=reader, daemon=True).start()
    def send(self, t, nl=True):
        self.proc.stdin.write(t + ("\n" if nl else ""))
        self.proc.stdin.flush()
    def wait(self, t, to=15):
        end = time.time() + to
        while time.time() < end:
            if t in self.buf: return True
            time.sleep(0.1)
        return False
    def stop(self):
        try: self.proc.stdin.close()
        except: pass
        try: self.proc.terminate()
        except: pass


print("=" * 60)
print("Test: 决策菜单 Enter 单独按下")
print("=" * 60)
h = H()
h.start()
h.wait("请选择教材", 30)
h.send("01-08")
h.wait("记忆导入-单词", 10) or h.wait("记忆导入", 10)
h.send("1")
h.wait("记忆导入 · 第", 5)
print("等待打字...")
h.wait("请准备打字", 180)
print(f"  ... 看到 请准备打字 at {time.time():.0f}")

# 看当前词
m = re.search(r"(\w+)\s*—\s*(.+)", h.buf)
es = m.group(1) if m else "test"
zh = m.group(2) if m else "test"
print(f"  当前词: {es} / {zh}")

# 输入拼写
h.send(es.lower())
h.wait("拼写正确", 15)
print(f"  ... 拼写 OK at {time.time():.0f}")

# 输入中文
h.wait("请输入中文意思", 10)
h.send(zh)
h.wait("中文正确", 15)
print(f"  ... 中文 OK at {time.time():.0f}")

# 现在应该到决策菜单
print(f"  当前 buf tail: {repr(h.buf[-300:])}")
print(f"  contains [Enter/P]: {'[Enter/P]' in h.buf}")

# 测试 Enter 单独按下
h.send("")  # 单独 Enter
print(f"  ... sent empty at {time.time():.0f}")
time.sleep(5)
print(f"  buf tail after Enter: {repr(h.buf[-500:])}")

h.stop()
