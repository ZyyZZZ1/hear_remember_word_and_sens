"""
test_e2e_2.py —— 单测试 E2E-2: toggle 显隐切换
用 POPUP_STDIN_HOOK=1 + stdin 发 TOGGLE/SHOW/HIDE 命令直接测 toggle 函数
（避免 PostMessage 跨线程/消息泵的复杂性）
"""
import os, sys, time, subprocess
import win32gui

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PYTHON = r"C:\Users\12099\miniconda3\python.exe"
PROJECT = r"D:\程序\脚本\01-08"
STATUS_LOG = os.path.join(PROJECT, "popup_status.log")

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
env["POPUP_TEST"] = "1"
env["POPUP_STDIN_HOOK"] = "1"

print("启动 popup (POPUP_TEST=1, POPUP_STDIN_HOOK=1) ...")
# 不传 CREATE_NEW_CONSOLE，让 popup 继承测试进程的控制台（stdin=PIPE 才能生效）
p = subprocess.Popen(
    [PYTHON, os.path.join(PROJECT, "popup_trainer.py")],
    cwd=PROJECT,
    env=env,
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(f"PID={p.pid}")
time.sleep(6.0)  # 等启动（含 TTS 加载）

log0 = open(STATUS_LOG, "r", encoding="utf-8").read()
print("=== 启动后 popup_status.log ===")
print(log0)

console_hwnd = 0
for line in log0.splitlines():
    if "console_hwnd=0x" in line:
        try:
            console_hwnd = int(line.split("console_hwnd=0x")[1].strip(), 16)
        except Exception:
            pass
print(f"console_hwnd = 0x{console_hwnd:X}")
print(f"启动 IsWindowVisible = {bool(win32gui.IsWindowVisible(console_hwnd))}")

# 第一次 toggle (visible -> hide)
print("\n[1] 发 TOGGLE (visible -> hide) ...")
p.stdin.write(b"TOGGLE\n")
p.stdin.flush()
time.sleep(1.0)
log1 = open(STATUS_LOG, "r", encoding="utf-8").read()
new = log1[len(log0):]
print(f"增量:\n{new}")
vis1 = bool(win32gui.IsWindowVisible(console_hwnd))
print(f"IsWindowVisible = {vis1}")

# 第二次 toggle (hide -> show)
print("\n[2] 发 TOGGLE (hide -> show) ...")
p.stdin.write(b"TOGGLE\n")
p.stdin.flush()
time.sleep(1.0)
log2 = open(STATUS_LOG, "r", encoding="utf-8").read()
new = log2[len(log1):]
print(f"增量:\n{new}")
vis2 = bool(win32gui.IsWindowVisible(console_hwnd))
print(f"IsWindowVisible = {vis2}")

# 第三次 toggle (show -> hide)
print("\n[3] 发 TOGGLE (show -> hide) ...")
p.stdin.write(b"TOGGLE\n")
p.stdin.flush()
time.sleep(1.0)
log3 = open(STATUS_LOG, "r", encoding="utf-8").read()
new = log3[len(log2):]
print(f"增量:\n{new}")
vis3 = bool(win32gui.IsWindowVisible(console_hwnd))
print(f"IsWindowVisible = {vis3}")

# 第四次发 SHOW 直接验证 SHOW 命令
print("\n[4] 发 SHOW (force show) ...")
p.stdin.write(b"SHOW\n")
p.stdin.flush()
time.sleep(1.0)
log4 = open(STATUS_LOG, "r", encoding="utf-8").read()
new = log4[len(log3):]
print(f"增量:\n{new}")
vis4 = bool(win32gui.IsWindowVisible(console_hwnd))
print(f"IsWindowVisible = {vis4}")

# 杀
subprocess.run(["taskkill", "/F", "/PID", str(p.pid), "/T"], capture_output=True)
time.sleep(0.5)

toggle_count = log4.count("toggle ")
print(f"\ntoggle 日志次数 = {toggle_count}")

# 判定
passed = (
    vis1 == False and  # 1: vis → False
    vis2 == True and   # 2: vis → True
    vis3 == False and  # 3: vis → False
    vis4 == True and   # 4: SHOW → True
    toggle_count >= 3
)
print(f"\n=== 结论 ===")
print(f"  [1] vis=True → TOGGLE → False : {vis1} {'OK' if vis1==False else 'FAIL'}")
print(f"  [2] vis=False → TOGGLE → True : {vis2} {'OK' if vis2==True else 'FAIL'}")
print(f"  [3] vis=True → TOGGLE → False : {vis3} {'OK' if vis3==False else 'FAIL'}")
print(f"  [4] vis=False → SHOW → True   : {vis4} {'OK' if vis4==True else 'FAIL'}")
print(f"  toggle 日志 >= 3 : {toggle_count} {'OK' if toggle_count>=3 else 'FAIL'}")
print(f"  整体: {'[PASS]' if passed else '[FAIL]'}")
