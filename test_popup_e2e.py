"""
test_popup_e2e.py —— popup_trainer.py 端到端测试

测试：
- E2E-1: 程序启动 → 热键注册成功 + 真实控制台创建 + 启动即隐藏
- E2E-2: 模拟 WM_HOTKEY → toggle 控制台显隐（日志 + 跨进程 IsWindowVisible 观测）
- E2E-3: 占用回退（占住主组合 → 启动 → 日志含 fallback）
- E2E-4: main.main() 集成（POPUP_TEST 模式窗口可见，main 跑得起来）
- E2E-5: 终端版 main.py 回归无破坏（用 test_runner.py 的 TC-01/02/03 跑一遍）

用 subprocess.Popen(creationflags=CREATE_NEW_CONSOLE) 让子进程带真控制台。
"""

import os
import sys
import subprocess
import time
import ctypes
import ctypes.wintypes as w
import win32gui
import win32con

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CREATE_NEW_CONSOLE = 0x00000010
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_A = 0x41

user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.PostMessageW.restype = w.BOOL

PYTHON = r"C:\Users\12099\miniconda3\python.exe"
PROJECT = r"D:\程序\脚本\01-08"
POPUP_SCRIPT = os.path.join(PROJECT, "popup_trainer.py")
MAIN_SCRIPT = os.path.join(PROJECT, "main.py")


def parse_hwnd_from_log(log_path):
    """从 popup 启动日志中解析 console_hwnd。"""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if "[POPUP] console_hwnd=" in line:
                    hex_str = line.split("console_hwnd=0x")[1].strip()
                    return int(hex_str, 16)
                if "[POPUP] message_hwnd=" in line:
                    hex_str = line.split("message_hwnd=0x")[1].strip()
                    return int(hex_str, 16)
    except Exception as e:
        print(f"  [解析失败] {e}")
    return 0


def parse_all_hwnds(log_path):
    """解析 console_hwnd 和 message_hwnd。"""
    hwnds = {"console": 0, "message": 0}
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if "[POPUP] console_hwnd=0x" in line:
                    hwnds["console"] = int(line.split("console_hwnd=0x")[1].strip(), 16)
                elif "[POPUP] message_hwnd=0x" in line:
                    hwnds["message"] = int(line.split("message_hwnd=0x")[1].strip(), 16)
    except Exception:
        pass
    return hwnds


