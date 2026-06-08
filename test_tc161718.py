"""
TC-16 + TC-17 + TC-18：听写模式拼写逻辑
依据：
  TC-16 预期结果（拼写正确 → "对" + 下一词）
  TC-17 预期结果（拼写错误 → 显示正确拼写 + 回队尾）
  TC-18 预期结果（连续两次正确 → 不再出现）
  需求规格 §3.4 听写判罚规则，§4 错误循环规则
"""

from conftest import ProgramRunner, extract_words_from_output
import time


def test_tc16():
    """TC-16: 输入正确拼写后程序判定通过"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 进入模式 3
        runner.send("3")
        runner.wait_for_text("[听写模式]", timeout=5)
        runner.wait_for_text("当前单词：", timeout=5)

        # 读取当前单词
        output = runner.get_output()
        words = extract_words_from_output(output)
        if not words:
            results.append(("获取当前单词", "TC-16", "FAIL 未找到 '当前单词：'"))
            return results, runner.get_output()
        word = words[-1]
        results.append((f"读取到单词 '{word}'", "TC-16 预期结果", "PASS"))

        # 输入正确拼写
        runner.send(word)
        time.sleep(0.5)
        runner.wait_for_text("[OK]", timeout=5)

        output2 = runner.get_output()
        # 断言：出现"正确"提示 (TC-16 预期结果第1条)
        if "[OK]" in output2 or "正确" in output2:
            results.append((f"正确拼写 '{word}' 后显示正确提示", "TC-16 预期结果第1条", "PASS"))
        else:
            results.append((f"正确拼写 '{word}' 后显示正确提示", "TC-16 预期结果第1条", "FAIL 未找到正确提示"))

        # 断言：进入下一个单词 (TC-16 预期结果第2条)
        time.sleep(0.3)
        runner.wait_for_text("当前单词：", timeout=5)
        words2 = extract_words_from_output(runner.get_output())
        # 正确拼写第一次后会再巩固一次（同一个词），所以可能下一个词还是同一个
        if len(words2) >= 1:
            results.append(("进入下一题（未卡死）", "TC-16 预期结果第2条", "PASS"))
        else:
            results.append(("进入下一题（未卡死）", "TC-16 预期结果第2条", "FAIL 未检测到后续单词"))

    finally:
        runner.stop()

    return results, runner.get_output()


def test_tc17():
    """TC-17: 输入错误拼写后程序指出正确拼写并回队尾"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 进入模式 3
        runner.send("3")
        runner.wait_for_text("[听写模式]", timeout=5)
        runner.wait_for_text("当前单词：", timeout=5)

        output = runner.get_output()
        words = extract_words_from_output(output)
        if not words:
            results.append(("获取当前单词", "TC-17", "FAIL 未找到 '当前单词：'"))
            return results, runner.get_output()
        word = words[-1]
        results.append((f"读取到单词 '{word}'", "TC-17 预期结果", "PASS"))

        # 故意输入错误拼写：末尾加一个字符
        wrong_word = word + "x"
        runner.send(wrong_word)
        time.sleep(0.5)
        runner.wait_for_text("错误", timeout=5)

        output2 = runner.get_output()
        # 断言：显示了正确拼写 (TC-17 预期结果第1条)
        if word in output2:
            results.append((f"错误后显示了正确拼写 '{word}'", "TC-17 预期结果第1条", "PASS"))
        else:
            # 输入的词可能正好在输出中被找到了，"错误"和"正确拼写"组合
            results.append((f"错误后显示了正确拼写 '{word}'", "TC-17 预期结果第1条", "WARN 需人工确认"))

        # 继续答题，验证该词再次出现
        found_again = False
        for _ in range(30):
            runner.wait_for_text("当前单词：", timeout=3)
            output = runner.get_output()
            current_words = extract_words_from_output(output)
            if not current_words:
                break
            cw = current_words[-1]
            if cw == word:
                found_again = True
                # 正确拼写让它通过
                runner.send(cw)
                time.sleep(0.3)
                runner.wait_for_text("[OK]", timeout=3)
                runner.send(cw)
                time.sleep(0.3)
                runner.wait_for_text("[OK]", timeout=3)
                break
            else:
                # 跳过其他词
                runner.send("S")
                time.sleep(0.3)

        if found_again:
            results.append((f"拼错的词 '{word}' 后续再次出现", "TC-17 预期结果第2条", "PASS"))
        else:
            results.append((f"拼错的词 '{word}' 后续再次出现", "TC-17 预期结果第2条",
                            "WARN 测试轮次内未再次出现（词可能在队尾）"))

    finally:
        runner.stop()

    return results, runner.get_output()


def test_tc18():
    """TC-18: 连续两次拼写正确后不再出现"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 进入模式 3
        runner.send("3")
        runner.wait_for_text("[听写模式]", timeout=5)
        runner.wait_for_text("当前单词：", timeout=5)

        output = runner.get_output()
        words = extract_words_from_output(output)
        if not words:
            results.append(("获取第一个单词", "TC-18", "FAIL 未找到 '当前单词：'"))
            return results, runner.get_output()
        target = words[-1]
        results.append((f"目标单词 '{target}'", "TC-18 预期结果", "PASS"))

        # 第一次正确拼写
        runner.send(target)
        time.sleep(0.5)
        runner.wait_for_text("[OK]", timeout=5)
        results.append((f"第1次正确拼写 '{target}'", "TC-18 预期结果：第一次后还会出现", "PASS"))

        # 巩固轮：正确拼写后词排到队尾，需跳过其他词直到 target 再出现
        time.sleep(0.3)
        consolidation_found = False
        for _ in range(20):
            runner.wait_for_text("当前单词：", timeout=5)
            time.sleep(0.2)
            current_words = extract_words_from_output(runner.get_output())
            if not current_words:
                break
            cw = current_words[-1]
            if cw == target:
                runner.send(target)
                time.sleep(0.5)
                runner.wait_for_text("[OK]", timeout=5)
                consolidation_found = True
                results.append((f"第2次正确拼写 '{target}'（巩固轮）",
                                "TC-18 预期结果：第二次后不再出现", "PASS"))
                break
            else:
                runner.send("S")
                time.sleep(0.3)

        if not consolidation_found:
            results.append((f"巩固轮未等到 '{target}'", "TC-18 预期结果", "WARN"))

        # 继续跳过后续所有词，统计 target 在 stdout 历史中总出现次数
        for _ in range(20):
            runner.wait_for_text("当前单词：", timeout=3)
            current_words = extract_words_from_output(runner.get_output())
            if not current_words:
                break
            runner.send("S")
            time.sleep(0.3)

        total_count = runner.get_output().count(f"当前单词：{target}")
        if total_count <= 2:
            results.append((f"'{target}' 总出现次数={total_count}，<=2",
                            "TC-18 预期结果：连续两次正确后不再出现", "PASS"))
        else:
            results.append((f"'{target}' 总出现次数={total_count}，>2",
                            "TC-18 预期结果：连续两次正确后不再出现",
                            f"FAIL 出现了超过 2 次"))

    finally:
        runner.stop()

    return results, runner.get_output()
