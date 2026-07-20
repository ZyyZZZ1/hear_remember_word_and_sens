# c.markdown

> 本会话进行中的问题、计划与状态记录。
> 创建日期：2026-06-29

---

## 0. 关于本文件

- **之前是否有过写为 markdown 的计划？** ❌ **没有**。本会话之前所有计划（包括已执行的复习课命名改造、当前未完成的 Kokoro 排查）都只存在于对话中，未落盘到任何文件。
- **本文件路径**：`D:\程序\脚本\01-08\c.markdown`（项目根目录）
- **记录范围**：2026-06-29 当天会话内产生的所有"问题 / 计划 / 实施状态"

---

## 1. 复习课命名规则改造 ✅ 已完成

### 1.1 问题

原命名 `01-16-复习课1`、`01-16-复习课2` 较长，输入繁琐，需要更简洁的代号。

### 1.2 计划（2026-06-29 上午提出）

格式：`XX-XX-<大写字母>`

- `XX-XX` = 复习课插入位置（在前一课之后、该编号课之前）
- 大写字母 = 同位置的第几个复习课（A=1, B=2, C=3……）
- 变体细分用 `-A1`、`-A2` 后缀

### 1.3 实施状态 ✅ 已完成

| 步骤 | 状态 | 内容 |
|------|------|------|
| 1 | ✅ | `教材/01-16-复习课1.txt` → `教材/01-16-A.txt` |
| 2 | ✅ | `教材/01-16-复习课2.txt` → `教材/01-16-B.txt` |
| 3 | ✅ | `favorites.json` key `"01-16-复习课1"` → `"01-16-A"`（6 个词内容不变） |
| 4 | ✅ | `.opencode/skills/generate-review-lesson/SKILL.md`（4 处更新：description / 示例 / 文件格式 / 已学范围说明） |
| 5 | ✅ | `.opencode/skills/add-favorite-word/SKILL.md`（2 处更新：课号示例 + 故障排查示例） |
| 6 | ✅ | grep 校验：`01-16-复习` 全仓 0 命中；`01-16-A/B` 引用一致 |

### 1.4 涉及文件清单

- `教材/01-16-A.txt`（原 01-16-复习课1.txt）
- `教材/01-16-B.txt`（原 01-16-复习课2.txt）
- `favorites.json:57`（key 改写）
- `.opencode/skills/generate-review-lesson/SKILL.md:3,10,14,34`
- `.opencode/skills/add-favorite-word/SKILL.md:77,80`

### 1.5 备注

- `audit_vocab.py` 因内置 `BASE_DIR` 写死旧路径（`c:\Users\OZI2SZH\...`）无法运行；本系统 `python.exe` 是 WindowsApps 0 字节占位符，Python 同样不可执行。改名靠 `Get-ChildItem` 校验，文件内容已用 read 工具直接确认。
- 临时调试文件已清理。

---

## 2. Kokoro TTS 不启用 ❌ 未解决（排查中）

### 2.1 问题（2026-06-29 提出）

用户询问：为什么 `kokoro` 语音引擎没启用。

### 2.2 排查结果（已确认的部分）

| 检查项 | 状态 |
|--------|------|
| 模型文件 `kokoro_models/kokoro-v1_1-zh.pth` (327MB) | ✅ 存在 |
| 配置 `kokoro_models/kmodel_config.json` (3.6KB) | ✅ 存在 |
| 声音文件 `kokoro_models/voices/zf_001.pt` 等 | ✅ 存在（3 个 .pt 声音） |
| Python 解释器 | ⚠️ WindowsApps 占位符（0 字节），本沙箱无法直接执行 |
| 用户本地环境 | 🟡 conda 环境（用户口头确认，未拿到 env 名） |
| `torch` / `kokoro` 包是否安装 | ❓ 未知，等用户排查 |

### 2.3 直接原因（推断）

`main.py:67-68` 的 Kokoro 加载块使用 `try / except ImportError: pass`（`main.py:104-105`），**ImportError 被静默吞掉**，不打印任何信息。如果 `torch` 或 `kokoro` 包没装，用户看不到 Kokoro 相关任何日志。

### 2.4 计划（2026-06-29 提出，未执行）

#### 阶段 1：用户执行排查

```powershell
# 1) 定位 conda env
conda env list
where.exe python

# 2) 在该 env 里查关键包
conda activate <env名>
pip list 2>&1 | Select-String -Pattern "torch|kokoro|jieba|phonemizer|espeakng"

# 3) 跑 main.py 抓启动日志
python main.py
```

#### 阶段 2：拿到结果后，精确装包（待定）

根据 `pip list` 输出，缺啥装啥。预案：

```powershell
conda activate <env名>
conda install pytorch::pytorch torchvision torchaudio cpuonly -c pytorch
pip install kokoro jieba phonemizer espeakng-loader
conda install -c conda-forge espeak-ng
```

