"""
test_runner.py —— 自动化测试主入口
依次执行 12 条 [自动] 用例，生成 test_report.md
"""

import os
import sys
import time
import traceback

# 确保能找到测试模块
sys.path.insert(0, os.path.dirname(__file__))

from test_tc01 import test_tc01
from test_tc02 import test_tc02
from test_tc03 import test_tc03
from test_tc0911 import test_tc09, test_tc11, test_tc20
from test_tc161718 import test_tc16, test_tc17, test_tc18
from test_tc29 import test_tc29
from test_tc33 import test_tc33
from test_tc37 import test_tc37

# ── 用例注册表 ────────────────────────────────────────────
# 顺序按测试用例编号排列

TEST_CASES = [
    # (编号, 名称, 测试函数, 测试内容原文)
    ("TC-01", "启动程序", test_tc01,
     "程序能否正常启动并显示主菜单"),
    ("TC-02", "主菜单选模式", test_tc02,
     "主菜单各按键是否进入对应模式"),
    ("TC-03", "主菜单按 Q 退出", test_tc03,
     "在主菜单按 Q 是否退出程序"),
    ("TC-09", "S 键跳过", test_tc09,
     "按 S 跳过当前词，该词稍后是否再次出现"),
    ("TC-11", "练习中按 Q 返回主菜单", test_tc11,
     "练习中途按 Q 是否回到主菜单"),
    ("TC-16", "拼写正确——通过", test_tc16,
     "输入正确拼写后程序判定通过"),
    ("TC-17", "拼写错误——回队尾", test_tc17,
     "输入错误拼写后程序指出正确拼写并回队尾"),
    ("TC-18", "连续两次拼写正确后通过", test_tc18,
     "同一词连续两次正确拼写后不再出现"),
    ("TC-20", "S 键跳过（补充）", test_tc20,
     "按 S 跳过，该词回到队尾"),
    ("TC-29", "语法点列表展示", test_tc29,
     "按 G 后是否显示语法点列表"),
    ("TC-33", "录音文件不残留", test_tc33,
     "退出程序后录音临时文件是否被清理"),
    ("TC-37", "退出后重新启动——练习记录清零", test_tc37,
     "退出程序再启动，之前的练习进度是否消失"),
]


def run_all():
    """执行所有用例，返回结构化结果列表"""
    all_results = []

    for tc_id, tc_name, tc_func, tc_desc in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"  执行 {tc_id}：{tc_name}…")
        print(f"{'='*60}")

        start_time = time.time()
        try:
            assertions, output_snippet = tc_func()
            elapsed = time.time() - start_time

            # 判断总体结果
            failed = [a for a in assertions if a[2].startswith("FAIL")]
            warnings = [a for a in assertions if a[2].startswith("WARN")]
            if failed:
                status = "FAIL 失败"
            elif warnings:
                status = "WARN 通过（有警告）"
            else:
                status = "PASS 通过"

            # 截取输出片段（前 800 字符）
            snippet = output_snippet[:800] if output_snippet else "(无输出)"

        except Exception as e:
            elapsed = time.time() - start_time
            assertions = [("执行异常", "", f"FAIL {traceback.format_exc()}")]
            status = "FAIL 失败（异常）"
            snippet = f"异常：{e}"

        all_results.append({
            "id": tc_id,
            "name": tc_name,
            "description": tc_desc,
            "status": status,
            "elapsed": f"{elapsed:.1f}s",
            "assertions": assertions,
            "output_snippet": snippet,
        })

        # 简要输出
        print(f"  → {status} ({elapsed:.1f}s)")

    return all_results


