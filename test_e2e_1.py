"""
test_e2e_1.py —— 单测试 E2E-1: 启动流程
读 popup_status.log 取 [POPUP] 状态行，跨进程查 console_hwnd 可见性。
"""
import os, sys, time, subprocess
import win32gui

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PYTHON = r"C:\Users\12099\miniconda3\python.exe"
PROJECT = r"D:\程序\脚本\01-08"
POPUP_SCRIPT = os.path.join(PROJECT, "popup_trainer.py")
STATUS_LOG = os.path.join(PROJECT, "popup_status.log")

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

print("启动 popup 子进程 (CREATE_NEW_CONSOLE, 不重定向 stdout) ...")
p = subprocess.Popen(
    [PYTHON, POPUP_SCRIPT],
    cwd=PROJECT,
    creationflags=0x00000010,  # CREATE_NEW_CONSOLE
    env=env,
    # 不重定向 stdout/stderr，让它走新建的控制台
)
print(f"PID={p.pid}")
time.sleep(3.0)  # 等热键注册 + 启动隐藏

# 读 popup_status.log
log_content = ""
if os.path.exists(STATUS_LOG):
    log_content = open(STATUS_LOG, "r", encoding="utf-8").read()
print("=== popup_status.log ===")
print(log_content)
print("=" * 40)

# 解析 hwnds
hwnds = {"console": 0, "message": 0}
for line in log_content.splitlines():
    if "console_hwnd=0x" in line:
        try:
            hwnds["console"] = int(line.split("console_hwnd=0x")[1].strip(), 16)
        except Exception:
            pass
    elif "message_hwnd=0x" in line:
        try:
            hwnds["message"] = int(line.split("message_hwnd=0x")[1].strip(), 16)
        except Exception:
            pass

print(f"console_hwnd = 0x{hwnds['console']:X}")
print(f"message_hwnd = 0x{hwnds['message']:X}")

# 用 popup 自己的 console_hwnd 跨进程查 IsWindowVisible
if hwnds["console"]:
    vis = bool(win32gui.IsWindowVisible(hwnds["console"]))
    print(f"IsWindowVisible(popup_console_hwnd) = {vis}")

# 杀
print("kill 子进程...")
subprocess.run(["taskkill", "/F", "/PID", str(p.pid), "/T"], capture_output=True)
time.sleep(0.5)
print("done.")