#### 阶段 3：验证

```powershell
python -c "import torch; from kokoro import KPipeline, KModel; print('torch', torch.__version__); print('kokoro OK')"
python main.py
```

期望看到 `[TTS] Kokoro 中文语音已加载`。

### 2.5 实施状态 🟡 等待用户反馈

- 用户已确认用 conda 环境
- 还没拿到 `conda env list` 和 `pip list` 的输出
- 装包命令**未执行**

### 2.6 注意事项

- 用户明确要求**不动 main.py**，所以 `main.py:104` 的静默吞错保持原样
- Kokoro **只用于中文朗读**（`tts_speak_zh`，见 `main.py:436-455`）；西语 TTS 用 Piper，与 Kokoro 无关

---

## 3. 快捷键需要按两次才能调出弹窗 ❌ 待排查

### 3.1 问题（2026-06-29 提出）

- **症状**：需要按 **两次** 快捷键才能把弹窗调出来，按一次没反应
- **用户评价**：很令人疑惑
- **可能原因（待验证）**：
  1. 第一次按键被系统/防抖逻辑吞掉
  2. 监听器只在"窗口最小化/失焦"状态下生效，第一次是"聚焦"，第二次才是"唤起"
  3. 全局热键注册时被其他进程抢占
  4. 弹窗代码里有 first-time init 卡顿

### 3.2 计划（2026-06-29 记录）

1. 定位热键监听实现（参考 `热键弹窗设计.md`）
2. 复现：确认是否稳定两次唤起，还是偶发
3. 排查监听逻辑、首次按键处理、防抖窗口
4. 给出修复方案

### 3.3 实施状态 ⏸️ 未启动

- 只记录现象，未开始排查
- 相关文件：`热键弹窗设计.md`、`热键弹窗测试用例.md`

---

## 4. 单词做完后菜单响应慢 ❌ 待优化

### 4.1 问题（2026-06-29 提出）

- **场景**：每做完一个单词，弹出菜单 `[Enter/P]通过  [N]保留  [B]上词  [R]重听  [G]下组  [F]收藏  [Q]退出 >`
- **症状**：按 Enter 后要等 **~1 秒** 才有反应，反馈感不强
- **用户评价**：有点慢，操作有阻塞感

### 4.2 用户怀疑的原因

- 可能是播放"请选择菜单"语音时设了**阻塞式**，导致按键处理被卡住
- 怀疑 `_stop_audio()` 在等 TTS 播完当前 buffer 才返回

### 4.3 代码定位（已读）

相关函数 `main.py:1203-1252` `_wait_key_voice`：

```python
for attempt in range(1, max_attempts + 1):
    _speak_zh_async_silent(voice_text)            # 异步播"请选择菜单"

    deadline = time.time() + interval             # 20s 一次循环
    while time.time() < deadline:
        if _safe_kbhit():
            ch = msvcrt.getch().decode(...)
            _stop_audio()                          # ← 嫌疑点
            _clear_line()
            return ch.upper()
        time.sleep(0.01)
```

- 关键嫌疑点：`_stop_audio()`（`main.py:455`）可能阻塞在 `TTS_LOCK` 或 `sd.stop()` 上
- 计时：`VOICE_REMINDER_INTERVAL = 20` 秒（`main.py:1188`），单次最多 4 次（`VOICE_REMINDER_MAX = 4`，`main.py:1189`）

### 4.4 计划（仅记录，未启动）

1. 在 `_stop_audio()` 里加耗时打印，定位阻塞点
2. 评估是否要把"按键 → 立刻返回"做成不等音频停完
3. 方案确定后再改 main.py（用户明确说本次**不修**）

### 4.5 实施状态 ⏸️ 未启动

- 只记录现象 + 定位代码，未改任何代码
- 涉及位置：`main.py:1203 _wait_key_voice`、`main.py:455 _stop_audio`、`main.py:1188-1189` 常量

---

## 5. 模式 3 中文测验只识别第一个释义 ❌ 待修复

### 5.1 问题（2026-06-29 提出）

- **场景**：模式 3 听写 → 拼写完 → "请输入中文意思"
- **教材示例**：`facultad	(英语同源词faculty),系，学院,Fakultät(德语同源词)`（多个释义 + 英德同源词）
- **症状**：
  - 输入第一个释义（逗号前的内容）→ 通过
  - 输入后续任何释义（BCD、放在词尾的英语/德语同源词）→ ✗ 不对，再试试？
- **用户评价**：很令人疑惑

### 5.2 根因（已分析）

**Bug 位置**：`main.py:1392` 和 `main.py:1435`（仅在 `_run_one_group_memory_import` 内）

```python
zh_first = re.split(r'[,，、]', item["zh"])[0].strip()   # ← 罪魁
print(f"  {es_text} — {zh_first}\n")                       # 屏幕只显示第一个
_memory_import_loop(es_text, zh_first)                     # TTS 只念第一个
_spelling_quiz_phase(es_text, zh_first)                    # 测验只用第一个
```

