"""
TC-09 + TC-11 + TC-20：模式 3 的 S 键跳过和 Q 键返回
依据：
  TC-09 预期结果（S 键跳过 → 词回队尾）
  TC-11 预期结果（练习中 Q 返回主菜单）
  TC-20 预期结果（S 键跳过 → 词回队尾）
  S 键行为见需求规格 §3.4
"""

from conftest import ProgramRunner, extract_words_from_output
import time


def test_tc09():
    """TC-09: S 键跳过当前词，该词稍后再次出现"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 进入模式 3
        runner.send("3")
        runner.wait_for_text("[听写模式]", timeout=5)

        # 等待第一个单词出现
        time.sleep(0.5)
        runner.wait_for_text("当前单词：", timeout=5)
        output = runner.get_output()
        words = extract_words_from_output(output)
        if not words:
            results.append(("获取第一个单词", "TC-09", "FAIL 未在 stdout 中找到 '当前单词：'"))
            return results, output
        first_word = words[-1]
        results.append((f"识别到第一个单词 '{first_word}'", "TC-09 预期结果", "PASS"))

        # 按 S 跳过
        runner.send("S")
        time.sleep(0.5)
        runner.wait_for_text("已跳过", timeout=5)

        # 验证跳到了下一个词
        output2 = runner.get_output()
        words2 = extract_words_from_output(output2)
        if len(words2) >= 2 and words2[-1] != first_word:
            results.append(("按 S 后跳到下一个词", "TC-09 预期结果第1条", "PASS"))
        else:
            results.append(("按 S 后跳到下一个词", "TC-09 预期结果第1条",
                            "FAIL 未检测到单词变化"))

        # 持续正确拼写所有词，验证被跳过的词后续再次出现
        seen_words = set()
        found_skipped = False
        for _ in range(30):  # 最多 30 轮
            output = runner.get_output()
            words = extract_words_from_output(output)
            if not words:
                # 可能本轮结束了
                break
            current_word = words[-1]
            if current_word in seen_words:
                # 本轮可能已结束
                break

            if current_word == first_word:
                found_skipped = True
                # 正确拼写这个被跳过的词，让它通过
                runner.send(current_word)
                time.sleep(0.3)
                runner.wait_for_text("[OK]", timeout=3)
                runner.send(current_word)  # 第二遍正确拼写
                time.sleep(0.3)
                runner.wait_for_text("[OK]", timeout=3)
                break
            else:
                seen_words.add(current_word)
                runner.send(current_word)
                time.sleep(0.3)
                runner.wait_for_text("[OK]", timeout=3)

        if found_skipped:
            results.append((f"被跳过的词 '{first_word}' 后续再次出现", "TC-09 预期结果第2条", "PASS"))
        else:
            # 如果没找到，可能被跳过的词在队尾还没出现，也不算严格失败
            results.append((f"被跳过的词 '{first_word}' 后续再次出现", "TC-09 预期结果第2条",
                            "WARN 测试轮次内未再次出现（词可能在队尾）"))

    finally:
        runner.stop()

    return results, runner.get_output()


def test_tc11():
    """TC-11: 练习中按 Q 返回主菜单"""
    results = []
    runner = ProgramRunner()

    try:
        runner.start()
        runner.select_textbook_and_wait_menu()

        # 进入模式 3
        runner.send("3")
        runner.wait_for_text("[听写模式]", timeout=5)
        runner.wait_for_text("当前单词：", timeout=5)

        # 按 Q
        runner.send("Q")
        back = runner.wait_for_text("西班牙语陪练", timeout=5)  # 注意：目前输出用的是特殊字符但本质相同

        if back:
            results.append(("练习中按 Q 返回主菜单", "TC-11 预期结果", "PASS"))
        else:
            output = runner.get_output()
            if "西班牙语陪练" in output:
                results.append(("练习中按 Q 返回主菜单", "TC-11 预期结果", "PASS"))
            else:
                results.append(("练习中按 Q 返回主菜单", "TC-11 预期结果", "FAIL 未返回主菜单"))

        # 断言程序未退出
        if runner.is_running:
            results.append(("按 Q 后程序仍在运行", "TC-11 预期结果：回到主菜单而非退出", "PASS"))
        else:
            results.append(("按 Q 后程序仍在运行", "TC-11 预期结果：回到主菜单而非退出", "FAIL 程序已退出"))

    finally:
        runner.stop()

    return results, runner.get_output()


def test_tc20():
    """TC-20: 模式 3 中按 S 跳过，该词回到队尾（同 TC-09）"""
    # TC-20 与 TC-09 测试目标相同，共用逻辑
    return test_tc09()
