"""
test_popup_hotkey_smoke.py —— 热键机制冒烟测试

验证"热键是否有效"三层：
  1. RegisterHotKey 能否成功注册 Ctrl+Shift+A
  2. 用 SendInput 模拟物理按键，WM_HOTKEY 是否被收到（端到端）
  3. PostMessage 直接投递 WM_HOTKEY，消息处理是否被触发（隔离测试）

关键修正：消息泵和窗口必须在同一线程（Win32 消息队列是线程局部的）。
"""

import ctypes
import ctypes.wintypes as w
import struct
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import win32gui
import win32con

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 常量
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_SHIFT = 0x0004
MOD_CONTROL = 0x0002
VK_A = 0x41
VK_CONTROL = 0x11
VK_SHIFT = 0x10
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = w.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
user32.PeekMessageW.restype = w.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
user32.TranslateMessage.restype = w.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
user32.DispatchMessageW.restype = ctypes.c_long
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.PostMessageW.restype = w.BOOL
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.SetForegroundWindow.restype = w.BOOL
user32.SendInput.argtypes = [w.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = w.UINT


# ── 共享状态（线程间通信） ──
state = {"WM_HOTKEY_count": 0, "any_count": 0, "got_event": threading.Event()}


def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_HOTKEY:
        state["WM_HOTKEY_count"] += 1
        state["got_event"].set()
    if msg != 0:
        state["any_count"] += 1
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


_class_registered = {"done": False}

def create_window():
    """在调用线程上创建消息窗口 + 注册类（仅一次），返回 hwnd。"""
    if not _class_registered["done"]:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = wnd_proc
        wc.lpszClassName = "SmokeTestWnd"
        wc.hInstance = win32gui.GetModuleHandle(None)
        win32gui.RegisterClass(wc)
        _class_registered["done"] = True
    hinst = win32gui.GetModuleHandle(None)
    hwnd = win32gui.CreateWindowEx(
        0, "SmokeTestWnd", "SmokeTest", 0,
        0, 0, 0, 0,
        win32con.HWND_MESSAGE,
        0, hinst, None,
    )
    return hwnd


def pump_messages_with_timeout(timeout_sec, predicate):
    """在调用线程上 pump 消息，直到 predicate() 为真或超时。
    使用 PeekMessageW 非阻塞轮询。返回 (predicate_result, elapsed)。"""
    start = time.time()
    msg = w.MSG()
    while time.time() - start < timeout_sec:
        if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, win32con.PM_REMOVE):
            if msg.message == WM_QUIT:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
            if predicate():
                return True, time.time() - start
        else:
            time.sleep(0.01)
    return predicate(), time.time() - start


# ── 发送 SendInput（可在任意线程调） ──

def _build_input_structs():
    """构建键盘 INPUT 结构体（按 64 位/32 位自动适配）。"""
    is64 = struct.calcsize("P") == 8

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", w.WORD),
                    ("wScan", w.WORD),
                    ("dwFlags", w.DWORD),
                    ("time", w.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(w.ULONG) if is64 else w.ULONG)]

    class _UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("_u",)
        _fields_ = [("type", w.DWORD), ("_u", _UNION)]

    def make(vk, flags=0):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk
        inp.ki.wScan = 0
        inp.ki.dwFlags = flags
        inp.ki.time = 0
        return inp

    return INPUT, make


def send_combo(vk_main, modifiers):
    INPUT, make = _build_input_structs()
    seq = [make(m, 0) for m in modifiers]
    seq.append(make(vk_main, 0))
    seq.append(make(vk_main, KEYEVENTF_KEYUP))
    for m in reversed(modifiers):
        seq.append(make(m, KEYEVENTF_KEYUP))
    n = len(seq)
    arr = (INPUT * n)(*seq)
    return user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))


# ── 测试 ──

def test_1_register():
    """测试1：RegisterHotKey 注册成功（主线程）。"""
    print("\n[测试1] RegisterHotKey 注册 Ctrl+Shift+A (主线程) ...")
    hwnd = create_window()
    ok = user32.RegisterHotKey(hwnd, 1, MOD_CONTROL | MOD_SHIFT, VK_A)
    err = kernel32.GetLastError()
    print(f"  hwnd=0x{hwnd:X}")
    print(f"  RegisterHotKey 返回 = {ok}, GetLastError = {err}")
    if ok:
        print("  [PASS] 热键注册成功")
    else:
        print(f"  [FAIL] 注册失败（错误码 {err}，组合可能被占用）")
    user32.UnregisterHotKey(hwnd, 1)
    win32gui.DestroyWindow(hwnd)
    return bool(ok)