def start_popup(log_path, test_mode=False, env_extra=None):
    """启动 popup_trainer.py 子进程（带真控制台）。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["POPUP_LOG_STDOUT"] = "1"
    if test_mode:
        env["POPUP_TEST"] = "1"
    if env_extra:
        env.update(env_extra)

    with open(log_path, "w", encoding="utf-8") as logf:
        p = subprocess.Popen(
            [PYTHON, POPUP_SCRIPT],
            cwd=PROJECT,
            creationflags=CREATE_NEW_CONSOLE,
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
    return p


def stop_popup(p, timeout=3):
    """停止 popup 子进程。"""
    try:
        p.terminate()
        p.wait(timeout=timeout)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def get_console_window(console_title="SpanishDrill"):
    """通过 FindWindow 找控制台窗口（conhost 创建的）。"""
    return win32gui.FindWindow(None, console_title)


def is_visible(hwnd):
    return bool(win32gui.IsWindowVisible(hwnd))


# ── 测试 ──

def E2E_1_startup():
    """E2E-1: 启动 → 真实控制台 + 热键注册 + 启动即隐藏"""
    print("\n[E2E-1] 启动 popup_trainer.py (普通模式) ...")
    log_path = os.path.join(PROJECT, "e2e1.log")
    p = start_popup(log_path, test_mode=False)
    time.sleep(2.5)  # 等热键注册 + 隐藏

    # 读日志
    log = ""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log = f.read()
    except Exception:
        pass

    # 证据
    hwnds = parse_all_hwnds(log_path)
    print(f"  日志前 600 字:\n{log[:600]}")
    print(f"  解析 hwnds: {hwnds}")

    # 找控制台窗口
    title_hwnd = get_console_window("SpanishDrill")
    print(f"  FindWindow('SpanishDrill') = 0x{title_hwnd:X}")

    # 检查启动即隐藏
    visible_at_start = is_visible(title_hwnd) if title_hwnd else None
    print(f"  启动后 IsWindowVisible = {visible_at_start}")

    # 检查热键注册日志
    has_registered = "hotkey registered Ctrl+Shift+A" in log
    has_hidden = "startup hidden" in log
    has_console_hwnd = hwnds["console"] != 0

    stop_popup(p)

    passed = has_registered and has_hidden and has_console_hwnd
    print(f"\n  证据汇总：")
    print(f"    [POPUP] hotkey registered Ctrl+Shift+A  = {has_registered}")
    print(f"    [POPUP] startup hidden                  = {has_hidden}")
    print(f"    [POPUP] console_hwnd=0x... (非0)         = {has_console_hwnd} (hwnd=0x{hwnds['console']:X})")
    if passed:
        print("  [PASS] 启动流程正确")
        return True
    else:
        print("  [FAIL] 启动流程有缺项")
        return False


def E2E_2_toggle():
    """E2E-2: 模拟 WM_HOTKEY → toggle 控制台显隐"""
    print("\n[E2E-2] 模拟 WM_HOTKEY 触发 toggle (POPUP_TEST=1) ...")
    log_path = os.path.join(PROJECT, "e2e2.log")
    p = start_popup(log_path, test_mode=True)  # 不自动隐藏
    time.sleep(2.5)  # 等热键注册完成

    log0 = ""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log0 = f.read()
    except Exception:
        pass

    hwnds = parse_all_hwnds(log_path)
    msg_hwnd = hwnds["message"]
    print(f"  message_hwnd = 0x{msg_hwnd:X}")
    print(f"  日志初:\n{log0[:400]}")

    # 启动后可见 (POPUP_TEST 模式不隐藏)
    title_hwnd = get_console_window("SpanishDrill")
    print(f"  启动时 console IsWindowVisible = {is_visible(title_hwnd) if title_hwnd else None}")

    # 模拟 WM_HOTKEY
    if msg_hwnd:
        user32.PostMessageW(msg_hwnd, WM_HOTKEY, 1, 0)
        print(f"  PostMessageW(WM_HOTKEY) 到 message_hwnd 已发")
        time.sleep(0.5)

    # 再读日志
    log1 = ""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log1 = f.read()
    except Exception:
        pass

    has_toggle = "toggle hide" in log1 or "toggle show" in log1
    print(f"  PostMessage 后日志增量:\n{log1[len(log0):]}")

    # 第一次 toggle: 可见→隐藏
    visible_after = is_visible(title_hwnd) if title_hwnd else None
    print(f"  第一次 toggle 后 IsWindowVisible = {visible_after}")

    # 再发一次 toggle: 隐藏→显示
    if msg_hwnd:
        user32.PostMessageW(msg_hwnd, WM_HOTKEY, 1, 0)
        time.sleep(0.5)
    visible_after2 = is_visible(title_hwnd) if title_hwnd else None
    print(f"  第二次 toggle 后 IsWindowVisible = {visible_after2}")

    log2 = ""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log2 = f.read()
    except Exception:
        pass
    toggle_count = log2.count("toggle ")
    print(f"  日志中 toggle 出现次数 = {toggle_count}")

    stop_popup(p)

    passed = has_toggle and toggle_count >= 2 and visible_after == False and visible_after2 == True
    print(f"\n  证据汇总：")
    print(f"    [POPUP] toggle 日志（>=2次）       = {toggle_count >= 2} (实际{toggle_count}次)")
    print(f"    第一次 toggle 后 IsWindowVisible=False = {visible_after == False}")
    print(f"    第二次 toggle 后 IsWindowVisible=True  = {visible_after2 == True}")
    if passed:
        print("  [PASS] toggle 显隐切换正常")
        return True
    else:
        print("  [FAIL] toggle 行为异常")
        return False


def E2E_3_occupied():
    """E2E-3: 主组合被占用 → popup 注册失败"""
    print("\n[E2E-3] 占住主组合 Ctrl+Shift+A → 启动 → 期待注册失败 ...")
    # 占住主组合
    import win32gui
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = lambda h, m, w, l: 0
    wc.lpszClassName = "E2E3Holder"
    wc.hInstance = win32gui.GetModuleHandle(None)
    try:
        win32gui.RegisterClass(wc)
    except Exception:
        pass
    holder_hwnd = win32gui.CreateWindowEx(
        0, "E2E3Holder", "holder", 0, 0, 0, 0, 0,
        win32con.HWND_MESSAGE, 0, wc.hInstance, None
    )
    ok = user32.RegisterHotKey(holder_hwnd, 100, MOD_CONTROL | MOD_SHIFT, VK_A)
    print(f"  占用主组合 RegisterHotKey = {ok}")

    try:
        log_path = os.path.join(PROJECT, "e2e3.log")
        p = start_popup(log_path, test_mode=True)
        time.sleep(2.5)

        log = ""
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = f.read()
        except Exception:
            pass

        print(f"  日志:\n{log[:600]}")

        has_failed = "hotkey failed" in log

        stop_popup(p)
    finally:
        user32.UnregisterHotKey(holder_hwnd, 100)
        win32gui.DestroyWindow(holder_hwnd)

    passed = has_failed
    print(f"\n  证据汇总：")
    print(f"    [POPUP] hotkey failed = {has_failed}")
    if passed:
        print("  [PASS] 占用后正确报告失败")
        return True
    else:
        print("  [FAIL] 占用后未报告失败")
        return False


def E2E_4_main_integration():
    """E2E-4: main.main() 集成（POPUP_TEST 模式窗口可见，能进教材选择）"""
    print("\n[E2E-4] main.main() 集成 (POPUP_TEST=1, 子进程喂 '01-01') ...")
    log_path = os.path.join(PROJECT, "e2e4.log")
    # 用 subprocess 而非 Popen 加 CREATE_NEW_CONSOLE 启动并通过 stdin 管道
    env = os.environ.copy()
    env["POPUP_TEST"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["POPUP_LOG_STDOUT"] = "1"

    proc = subprocess.Popen(
        [PYTHON, POPUP_SCRIPT],
        cwd=PROJECT,
        creationflags=CREATE_NEW_CONSOLE,
        env=env,
        stdin=subprocess.PIPE,
        stdout=open(log_path, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    # 等热键注册 + main 启动到教材选择
    time.sleep(3.0)

    # 喂 "01-01" 选第一个教材
    try:
        proc.stdin.write("01-01\n")
        proc.stdin.flush()
    except Exception as e:
        print(f"  [stdin 失败] {e}")
    time.sleep(2.0)

    # 喂 Q 退出主菜单
    try:
        proc.stdin.write("Q\n")
        proc.stdin.flush()
    except Exception:
        pass
    time.sleep(0.5)

    stop_popup(proc)

    log = ""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log = f.read()
    except Exception:
        pass

    print(f"  日志 (前 1200 字):\n{log[:1200]}")

    has_main_title = "西班牙语陪练" in log
    has_select = "请选择教材" in log or "自动加载教材" in log
    has_menu = "[0] 记忆导入" in log or "[" in log and "]" in log
    has_popup_registered = "hotkey registered Ctrl+Shift+A" in log

    passed = has_main_title and has_select and has_popup_registered
    print(f"\n  证据汇总：")
    print(f"    日志含 '西班牙语陪练'                = {has_main_title}")
    print(f"    日志含 '请选择教材' 或 '自动加载教材' = {has_select}")
    print(f"    日志含 [POPUP] hotkey registered/fallback = {has_popup_registered}")
    if passed:
        print("  [PASS] main 集成成功")
        return True
    else:
        print("  [FAIL] main 集成失败")
        return False


def E2E_5_main_no_regression():
    """E2E-5: 终端版 main.py 跑测试_runner 的 TC-01/02/03 验证无回归"""
    print("\n[E2E-5] 终端版 main.py 无回归 (TC-01/02/03) ...")
    # 用现有的 test_runner 里的子测试
    sys.path.insert(0, PROJECT)
    try:
        from test_tc01 import test_tc01
        from test_tc02 import test_tc02
        from test_tc03 import test_tc03

        # TC-01
        print("  跑 TC-01 ...")
        t1_assertions, t1_out = test_tc01()
        t1_pass = all(not a[2].startswith("FAIL") for a in t1_assertions)
        print(f"  TC-01: {'PASS' if t1_pass else 'FAIL'}")

        # TC-02
        print("  跑 TC-02 ...")
        t2_assertions, t2_out = test_tc02()
        t2_pass = all(not a[2].startswith("FAIL") for a in t2_assertions)
        print(f"  TC-02: {'PASS' if t2_pass else 'FAIL'}")

        # TC-03
        print("  跑 TC-03 ...")
        t3_assertions, t3_out = test_tc03()
        t3_pass = all(not a[2].startswith("FAIL") for a in t3_assertions)
        print(f"  TC-03: {'PASS' if t3_pass else 'FAIL'}")

        passed = t1_pass and t2_pass and t3_pass
        print(f"\n  证据汇总：")
        print(f"    TC-01 启动菜单       = {t1_pass}")
        print(f"    TC-02 模式入口       = {t2_pass}")
        print(f"    TC-03 Q 退出         = {t3_pass}")
        if passed:
            print("  [PASS] 终端版无回归")
            return True
        else:
            print("  [FAIL] 终端版回归")
            return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("  popup_trainer.py 端到端测试 + 回归测试")
    print("=" * 60)

    r1 = E2E_1_startup()
    r2 = E2E_2_toggle()
    r3 = E2E_3_occupied()
    r4 = E2E_4_main_integration()
    r5 = E2E_5_main_no_regression()

    print("\n" + "=" * 60)
    print("  汇总")
    print("=" * 60)
    results = [
        ("E2E-1 启动流程（控制台+热键+启动隐藏）", r1),
        ("E2E-2 toggle 显隐切换", r2),
        ("E2E-3 占用主组合时注册失败", r3),
        ("E2E-4 main.main() 集成", r4),
        ("E2E-5 终端版无回归", r5),
    ]
    for name, ok in results:
        print(f"  {name:40s} : {'PASS' if ok else 'FAIL'}")
    if all(r for _, r in results):
        print("\n  全部 PASS。")
        sys.exit(0)
    else:
        print("\n  有 FAIL。")
        sys.exit(1)


if __name__ == "__main__":
    main()
