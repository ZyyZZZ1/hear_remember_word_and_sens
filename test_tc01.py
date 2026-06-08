"""
TC-01：启动程序 —— 验证启动后显示主菜单
依据：测试用例 TC-01 预期结果，需求规格 §3.1
"""

from conftest import ProgramRunner, assert_contains, EXPECTED_MENU_ITEMS


def test_tc01():
    """TC-01: 程序能否正常启动并显示主菜单"""
    results = []
    runner = ProgramRunner()

    try:
        # 步骤 1：启动程序
        runner.start()
        runner.select_textbook_and_wait_menu()

        output = runner.get_output()

        # 断言 1：stdout 包含程序标题 (TC-01 预期结果第1条)
        try:
            assert_contains(output, "西班牙语陪练", "TC-01:1 标题")
            results.append(("stdout 包含程序标题", "TC-01 预期结果第1条", "PASS"))
        except AssertionError as e:
            results.append(("stdout 包含程序标题", "TC-01 预期结果第1条", f"FAIL {e}"))

        # 断言 2：stdout 包含模式选项列表 (TC-01 预期结果第2条)
        for item in EXPECTED_MENU_ITEMS:
            try:
                assert_contains(output, item, f"TC-01:2 菜单项 {item}")
                results.append((f"stdout 包含菜单项 '{item}'", "TC-01 预期结果第2条", "PASS"))
            except AssertionError as e:
                results.append((f"stdout 包含菜单项 '{item}'", "TC-01 预期结果第2条", f"FAIL {e}"))

        # 断言 3：程序仍在运行，等待用户输入 (TC-01 预期结果第3条)
        if runner.is_running:
            results.append(("进程仍在运行，等待输入", "TC-01 预期结果第3条", "PASS"))
        else:
            results.append(("进程仍在运行，等待输入", "TC-01 预期结果第3条", "FAIL 进程已退出"))

    finally:
        runner.stop()

    return results, runner.get_output()