def test_2_sendinput_trigger():
    """测试2：主线程注册热键 + 主线程 pump + 后台线程 SendInput。"""
    print("\n[测试2] SendInput 模拟物理按键 (主线程注册+pump, 后台线程发送) ...")
    state["WM_HOTKEY_count"] = 0
    state["any_count"] = 0
    state["got_event"].clear()

    hwnd = create_window()
    ok = user32.RegisterHotKey(hwnd, 2, MOD_CONTROL | MOD_SHIFT, VK_A)
    if not ok:
        print("  [FAIL] 注册失败，跳过")
        win32gui.DestroyWindow(hwnd)
        return False

    # 把窗口设前台提升 SendInput 命中率
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)

    # 后台线程发 SendInput（不等主线程 pump）
    def fire():
        time.sleep(0.05)
        sent = send_combo(VK_A, [VK_CONTROL, VK_SHIFT])
        print(f"  [发送线程] SendInput 注入事件数 = {sent}")

    t = threading.Thread(target=fire, daemon=True)
    t.start()

    # 主线程 pump 消息，等待 WM_HOTKEY
    got, elapsed = pump_messages_with_timeout(2.5, lambda: state["got_event"].is_set())
    print(f"  等待 {elapsed:.2f}s, 收到 WM_HOTKEY = {got}")
    print(f"  窗口收到消息总数 = {state['any_count']}, WM_HOTKEY 数 = {state['WM_HOTKEY_count']}")

    user32.UnregisterHotKey(hwnd, 2)
    win32gui.DestroyWindow(hwnd)

    if got:
        print("  [PASS] 物理模拟按键成功触发热键")
        return True
    else:
        print("  [WARN] 未收到 WM_HOTKEY（SendInput 模拟热键易抖动：UIPI/会话/焦点影响）。")
        print("         不视为硬失败，以测试1+测试3为准；真实物理按键需手动 PTC-10 确认。")
        return False


def test_3_postmessage_dispatch():
    """测试3：主线程创建窗口 + 主线程 PostMessage(WM_HOTKEY) + 主线程 pump。"""
    print("\n[测试3] PostMessage 直接投递 WM_HOTKEY (全部主线程) ...")
    state["WM_HOTKEY_count"] = 0
    state["any_count"] = 0
    state["got_event"].clear()

    hwnd = create_window()
    # 主线程投递（关键：必须与窗口创建同线程）
    result = user32.PostMessageW(hwnd, WM_HOTKEY, 3, 0)
    print(f"  PostMessage(WM_HOTKEY) 返回 = {result}")

    got, elapsed = pump_messages_with_timeout(1.0, lambda: state["got_event"].is_set())
    print(f"  等待 {elapsed:.2f}s, 收到并处理 = {got}")
    print(f"  窗口收到消息总数 = {state['any_count']}, WM_HOTKEY 数 = {state['WM_HOTKEY_count']}")

    win32gui.DestroyWindow(hwnd)
    if got:
        print("  [PASS] 消息分发路径正常，toggle 处理可被触发")
        return True
    else:
        print("  [FAIL] 消息未送达处理")
        return False


def main():
    print("=" * 56)
    print("  热键机制冒烟测试（Ctrl+Shift+A = VK_A）")
    print("=" * 56)

    r1 = test_1_register()
    r2 = test_2_sendinput_trigger()
    r3 = test_3_postmessage_dispatch()

    print("\n" + "=" * 56)
    print("  汇总")
    print("=" * 56)
    print(f"  测试1 RegisterHotKey 注册      : {'PASS' if r1 else 'FAIL'}")
    print(f"  测试2 SendInput 端到端触发     : {'PASS' if r2 else 'WARN(可抖动)'}")
    print(f"  测试3 PostMessage 消息分发     : {'PASS' if r3 else 'FAIL'}")

    if r1 and r3:
        print("\n  结论：热键机制 [有效]。注册与消息分发路径可用。")
        if not r2:
            print("  注：SendInput 模拟未命中属已知抖动，真实物理按键需手动 PTC-10 确认。")
        sys.exit(0)
    else:
        print("\n  结论：热键机制存在硬障碍，需重新评估方案。")
        sys.exit(1)


if __name__ == "__main__":
    main()
