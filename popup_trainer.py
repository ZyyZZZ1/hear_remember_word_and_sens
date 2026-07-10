"""
popup_trainer.py —— 西班牙语陪练 · 全局热键弹窗版

设计依据：热键弹窗设计.md
- 单文件，python 启动
- 启动时设控制台标题/尺寸/居中 → 注册热键 → 立即隐藏
- 后台线程：RegisterHotKey Ctrl+Shift+A（无管理员）
- 主线程：import main; main.main()  行为与终端版完全一致
- main.py 零改动

测试钩子：
- POPUP_TEST=1   启动后不自动隐藏，便于自动化观察显隐
- [POPUP]  日志写入独立文件 popup_status.log（与 main.print 解耦，防爆日志）
"""

import os
import sys
import time
import threading
import ctypes
import ctypes.wintypes as w
import win32gui
import win32con

# ── 测试钩子 ──
TEST_MODE = os.environ.get("POPUP_TEST") == "1"
LOG_TO_STDOUT = os.environ.get("POPUP_LOG_STDOUT") == "1"

# ── [POPUP] 状态日志 → 独立文件（与 main 的 print 解耦） ──
POPUP_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "popup_status.log")
_LOG_LOCK = threading.Lock()
_LOG_BYTES = [0]
_LOG_MAX = 64 * 1024  # 64KB 上限，防爆


