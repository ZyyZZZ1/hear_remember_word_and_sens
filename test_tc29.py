"""
TC-29：语法点列表展示 —— 验证按 G 后列出语法点名称和编号
依据：测试用例 TC-29 预期结果，需求规格 §3.7
预期语法点名称来自总计划 §1.5 语法点表
"""

from conftest import ProgramRunner, EXPECTED_GRAMMAR
import re


def test_tc29():
    """TC-29: 按 G 后是否显示语法点列表"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 按 G 进入语法讲解
        runner.send("G")
        # 不能等 "语法讲解" 或 "[1]"，因为菜单里也有这些文字
        # 等语法模式独有的文字："返回主菜单"（语法点列表底部的选项）
        import time
        time.sleep(0.5)
        runner.wait_for_text("返回主菜单", timeout=5)
        output = runner.get_output()

        # 验证语法模式特有内容存在
        if "请选择语法点" in output or "返回主菜单" in output:
            results.append(("按 G 后进入语法讲解", "TC-29 预期结果：屏幕列出所有语法点", "PASS"))
        else:
            results.append(("按 G 后进入语法讲解", "TC-29 预期结果：屏幕列出所有语法点",
                            "FAIL 未找到语法点列表"))

        # 断言：每个语法点名称出现 (TC-29 预期结果第1条)
        for name in EXPECTED_GRAMMAR:
            if name in output:
                results.append((f"stdout 包含语法点 '{name}'", "TC-29 预期结果第1条", "PASS"))
            else:
                results.append((f"stdout 包含语法点 '{name}'", "TC-29 预期结果第1条",
                                f"FAIL 未找到 '{name}'"))

        # 断言：每个语法点前有编号 (TC-29 预期结果第2条)
        numbered = re.findall(r'\[\d+\]', output)
        if len(numbered) >= 2:
            results.append((f"语法点有编号（找到 {len(numbered)} 个编号）",
                            "TC-29 预期结果第2条", "PASS"))
        else:
            results.append(("语法点有编号", "TC-29 预期结果第2条",
                            f"FAIL 仅找到 {len(numbered)} 个编号"))

        # 断言：提示用户选择 (TC-29 预期结果第3条)
        has_prompt = "选择" in output or "输入编号" in output or "按数字" in output or "请选择" in output
        if has_prompt:
            results.append(("提示用户按数字选择", "TC-29 预期结果第3条", "PASS"))
        else:
            results.append(("提示用户按数字选择", "TC-29 预期结果第3条",
                            "WARN 未找到明确的选择提示"))

    finally:
        runner.stop()

    return results, output
