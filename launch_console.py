"""
launch_console.py —— 用 CREATE_NEW_CONSOLE 启动子进程，并把 stdout 重定向到文件
"""
import ctypes
import ctypes.wintypes as w
import sys
import time
import os
import struct

kernel32 = ctypes.windll.kernel32

CREATE_NEW_CONSOLE = 0x00000010
STARTF_USESTDHANDLES = 0x00000100
STARTF_USESHOWWINDOW = 0x00000001

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD),
        ("lpReserved", w.LPWSTR),
        ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR),
        ("dwX", w.DWORD),
        ("dwY", w.DWORD),
        ("dwXSize", w.DWORD),
        ("dwYSize", w.DWORD),
        ("dwXCountChars", w.DWORD),
        ("dwYCountChars", w.DWORD),
        ("dwFillAttribute", w.DWORD),
        ("dwFlags", w.DWORD),
        ("wShowWindow", w.WORD),
        ("cbReserved2", w.WORD),
        ("lpReserved2", ctypes.POINTER(w.BYTE)),
        ("hStdInput", w.HANDLE),
        ("hStdOutput", w.HANDLE),
        ("hStdError", w.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", w.HANDLE),
        ("hThread", w.HANDLE),
        ("dwProcessId", w.DWORD),
        ("dwThreadId", w.DWORD),
    ]

def launch_with_console(cmd_args, cwd, log_path, env_extra=None):
    """启动带新控制台的子进程，stdout/stderr 重定向到 log 文件。"""
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.dwFlags = STARTF_USESTDHANDLES

    # 打开日志文件作为 stdout
    log_handle_out = kernel32.CreateFileW(
        log_path, 0x40000000,  # GENERIC_WRITE
        0x00000002,  # FILE_SHARE_WRITE
        None, 4,  # OPEN_ALWAYS
        0x80, 0  # FILE_ATTRIBUTE_NORMAL
    )
    log_handle_err = kernel32.CreateFileW(
        log_path + ".err", 0x40000000, 0x00000002, None, 4, 0x80, 0
    )
    log_handle_in = kernel32.CreateFileW(
        "CONIN$", 0x80000000, 0x00000003, None, 3, 0, 0  # OPEN_EXISTING
    )

    si.hStdInput = log_handle_in
    si.hStdOutput = log_handle_out
    si.hStdError = log_handle_err

    cmdline = " ".join(f'"{a}"' if " " in a else a for a in cmd_args)
    pi = PROCESS_INFORMATION()

    ok = kernel32.CreateProcessW(
        None, cmdline, None, None, False,
        CREATE_NEW_CONSOLE,
        None, cwd,
        ctypes.byref(si), ctypes.byref(pi)
    )
    if not ok:
        err = ctypes.get_last_error()
        raise OSError(f"CreateProcessW failed: {err}")
    kernel32.CloseHandle(pi.hThread)
    return pi


if __name__ == "__main__":
    # 命令行：python launch_console.py <log_path> <cwd> <cmd...>
    log_path = sys.argv[1]
    cwd = sys.argv[2]
    cmd = sys.argv[3:]
    pi = launch_with_console(cmd, cwd, log_path)
    print(f"PID={pi.dwProcessId}")