def log(msg):
    """状态日志：写独立文件，前缀 [POPUP]，便于测试脚本解析。
    测试模式下（POPUP_LOG_STDOUT=1）同时输出到 stdout，方便 subprocess 捕获。"""
    line = f"[POPUP] {msg}\n"
    if LOG_TO_STDOUT:
        try:
            print(line, end="", flush=True)
        except Exception:
            pass
    with _LOG_LOCK:
        if _LOG_BYTES[0] + len(line.encode("utf-8")) > _LOG_MAX:
            return
        try:
            with open(POPUP_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                try:
                    import os
                    os.fsync(f.fileno())
                except Exception:
                    pass
            _LOG_BYTES[0] += len(line.encode("utf-8"))
        except Exception:
            pass


# 启动时清空旧日志
try:
    with open(POPUP_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"[POPUP] popup_trainer.py 启动 (test_mode={TEST_MODE})\n")
    _LOG_BYTES[0] = len(f"[POPUP] popup_trainer.py 启动 (test_mode={TEST_MODE})\n".encode("utf-8"))
except Exception:
    pass


# ── Win32 原型 ──
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = w.BOOL
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.SetForegroundWindow.restype = w.BOOL
user32.ShowWindowAsync.argtypes = [w.HWND, ctypes.c_int]
user32.ShowWindowAsync.restype = w.BOOL
kernel32.SetConsoleTitleW.argtypes = [w.LPCWSTR]
kernel32.SetConsoleTitleW.restype = w.BOOL
kernel32.GetConsoleWindow.argtypes = []
kernel32.GetConsoleWindow.restype = w.HWND
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int


# ── 常量 ──
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_A = 0x41       # 字母 A，键盘布局无关
HOTKEY_PRIMARY_ID = 1


# ── 状态 ──
_state = {"hidden": False, "toggle_count": 0}
_message_hwnd = None


# ── 控制台窗口管理 ──

def get_console_hwnd():
    """获取本进程控制台窗口句柄。0 = 无控制台（管道子进程等场景）。"""
    return kernel32.GetConsoleWindow()


def set_console_visible(hwnd, visible):
    """设置控制台显隐（显示时置顶+聚焦），并同步进程内状态。

    用 ShowWindowAsync 替代 ShowWindow，避免被主线程阻塞，降低弹出/收起延迟。
    HWND_TOPMOST 在 setup_console() 中一次性设置，此处不再重复调用。

    关键：同步更新 _state["hidden"]。toggle() 依赖 _state 而非 IsWindowVisible()，
    因为 ShowWindowAsync 是异步的，调用后 IsWindowVisible 可能仍返回旧值（WS_VISIBLE
    标志位未即时更新），导致 toggle 误判方向——首次按键本应 show 却执行 hide，
    需按两次热键才能弹出窗口（见 popup_status.log 启动后首条 toggle 为 hide 的现象）。
    """
    if visible:
        user32.ShowWindowAsync(hwnd, win32con.SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    else:
        user32.ShowWindowAsync(hwnd, win32con.SW_HIDE)
    _state["hidden"] = not visible


def toggle(hwnd):
    """切换控制台显隐，返回新的可见状态。

    状态源为进程内 _state["hidden"]，不查询 IsWindowVisible()——后者对异步
    ShowWindow 的判断会滞后，曾导致首次按键方向反转（hide 而非 show）。
    """
    new_state = _state.get("hidden", False)  # 当前隐藏→显示(True)；当前显示→隐藏(False)
    set_console_visible(hwnd, new_state)
    _state["toggle_count"] += 1
    log(f"toggle {'show' if new_state else 'hide'} (count={_state['toggle_count']})")
    return new_state


# ── 热键消息窗口 ──

def _hotkey_wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_HOTKEY:
        log(f"WM_HOTKEY received wparam={wparam} lparam_hi={lparam >> 16} lparam_lo={lparam & 0xFFFF}")
        hwnd_console = get_console_hwnd()
        if hwnd_console:
            toggle(hwnd_console)
        return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def register_hotkey(hwnd, mod, vk, hotkey_id):
    """注册全局热键，返回 True 成功。"""
    return bool(user32.RegisterHotKey(hwnd, hotkey_id, mod, vk))


# ── 热键线程 ──

def _hotkey_thread():
    global _message_hwnd
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = _hotkey_wnd_proc
    wc.lpszClassName = "PopupTrainerHotkey"
    wc.hInstance = win32gui.GetModuleHandle(None)
    win32gui.RegisterClass(wc)

    _message_hwnd = win32gui.CreateWindowEx(
        0, "PopupTrainerHotkey", "PopupTrainerHotkey", 0,
        0, 0, 0, 0,
        win32con.HWND_MESSAGE,
        0, wc.hInstance, None,
    )
    log(f"message_hwnd=0x{_message_hwnd:X}")

    primary_ok = register_hotkey(_message_hwnd, MOD_CONTROL | MOD_SHIFT, VK_A, HOTKEY_PRIMARY_ID)
    if primary_ok:
        log("hotkey registered Ctrl+Shift+A")
    else:
        log("hotkey failed")

    win32gui.PumpMessages()


# ── 控制台外观 ──

def setup_console():
    """设置控制台标题、居中缩小，返回 hwnd。"""
    kernel32.SetConsoleTitleW("SpanishDrill")
    time.sleep(0.05)
    hwnd = get_console_hwnd()
    if hwnd:
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        # 控制台尺寸：约 38 列 x 9 行（受字体限制的紧凑极限）
        # 字符宽度按 ~8px，高度按 ~16px 估算
        w_px, h_px = 380, 200
        x = max(0, (screen_w - w_px) // 2)
        y = max(0, (screen_h - h_px) // 2)
        win32gui.SetWindowPos(hwnd, 0, x, y, w_px, h_px, 0)
        # 一次性设为置顶，后续 show/hide 不再重复调用 SetWindowPos
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
    log(f"console_hwnd=0x{hwnd:X}")
    return hwnd


# ── 入口 ──

def run():
    # 0. 测试模式且无控制台时，强制 AllocConsole 创建一个独立控制台
    hwnd = get_console_hwnd()
    if hwnd == 0 and os.environ.get("POPUP_STDIN_HOOK") == "1":
        try:
            kernel32.AllocConsole()
            kernel32.SetConsoleTitleW("SpanishDrill")
            time.sleep(0.05)
            hwnd = get_console_hwnd()
            log(f"AllocConsole new hwnd=0x{hwnd:X}")
        except Exception as e:
            log(f"AllocConsole failed: {e}")

    # 1. 设置控制台外观（总是调用，记录 console_hwnd）
    new_hwnd = setup_console()
    if new_hwnd:
        hwnd = new_hwnd
    if hwnd == 0:
        log("WARN: no console hwnd (running in pipe-only subprocess?)")

    # 2. 启动热键监听线程
    t = threading.Thread(target=_hotkey_thread, daemon=True)
    t.start()
    time.sleep(0.3)  # 等待热键注册完成

    # 3. 启动即隐藏（除非测试模式）
    if hwnd and not TEST_MODE:
        set_console_visible(hwnd, False)
        log("startup hidden")
    else:
        log(f"startup visible (test_mode={TEST_MODE})")

    # 4. 跑 main.main()（与终端版完全相同的入口）
    import main as m
    try:
        m.main()
    except KeyboardInterrupt:
        pass
    finally:
        if _message_hwnd:
            try:
                user32.UnregisterHotKey(_message_hwnd, HOTKEY_PRIMARY_ID)
            except Exception:
                pass
            try:
                win32gui.DestroyWindow(_message_hwnd)
            except Exception:
                pass


if __name__ == "__main__":
    run()
