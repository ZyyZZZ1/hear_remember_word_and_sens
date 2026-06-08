"""
TC-02：主菜单选模式 —— 验证各按键进入对应模式后能返回主菜单
依据：测试用例 TC-02 预期结果，需求规格 §3.1 按键映射表
"""

from conftest import ProgramRunner, assert_contains

# 每个按键对应的预期模式标识文字
MODE_MARKERS = {
    "1": "[模式1]",
    "2": "[模式2]",
    "3": "[听写模式]",
    "4": "[跟读模式]",
    "5": "[混着来模式]",
    "G": "语法讲解",
}


def test_tc02():
    """TC-02: 主菜单各按键是否进入对应模式"""
    results = []

    for key, marker in MODE_MARKERS.items():
        runner = ProgramRunner()
        try:
            runner.start()
            runner.select_textbook_and_wait_menu()

            # 步骤：按模式键进入
            runner.send_key(key)
            entered = runner.wait_for_text(marker, timeout=5)
            output = runner.get_output()

            if entered:
                results.append((f"按 [{key}] 后进入对应模式", f"TC-02 预期结果：{marker}", "PASS"))
            else:
                results.append((f"按 [{key}] 后进入对应模式", f"TC-02 预期结果：{marker}",
                                f"FAIL stdout 中未找到 '{marker}'"))

            # 步骤：按 Q 返回主菜单
            runner.send_key("Q")
            back = runner.wait_for_text("西班牙语陪练", timeout=5)
            output2 = runner.get_output()

            if back:
                results.append((f"在 [{key}] 模式中按 Q 返回主菜单", "TC-02 预期结果：每次按 Q 都能回到主菜单", "PASS"))
            else:
                results.append((f"在 [{key}] 模式中按 Q 返回主菜单", "TC-02 预期结果：每次按 Q 都能回到主菜单",
                                "FAIL stdout 中未找到主菜单标题"))

        finally:
            runner.stop()

    # 汇总输出用最后一个 runner 的输出（所有模式测试的总体评估）
    return results, "[TC-02 为多模式遍历测试，输出不集中展示]"
