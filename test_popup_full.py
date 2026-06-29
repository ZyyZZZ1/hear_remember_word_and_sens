"""
test_popup_full.py —— popup_trainer 综合测试
1. 冒烟测试（热键机制）
2. popup 启动测试（hwnd + hotkey + startup hidden）
3. 终端版回归（main.py 行为不变）
"""
import os, sys, time, subprocess, traceback
import ctypes, ctypes.wintypes as w

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PYTHON = r"C:\Users\12099\miniconda3\python.exe"
PROJECT = r"D:\程序\脚本\01-08"

results = []  # (id, name, status, evidence)

def record(tc_id, name, ok, evidence):
    status = "PASS" if ok else "FAIL"
    results.append((tc_id, name, status, evidence))
    print(f"\n[{tc_id}] {name} ... {status}")
    print(f"  evidence: {evidence}")


# ── 1. 冒烟测试（复用 test_popup_hotkey_smoke）──
print("=" * 60)
print("阶段 1: 热键机制冒烟测试")
print("=" * 60)

import win32gui, win32con
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_A = 0x41  # popup 实际使用 Ctrl+Shift+A
user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.PostMessageW.restype = w.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
user32.PeekMessageW.restype = w.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
user32.TranslateMessage.restype = w.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
user32.DispatchMessageW.restype = ctypes.c_long

state = {"WM_HOTKEY_count": 0, "got_event": False}
def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_HOTKEY:
        state["WM_HOTKEY_count"] += 1
        state["got_event"] = True
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

_wc_registered = [False]
def make_msg_hwnd(name="TestWnd"):
    if not _wc_registered[0]:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = wnd_proc
        wc.lpszClassName = name
        wc.hInstance = win32gui.GetModuleHandle(None)
        win32gui.RegisterClass(wc)
        _wc_registered[0] = True
    return win32gui.CreateWindowEx(
        0, name, "Test", 0, 0, 0, 0, 0, win32con.HWND_MESSAGE,
        0, win32gui.GetModuleHandle(None), None,
    )

# PTC-01: RegisterHotKey 注册成功（与 popup 使用相同组合）
hwnd = make_msg_hwnd()
ok = user32.RegisterHotKey(hwnd, 1, MOD_CONTROL | MOD_SHIFT, VK_A)
err = kernel32.GetLastError()
record("PTC-01", "RegisterHotKey 注册 Ctrl+Shift+A", bool(ok),
       f"RegisterHotKey 返回={ok} GetLastError={err} hwnd=0x{hwnd:X}")
user32.UnregisterHotKey(hwnd, 1)
win32gui.DestroyWindow(hwnd)
state["WM_HOTKEY_count"] = 0
state["got_event"] = False

# PTC-03: PostMessage 消息分发
hwnd = make_msg_hwnd()  # 复用已注册的 TestWnd class
ok = user32.PostMessageW(hwnd, WM_HOTKEY, 1, 0)
start = time.time()
msg = w.MSG()
while time.time() - start < 1.0:
    if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, win32con.PM_REMOVE):
        if msg.message == WM_QUIT if False else False:
            break
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
        if state["got_event"]:
            break
    else:
        time.sleep(0.01)
record("PTC-03", "PostMessage 消息分发", state["got_event"],
       f"PostMessage 返回={ok}, WM_HOTKEY_count={state['WM_HOTKEY_count']}, got_event={state['got_event']}, elapsed={time.time()-start:.3f}s")
win32gui.DestroyWindow(hwnd)
WM_QUIT = 0x0012

# ── 2. popup 启动测试 ──
print("\n" + "=" * 60)
print("阶段 2: popup_trainer.py 启动测试")
print("=" * 60)

STATUS_LOG = os.path.join(PROJECT, "popup_status.log")
if os.path.exists(STATUS_LOG):
    os.remove(STATUS_LOG)

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
env["POPUP_LOG_STDOUT"] = "1"