def generate_report(results, report_path="test_report.md"):
    """根据测试结果生成 test_report.md"""

    lines = []
    lines.append("# 西班牙语陪练程序 —— 自动化测试报告\n")
    lines.append(f"**生成时间：** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**被测程序：** `main.py`\n")
    lines.append("---\n")

    # ── 逐条用例 ──
    for r in results:
        tc_id = r["id"]
        tc_name = r["name"]
        status = r["status"]
        description = r["description"]
        elapsed = r["elapsed"]
        assertions = r["assertions"]
        snippet = r["output_snippet"]

        lines.append(f"## {tc_id}：{tc_name} —— {status}\n")
        lines.append(f"- **测试内容**：{description}")
        lines.append(f"- **执行过程**：")
        lines.append(f"  1. 启动子进程 `python main.py`")
        lines.append(f"  2. 发送按键 / 读取 stdout")
        lines.append(f"  3. 验证断言条件")
        lines.append(f"- **耗时**：{elapsed}")
        lines.append(f"- **关键输出片段**：")
        lines.append(f"  ```")
        for line in snippet.split("\n")[:20]:
            lines.append(f"  {line}")
        lines.append(f"  ```")
        lines.append(f"- **断言结果**：")
        lines.append(f"  | 断言 | 依据（文档出处） | 结果 |")
        lines.append(f"  |------|-----------------|------|")
        for assertion in assertions:
            label, doc_ref, result = assertion
            # 转义表格中的管道符
            label = label.replace("|", "\\|")
            doc_ref = doc_ref.replace("|", "\\|")
            lines.append(f"  | {label} | {doc_ref} | {result} |")
        lines.append(f"- **代码依据**：断言代码见对应 `test_{tc_id.lower().replace('-','')}.py`，"
                      f"每行断言上方有注释标注对应的测试用例条款号")
        lines.append("")

    # ── 汇总 ──
    passed = sum(1 for r in results if "PASS" in r["status"])
    failed = sum(1 for r in results if "FAIL" in r["status"])
    warned = sum(1 for r in results if "WARN" in r["status"])
    skipped = 0  # 当前无跳过策略触发

    lines.append("---\n")
    lines.append("## 汇总\n")
    lines.append("| 用例 | 结果 | 耗时 |")
    lines.append("|------|------|------|")
    for r in results:
        lines.append(f"| {r['id']} | {r['status']} | {r['elapsed']} |")
    lines.append("")
    lines.append(f"**通过：{passed} / {len(results)}，"
                 f"失败：{failed} / {len(results)}，"
                 f"跳过：{skipped} / {len(results)}**")
    if warned:
        lines.append(f"\n（{warned} 条用例有警告，需人工确认）")
    lines.append("")

    # ── 防止造假机制 ──
    lines.append("---\n")
    lines.append("## 防止造假机制\n")
    lines.append("| 机制 | 说明 |")
    lines.append("|------|------|")
    lines.append("| 断言挂文档 | 每条断言代码的注释必须引用测试用例的具体行号和条款 |")
    lines.append("| stdout 原文取证 | 报告中粘贴程序的真实 stdout 输出，不用脚本的\"理解\"代替 |")
    lines.append("| 输入来自输出 | 拼写测试中，脚本输入的内容是从程序 stdout 中读到的，不是脚本自编的 |")
    lines.append("| baseline 对比 | 文件残留检查用\"前后差异\"而非\"目录为空\" |")
    lines.append("| 独立进程验证 | 持久化测试用两个独立进程，防止共享内存状态导致的虚假通过 |")
    lines.append("| 预期值来自文档 | 语法点清单等预期值直接取自总计划 §1.5 的生词表/语法点表，不动态生成 |")
    lines.append("")

    # 写入文件
    content = "\n".join(lines)
    report_path = os.path.join(os.path.dirname(__file__), report_path)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n📄 测试报告已生成：{report_path}")
    return report_path


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║   西班牙语陪练程序 —— 自动化测试执行器     ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\n共 {len(TEST_CASES)} 条自动化用例待执行\n")

    results = run_all()
    generate_report(results)

    # 简要摘要
    passed = sum(1 for r in results if "PASS" in r["status"])
    failed = sum(1 for r in results if "FAIL" in r["status"])
    print(f"\n{'='*60}")
    print(f"  执行完毕：{passed} 通过，{failed} 失败，共 {len(results)} 条")
    print(f"{'='*60}")
