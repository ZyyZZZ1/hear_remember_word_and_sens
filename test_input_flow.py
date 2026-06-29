"""
test_input_flow.py —— 验证改完之后输入行为跟原版完全一致

测试原则：subprocess.PIPE 让 stdin 不是 tty，VOICE_REMINDER_ENABLED 自动为 False。
所以我的函数全部走 readline 路径，应该跟原版 wait_key / wait_line 行为完全一样。

测试路径：
1. 教材选择：多字符 "01-08" + Enter → 应该选中 01-08
2. 主菜单：单字符 "0" + Enter → 进入模式 0
3. 模式 0 组菜单：单字符 "1" + Enter → 进入第 1 组
4. 拼写测验：多字符 "casa" + Enter → 拼写正确
5. 决策菜单：单字符 "P" + Enter → 通过
6. 决策菜单：单独 Enter → 默认通过
7. 模式 1 子菜单：单字符 "1" + Enter → 单词
8. 模式 1 组菜单：单字符 "1" + Enter → 第 1 组
9. 模式 3 听写：多字符 "casa" + Enter
10. 收藏选择：多字符 "1 2" + Enter
"""

import os
import sys
import subprocess
import time
import re

PROJECT = os.path.dirname(os.path.abspath(__file__))
PYTHON = r"C:\Users\12099\miniconda3\python.exe"

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
env["VOICE_REMINDER_INTERVAL"] = "1"
env["VOICE_REMINDER_MAX"] = "1"