函数开头用 `re.split(...)[0]` 把全量释义**只取第一个 variant**，屏幕展示、TTS 朗读、拼写测验**全部**只用第一个变体。后续释义（包括放在词尾的英语/德语同源词）从不被展示、不被朗读、不被作为匹配项。

### 5.3 为什么"词首工作、词尾不工作"

- 英语/德语同源词如果写在第一个 variant 里（如 `(英语同源词faculty),系,学院`）→ 能被识别（因为它就是 `zh_first`）
- 同源词写在后面的 variant 里（如 `系,学院,Fakultät(德语同源词)`）→ 被 `[0]` 截掉，不被识别

### 5.4 巧合（值得记）

`_spelling_quiz_phase`（`main.py:680`）**本身**已经支持多 variant 匹配（`zh_variants = re.split(...)`），但因为上游只传了 `zh_first`，这个能力被白白浪费。

### 5.5 影响范围

- **仅**"模式 3 记忆导入"（`_run_one_group_memory_import`，`main.py:1381`）有 bug
- 其他模式（`_run_one_group_practice`、`_run_group_menu_es_to_zh` 等）直接用 `zh_text` 全量，**不受影响**
- 共 2 处用到 `zh_first`：`main.py:1392`（当前词）、`main.py:1435`（回退词）

### 5.6 修复方向（仅记，未启动）

**关键设计原则：解耦"播报"和"匹配"**

| 环节 | 当前行为 | 期望行为 |
|------|----------|----------|
| 屏幕展示 | 显示第一个 variant | ✅ **保持**（保持） |
| TTS 播报 | 只念第一个 variant | ✅ **保持**（全念太冗长） |
| 中文输入匹配 | 只匹配第一个 variant | ❌ **应接受所有 variant** |

**正确做法**：把 `zh_first` 拆成两个变量：
- `zh_for_speak = zh_first` —— 播报用，保留全量冗长优化
- `zh_text = item["zh"]` —— 匹配用，传全量给 `_spelling_quiz_phase`

**改动点**：
- `main.py:1392, 1435` 的 `zh_first` 保留（播报用）
- 新增 `zh_text = item["zh"]` 或类似变量
- `main.py:1403`（调用 `_spelling_quiz_phase`）传全量
- `main.py:1429, 1436`（R 重听 / B 回退）播报用 `zh_first`，匹配保持当前调用

**关键不破坏**：`_spelling_quiz_phase` 内部 `zh_variants` 拆分（`main.py:680`）已经能处理多 variant，零改动即可用。

### 5.7 实施状态 ⏸️ 未启动

- 用户本次**未要求修复**，仅要求"分析 + 记到 issues"
- 已记到 `issues.md §9`

---

## 6. 当前总状态

| 任务 | 状态 | 阻塞点 |
|------|------|--------|
| 复习课命名改造 | ✅ 完成 | — |
| Kokoro 排查 | 🟡 进行中 | 等用户执行 `conda env list` + `pip list` |
| Kokoro 装包 | ⏸️ 待启动 | 依赖上一项结果 |
| Kokoro 验证 | ⏸️ 待启动 | 依赖装包结果 |
| 快捷键两次唤起 | ⏸️ 未启动 | 等用户确认是否排查 |
| 菜单响应慢 | ⏸️ 未启动 | 用户已明确本次不修 |
| 模式 3 只识别第一个释义 | ⏸️ 未启动 | 用户明确本次不修 |

---

## 7. 文件位置索引

| 文件 | 路径 | 用途 |
|------|------|------|
| **本文件** | `D:\程序\脚本\01-08\c.markdown` | 本会话进行中事项 |
| 复习课 SKILL | `.opencode/skills/generate-review-lesson/SKILL.md` | 复习课生成规则（已更新） |
| 收藏夹 SKILL | `.opencode/skills/add-favorite-word/SKILL.md` | 收藏夹规则（已更新） |
| 教材文件 | `教材/01-16-A.txt`、`教材/01-16-B.txt` | 复习课教材（已重命名） |
| 收藏数据 | `favorites.json` | 收藏生词（key 已更新） |
| 主程序 | `main.py:67-107` | Kokoro 加载块（未改） |
| 菜单响应 | `main.py:1203 _wait_key_voice`、`main.py:455 _stop_audio` | 嫌疑阻塞点（未改） |
| 模式 3 中文测验 | `main.py:1392,1435` (`zh_first` 截取) | 多释义只取第一个（未改） |
| 已知 issues | `issues.md` | 旧问题记录 |
| 总计划 | `总计划.md` | 项目级总计划（未变） |
| 热键弹窗设计 | `热键弹窗设计.md` | 快捷键弹窗设计文档（待查） |
| 热键测试用例 | `热键弹窗测试用例.md` | 弹窗测试用例（待查） |
