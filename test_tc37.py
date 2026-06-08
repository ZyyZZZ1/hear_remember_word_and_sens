"""
TC-37：退出后重新启动 —— 练习记录清零
依据：测试用例 TC-37 预期结果，需求规格 §2.2 无持久化
使用两个独立进程验证
"""

from conftest import ProgramRunner, extract_words_from_output
import time


def test_tc37():
    """TC-37: 退出程序再启动，之前的练习进度是否消失"""
    results = []
    passed_words = []  # 第一轮已通过的词

    # ═══ 第一轮进程 ═══
    runner1 = ProgramRunner()
    try:
        runner1.start()
        runner1.wait_for_text("西班牙语陪练")

        # 进入模式 3
        runner1.send("3")
        runner1.wait_for_text("[听写模式]", timeout=5)

        # 正确拼写前几个词使其通过（连续两次正确）
        vocab_words = [
            "Ricardo", "Rosa", "nuestra", "lengua", "universidad",
            "este", "país", "del", "González", "ahora",
        ]

        for word in vocab_words[:3]:  # 只通过前 3 个词
            # 等待该词出现
            found = runner1.wait_for_text(f"当前单词：{word}", timeout=10)
            if not found:
                continue

            # 第一次正确拼写
            runner1.send(word)
            time.sleep(0.4)
            runner1.wait_for_text("[OK]", timeout=5)

            # 等待巩固轮（同一个词再次出现）
            time.sleep(0.3)
            found_again = runner1.wait_for_text(f"当前单词：{word}", timeout=5)
            if found_again:
                # 第二次正确拼写
                runner1.send(word)
                time.sleep(0.4)
                runner1.wait_for_text("[OK]", timeout=5)
                passed_words.append(word)
                results.append((f"第一轮通过 '{word}'（连续两次正确）", "TC-37 准备步骤", "PASS"))
            else:
                # 巩固轮可能排到后面了，跳过
                results.append((f"第一轮通过 '{word}'（巩固轮未立即出现）",
                                "TC-37 准备步骤", "WARN"))

        # 退出第一轮
        runner1.send("Q")
        runner1.wait_for_text("西班牙语陪练", timeout=5)
        runner1.send("Q")  # 再按 Q 退出程序
        time.sleep(1)

    finally:
        runner1.stop()

    results.append((f"第一轮已通过词列表：{passed_words}", "TC-37 准备步骤", "PASS"))

    # ═══ 第二轮进程（全新独立进程） ═══
    runner2 = ProgramRunner()
    try:
        runner2.start()
        runner2.wait_for_text("西班牙语陪练")

        # 进入模式 3
        runner2.send("3")
        runner2.wait_for_text("[听写模式]", timeout=5)
        runner2.wait_for_text("当前单词：", timeout=5)
        time.sleep(0.5)

        # 收集第二轮出现的所有单词
        output2 = runner2.get_output()
        round2_words = set(extract_words_from_output(output2))

        # 继续收集几轮
        for _ in range(10):
            words = extract_words_from_output(runner2.get_output())
            if words:
                runner2.send("S")  # 跳过
                time.sleep(0.3)
                runner2.wait_for_text("当前单词：", timeout=3)
            else:
                break

        final_output = runner2.get_output()
        all_round2_words = set(extract_words_from_output(final_output))

        # 断言：第一轮已通过的词在第二轮中重新出现
        all_reappeared = True
        for pw in passed_words:
            if pw in all_round2_words:
                results.append((f"已通过词 '{pw}' 在第二轮重新出现", "TC-37 预期结果：记录清零", "PASS"))
            else:
                all_reappeared = False
                results.append((f"已通过词 '{pw}' 在第二轮重新出现", "TC-37 预期结果：记录清零",
                                f"FAIL 未在第二轮单词列表中找到"))

        if all_reappeared and len(passed_words) > 0:
            results.append(("全部已通过词均在第二轮重新出现，持久化未发生",
                            "TC-37 预期结果：从零开始", "PASS"))
        elif len(passed_words) == 0:
            results.append(("无已通过词可验证", "TC-37 预期结果", "WARN 第一轮未通过任何词"))

    finally:
        runner2.stop()

    return results, f"第一轮通过={passed_words}, 第二轮词={all_round2_words}"
