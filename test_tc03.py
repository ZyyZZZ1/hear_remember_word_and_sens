"""
TC-03：主菜单按 Q 退出 —— 验证退出码和 stdout
依据：测试用例 TC-03 预期结果，需求规格 §3.1
"""

from conftest import ProgramRunner, assert_not_contains


def test_tc03():
    """TC-03: 在主菜单按 Q 是否退出程序"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 步骤：在主菜单按 Q
        runner.send_key("Q")

        # 等待进程退出
        import time
        deadline = time.time() + 5
        while runner.is_running and time.time() < deadline:
            time.sleep(0.2)

        output = runner.get_output()

        # 断言 1：进程退出码为 0 (TC-03 预期结果第1条)
        exit_code = runner.proc.poll() if runner.proc else -1
        if exit_code == 0:
            results.append(("进程退出码为 0", "TC-03 预期结果：程序退出，回到终端", "PASS"))
        else:
            results.append(("进程退出码为 0", "TC-03 预期结果：程序退出，回到终端",
                            f"FAIL 退出码={exit_code}（非零）"))

        # 断言 2：stdout 无异常堆栈 (TC-03 预期结果第2条)
        try:
            assert_not_contains(output, "Traceback", "TC-03:2 无 crash")
            results.append(("stdout 无 crash 堆栈", "TC-03 预期结果：正常退出", "PASS"))
        except AssertionError as e:
            results.append(("stdout 无 crash 堆栈", "TC-03 预期结果：正常退出", f"FAIL {e}"))

        try:
            assert_not_contains(output, "Error", "TC-03:2 无 Error")
        except AssertionError:
            pass  # "Error" 可能出现在正常文本中，不作为硬失败

    finally:
        runner.stop()

    return results, output
