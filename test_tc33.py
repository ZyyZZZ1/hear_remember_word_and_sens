"""
TC-33：录音文件不残留 —— 验证退出后无新增音频文件
依据：测试用例 TC-33 预期结果，需求规格 §5.2
"""

from conftest import ProgramRunner, scan_audio_files
import os
import time

PROGRAM_DIR = os.path.dirname(os.path.abspath(__file__))


def test_tc33():
    """TC-33: 退出程序后录音临时文件是否被清理"""
    results = []
    runner = ProgramRunner()

    # 步骤 1：记录 baseline
    baseline = set(scan_audio_files(PROGRAM_DIR))
    results.append((f"baseline 音频文件数：{len(baseline)}", "TC-33 准备步骤", "PASS"))

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 进入模式 1（产生录音）
        runner.send("1")
        runner.wait_for_text("[模式1]", timeout=5)
        time.sleep(1)

        # 按 Enter 结束录音（即使没有麦克风，程序也会处理）
        runner.send("")
        time.sleep(0.5)
        runner.send("Y")  # 自判为对
        time.sleep(0.5)

        # 退出
        runner.send("Q")
        time.sleep(0.5)

    finally:
        runner.stop()
        time.sleep(1)  # 等待清理完成

    # 步骤 2：扫描新增音频文件
    after = set(scan_audio_files(PROGRAM_DIR))
    new_files = after - baseline

    if len(new_files) == 0:
        results.append(("退出后无新增音频文件", "TC-33 预期结果：没有残留音频文件", "PASS"))
    else:
        results.append(("退出后无新增音频文件", "TC-33 预期结果：没有残留音频文件",
                        f"FAIL 发现新增文件：{new_files}"))

    return results, f"baseline={len(baseline)}, after={len(after)}, new={len(new_files)}"