p = subprocess.Popen(
    [PYTHON, os.path.join(PROJECT, "popup_trainer.py")],
    cwd=PROJECT,
    creationflags=0x00000010,  # CREATE_NEW_CONSOLE
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(4.0)

log = ""
if os.path.exists(STATUS_LOG):
    log = open(STATUS_LOG, "r", encoding="utf-8").read()
print("popup_status.log:")
print(log)

# 解析
console_hwnd = message_hwnd = 0
hotkey_ok = False
startup_hidden = False
for line in log.splitlines():
    if "console_hwnd=0x" in line:
        try: console_hwnd = int(line.split("console_hwnd=0x")[1].strip(), 16)
        except: pass
    elif "message_hwnd=0x" in line:
        try: message_hwnd = int(line.split("message_hwnd=0x")[1].strip(), 16)
        except: pass
    elif "hotkey registered Ctrl+Shift+A" in line:
        hotkey_ok = True
    elif "startup hidden" in line:
        startup_hidden = True

# PTC-05/06/07: 启动 + 控制台 hwnd + 启动隐藏
record("PTC-05/06", "popup 启动: console_hwnd 非 0", console_hwnd != 0,
       f"console_hwnd=0x{console_hwnd:X} (来自 [POPUP] console_hwnd= 日志)")
record("PTC-05b", "popup 启动: message_hwnd 非 0", message_hwnd != 0,
       f"message_hwnd=0x{message_hwnd:X} (来自 [POPUP] message_hwnd= 日志)")
record("PTC-07", "popup 启动即隐藏", startup_hidden,
       "日志含 [POPUP] startup hidden")
record("PTC-01b", "popup 热键注册成功", hotkey_ok,
       "日志含 'hotkey registered Ctrl+Shift+A'")

# 跨进程 IsWindowVisible 验证
if console_hwnd:
    vis = bool(win32gui.IsWindowVisible(console_hwnd))
    record("PTC-07b", "跨进程 IsWindowVisible(console) == False", not vis,
           f"IsWindowVisible(0x{console_hwnd:X}) = {vis}（启动后控制台应隐藏）")

# 杀
subprocess.run(["taskkill", "/F", "/PID", str(p.pid), "/T"], capture_output=True)
time.sleep(0.5)

# ── 3. 终端版回归（main.py 无破坏）──
print("\n" + "=" * 60)
print("阶段 3: 终端版 main.py 回归测试（无破坏）")
print("=" * 60)

sys.path.insert(0, PROJECT)
try:
    from test_tc01 import test_tc01
    from test_tc02 import test_tc02
    from test_tc03 import test_tc03
    from test_tc161718 import test_tc16, test_tc17, test_tc18
    from test_tc29 import test_tc29

    for tc_id, tc_name, tc_func in [
        ("TC-01", "主菜单启动", test_tc01),
        ("TC-02", "主菜单选模式", test_tc02),
        ("TC-03", "Q 退出", test_tc03),
        ("TC-16", "拼写正确", test_tc16),
        ("TC-17", "拼写错误", test_tc17),
        ("TC-18", "两次正确通过", test_tc18),
        ("TC-29", "语法点列表", test_tc29),
    ]:
        try:
            assertions, out = tc_func()
            failed = [a for a in assertions if a[2].startswith("FAIL")]
            ok = not failed
            failed_str = f", {len(failed)} FAIL" if failed else ""
            record(f"REG-{tc_id}", f"终端版 {tc_name}", ok,
                   f"{len(assertions)} 断言{failed_str}")
        except Exception as e:
            record(f"REG-{tc_id}", f"终端版 {tc_name}", False, f"异常: {e}")
except Exception as e:
    record("REG-00", "import 测试模块", False, f"异常: {e}")
    traceback.print_exc()

# ── 汇总 ──
print("\n" + "=" * 60)
print("最终汇总")
print("=" * 60)
print(f"{'ID':10s} {'名称':40s} 状态")
print("-" * 70)
passed = 0
failed = 0
for tc_id, name, status, _ in results:
    print(f"{tc_id:10s} {name:40s} {status}")
    if status == "PASS": passed += 1
    else: failed += 1
print(f"\n通过 {passed} / 失败 {failed} / 总 {len(results)}")
sys.exit(0 if failed == 0 else 1)