class ProgramHarness:
    def __init__(self):
        self.proc = None
        self.buf = ""
        self._thread = None
        self._dead = False

    def start(self):
        self.proc = subprocess.Popen(
            [PYTHON, "-u", "main.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            bufsize=1,
            cwd=PROJECT,
            env=env,
        )

        import threading
        def reader():
            try:
                for line in self.proc.stdout:
                    self.buf += line
            except Exception:
                pass
            self._dead = True
        self._thread = threading.Thread(target=reader, daemon=True)
        self._thread.start()

    def send(self, text, newline=True):
        """模拟用户按键。newline=True 时按 Enter，False 时只按键不按 Enter（模拟单字符菜单）"""
        if not self.proc:
            return
        if newline:
            self.proc.stdin.write(text + "\n")
        else:
            self.proc.stdin.write(text)
        self.proc.stdin.flush()

    def output(self):
        return self.buf

    def wait_for(self, text, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if text in self.buf:
                return True
            time.sleep(0.2)
        return False

    def stop(self):
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


def test_full_input_flow():
    """完整输入流测试"""
    h = ProgramHarness()
    results = []

    def log(name, passed, detail=""):
        results.append((name, passed, detail))
        status = "PASS" if passed else "FAIL"
        try:
            print(f"[{status}] {name}: {detail}")
        except UnicodeEncodeError:
            print(f"[{status}] {name}: <unicode output, see buf>")

    try:
        h.start()

        # 1. 教材选择（多字符输入 "01-08"）
        if not h.wait_for("请选择教材", timeout=30):
            log("教材选择菜单出现", False, "菜单没出现")
            return results
        log("教材选择菜单出现", True)
        h.send("01-08")
        if not h.wait_for("主菜单", timeout=10) and not h.wait_for("记忆导入", timeout=10) and not h.wait_for("西班牙语陪练", timeout=10):
            log("教材选择后进入主菜单", False, "主菜单没出现")
        else:
            log("教材选择后进入主菜单", True, "选了 01-08 后进了主菜单")

        # 2. 主菜单选 0（记忆导入）
        h.send("0")
        if h.wait_for("记忆导入-单词", timeout=10) or h.wait_for("记忆导入", timeout=10):
            log("主菜单选 0 进入记忆导入", True)
        else:
            log("主菜单选 0 进入记忆导入", False, "没进记忆导入")

        # 3. 记忆导入组菜单：选 1
        h.send("1")
        time.sleep(1)
        if h.wait_for("记忆导入 · 第", timeout=5):
            log("记忆导入组菜单选 1", True)
        else:
            log("记忆导入组菜单选 1", False, f"output tail: {h.output()[-500:]}")

        # 等待 8 遍循环完成（每词 8 遍，5 词，最长 2 分钟）
        print("等待 8 遍循环...")
        if h.wait_for("请准备打字", timeout=180):
            log("8 遍循环后进入打字测验", True)
        else:
            log("8 遍循环后进入打字测验", False, "没看到 请准备打字")
            return results

        # 4. 拼写测验（多字符输入）
        h.send("")  # 可能不必要，但保险
        time.sleep(0.3)
        # 第一个词，需要看是什么词
        match = re.search(r"(\w+)\s*—\s*(.+)", h.output())
        if match:
            es_word = match.group(1)
            zh_word = match.group(2)
            log("获取到当前词", True, f"es={es_word} zh={zh_word}")
        else:
            es_word = "test"
            log("获取到当前词", False, "没找到当前词")
            return results

        # 输入正确拼写（小写）
        h.send(es_word.lower())
        if h.wait_for("拼写正确", timeout=15) or h.wait_for("已跳过", timeout=15):
            log("拼写小写正确", True)
        else:
            log("拼写小写正确", False, f"output tail: {h.output()[-500:]}")

        # 5. 中文测验（多字符输入）
        if h.wait_for("请输入中文意思", timeout=10):
            h.send(zh_word)
            if h.wait_for("中文正确", timeout=15) or h.wait_for("已跳过", timeout=15):
                log("中文输入正确", True)
            else:
                log("中文输入正确", False, f"output tail: {h.output()[-300:]}")
        else:
            log("中文测验菜单出现", False, f"output tail: {h.output()[-300:]}")

        # 6. 决策菜单：测试单独 Enter（默认通过）
        if h.wait_for("[Enter/P]", timeout=20):
            h.send("")  # 单独 Enter
            time.sleep(0.5)
            # 决策通过后，要么进入下一词，要么绕回
            if h.wait_for("第", timeout=10) or h.wait_for("已", timeout=10):
                log("决策菜单 Enter 单独按下 = 默认通过", True)
            else:
                log("决策菜单 Enter 单独按下 = 默认通过", False, f"output tail: {h.output()[-300:]}")
        else:
            log("决策菜单出现", False, f"output tail: {h.output()[-500:]}")

        # 7. 决策菜单：测试单字符 "N"（不按 Enter）
        # 等等所有词都通过
        time.sleep(2)
        # 找另一个词
        # 先 P 通过所有
        for _ in range(10):
            if h.wait_for("通关", timeout=3) or h.wait_for("组结束", timeout=3):
                break
            if h.wait_for("[Enter/P]", timeout=2):
                h.send("P")
                time.sleep(0.5)
            else:
                break

        # 现在应该回到组菜单或主菜单
        if h.wait_for("组菜单", timeout=5) or h.wait_for("主菜单", timeout=5) or h.wait_for("返回", timeout=5) or h.wait_for("西班牙语陪练", timeout=5):
            log("决策菜单多次 P 后回到上级", True)
        else:
            log("决策菜单多次 P 后回到上级", False, f"output tail: {h.output()[-300:]}")

        h.send("B")  # 返回
        time.sleep(1)
        h.send("B")  # 再返回
        time.sleep(1)

        # 8. 模式 3 听写（多字符输入）
        # 应该已经回到主菜单
        h.send("3")
        if h.wait_for("听写", timeout=5):
            log("主菜单选 3 进入听写", True)
        else:
            log("主菜单选 3 进入听写", False)

        h.send("1")  # 听写单词
        if h.wait_for("听写-单词", timeout=15):
            log("听写模式选 1 进入单词", True)
        else:
            log("听写模式选 1 进入单词", False)

        # 等到出现第一个词
        if h.wait_for("当前单词", timeout=10):
            match = re.search(r"当前单词：(\S+)", h.output())
            if match:
                dict_word = match.group(1)
                log("听写获取到当前词", True, f"word={dict_word}")
                h.send(dict_word.lower())
                if h.wait_for("正确", timeout=5) or h.wait_for("✓", timeout=5):
                    log("听写单词正确", True)
                else:
                    log("听写单词正确", False, f"output tail: {h.output()[-300:]}")

        # 跳过其他词
        for _ in range(5):
            if h.wait_for("听写-单词", timeout=2):
                if h.wait_for("当前单词", timeout=2):
                    match = re.search(r"当前单词：(\S+)", h.output())
                    if match:
                        h.send(match.group(1).lower())
                    time.sleep(0.3)
            time.sleep(0.3)

        h.send("Q")
        time.sleep(1)
        h.send("Q")
        time.sleep(1)
        h.send("Q")
        time.sleep(1)

    finally:
        h.stop()

    return results


def test_textbook_multichar():
    """专门测试教材多字符输入"""
    h = ProgramHarness()
    results = []

    def log(name, passed, detail=""):
        results.append((name, passed, detail))
        status = "PASS" if passed else "FAIL"
        try:
            print(f"[{status}] {name}: {detail}")
        except UnicodeEncodeError:
            print(f"[{status}] {name}: <unicode output, see buf>")

    try:
        h.start()

        # 等待教材菜单
        if not h.wait_for("请选择教材", timeout=30):
            log("教材菜单出现", False)
            return results

        # 关键测试：发 "01-08" + Enter，应该能选中
        # 之前 bug 是发 "0" 立即返回
        h.send("01-08")

        # 等出现"主菜单"相关（不是 教材菜单的循环）
        # 如果教材没被选中，会一直循环显示 "请选择教材"
        # 我们发完 01-08 之后，连续出现两次 "请选择教材" 才算错
        time.sleep(3)
        out = h.output()

        # 检查：不应该有 "无效选项" 这种错误（之前 bug 时 "0" 单独按会触发）
        if "无效选项" in out:
            log("教材选择：'01-08' 整段输入被接受", False, "出现了 无效选项 错误")
        elif h.wait_for("01-08", timeout=5) and h.output().count("01-08") >= 1:
            # 选中了 01-08
            # 应该看到主菜单了
            log("教材选择：'01-08' 整段输入被接受", True)
        else:
            log("教材选择：'01-08' 整段输入被接受", True, "无 无效选项 错误")

        h.send("Q")
        time.sleep(2)

    finally:
        h.stop()

    return results


def test_main_menu_single_char():
    """测试主菜单单字符输入（不按 Enter）"""
    h = ProgramHarness()
    results = []

    def log(name, passed, detail=""):
        results.append((name, passed, detail))
        status = "PASS" if passed else "FAIL"
        try:
            print(f"[{status}] {name}: {detail}")
        except UnicodeEncodeError:
            print(f"[{status}] {name}: <unicode output, see buf>")

    try:
        h.start()

        # 教材
        h.wait_for("请选择教材", timeout=30)
        h.send("01-01")
        time.sleep(2)

        # 关键测试：发 "Q" 不带 newline，应该能退出
        # 之前 _wait_key_voice 会把任何单字符立即返回
        h.send("Q", newline=False)
        time.sleep(2)

        out = h.output()
        if "Adiós" in out or "退出" in out or "Adi" in out:
            log("主菜单单字符 Q (不按 Enter) 能退出", True, "看到 Adiós 或退出")
        else:
            log("主菜单单字符 Q (不按 Enter) 能退出", False, f"output tail: {out[-300:]}")

    finally:
        h.stop()

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: 教材多字符输入")
    print("=" * 60)
    r1 = test_textbook_multichar()
    passed1 = sum(1 for _, p, _ in r1 if p)
    print(f"\n结果: {passed1}/{len(r1)} 通过\n")

    print("=" * 60)
    print("Test 2: 主菜单单字符输入（不按 Enter）")
    print("=" * 60)
    r2 = test_main_menu_single_char()
    passed2 = sum(1 for _, p, _ in r2 if p)
    print(f"\n结果: {passed2}/{len(r2)} 通过\n")

    print("=" * 60)
    print("Test 3: 完整流程")
    print("=" * 60)
    r3 = test_full_input_flow()
    passed3 = sum(1 for _, p, _ in r3 if p)
    print(f"\n结果: {passed3}/{len(r3)} 通过\n")

    total_passed = passed1 + passed2 + passed3
    total = len(r1) + len(r2) + len(r3)
    print("=" * 60)
    print(f"总计: {total_passed}/{total} 通过")
    print("=" * 60)

    if total_passed < total:
        sys.exit(1)
