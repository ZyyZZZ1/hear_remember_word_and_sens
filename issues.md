# Issues

---

## 1. 模式 2（听中文说西语）没有中文声音 ✅ 已修复

- **修复**：TTS 初始化时同时查找中文语音（Huihui），新增 `tts_speak_zh()` 函数用中文语音朗读
- 模式 2 现在会先用中文语音念中文，用户听到中文后说西语

## 2. 模式 1 和 2 的录音时间太短 ✅ 已修复

- **修复**：录音改为 `sd.InputStream` + 回调累积模式，从 `start_recording()` 到 `stop_and_playback()` 之间持续录制，精确覆盖用户说话的全过程

## 3. 模式 1 和 2 的跳过功能设计不合理 ✅ 已修复

- **修复**：`mark_skip()` 改为永久移出本轮队列（pop 后不再 append），S 键 = "我会了，别再问了"

## 4. 生词列表缺少两个词 ✅ 已修复

- 已补充 `Enseño`（教学）和 `vuestra`（你们的）到 VOCAB

## 6. 听写模式 TTS 报错：CoInitialize ✅ 已修复

- **现象**：进入模式 3（听写）后每次 TTS 朗读都报 `[TTS] 朗读失败：(-2147221008, '尚未调用 CoInitialize。')`
- **原因**：`tts_speak_async` 在子线程中调用 `win32com.client.Dispatch`，COM 需要先 `CoInitialize`
- **修复**：在 `_tts_speak_with_voice` 开头加 `pythoncom.CoInitialize()`

## 7. 新增「句子收藏夹」功能 ⏳ 待实施

- **主题**：在现有单词收藏夹（`favorites.json` + `[*] 收藏集`）的基础上，平行新增一个**句子级**的全局收藏夹，让用户能把整句西语收藏到独立池子里，便于复习整句结构
- **完整 Plan**：见本次 opencode 会话内的"完整实施计划：句子收藏夹"回复
- **关键决策**（用户在会话中确认）：
  - 存储：扩展 `favorites.json`，新增全局 key `"句子收藏"`
  - 虚拟教材名：`收藏句子集`
  - 句子模式快捷键：`[J]收藏本句`
  - 保留旧功能 `[F]收藏句中单词`
- **计划入口**：
  - 教材选择菜单新增 `[**] 收藏句子集（N 个收藏句）`，与现有 `[*] 收藏集` 并列
  - 句子模式决策菜单新增 `[J]收藏本句`，与现有 `[F]收藏句中单词` 并列
  - 句子模式组菜单新增 `[*] 收藏句组`
- **计划新增/修改函数**：
  - 新增：`_load_sentence_favorites` / `_save_sentence_favorites` / `_get_sentence_favorites` / `_toggle_sentence_favorite` / `_build_sentence_favorites_textbook`
  - 修改：`select_textbook`、`_decision_pnbr`、`_post_judgment_menu_pnbr`、`_post_judgment_menu_ynsfq`、纯听循环、`_shadow_one`、听写-句子、混着来、`_run_group_menu_es_to_zh`、`_run_group_menu_zh_to_es`
- **现状**：⏳ **未实施**（仅完成方案讨论，未改 main.py、未改 favorites.json、未写测试）
- **提出时间**：2026-06-29

## 8. 单词做完后菜单响应慢（约 1 秒）❌ 未修复

- **现象**：每做完一个单词弹出菜单 `[Enter/P]通过 [N]保留 [B]上词 [R]重听 [G]下组 [F]收藏 [Q]退出 >`，按 Enter 后要等约 1 秒才进入下一词，反馈感不强
- **用户反馈**："有点慢，操作有阻塞感"
- **用户怀疑**："是不是已经设置了阻塞式的，所以导致的比较慢"（指菜单语音提醒）
- **代码定位**：
  - `main.py:1203 _wait_key_voice` 关键嫌疑：按键后调用 `_stop_audio()` 才会 return
  - `main.py:455 _stop_audio` 可能是阻塞点（TTS_LOCK 或 `sd.stop()` 等 buffer 排空）
  - `main.py:1188-1189` 常量 `VOICE_REMINDER_INTERVAL=20` / `VOICE_REMINDER_MAX=4`
- **用户要求**：本次**不修**，仅记录
- **修复方向（待定）**：
  1. `_stop_audio()` 加耗时打印，定位阻塞点
  2. 把"按键 → 立即返回"做成不等音频播完
- **提出时间**：2026-06-29
- **会话记录**：`c.markdown §4`

## 9. 模式 3 中文测验只识别第一个释义 ❌ 未修复

- **现象**：模式 3 听写 → 拼写完 → "请输入中文意思" 时，只对**逗号前的第一个释义**生效；输入后续任何释义（其它中文意思、英语/德语同源词放在词尾）→ ✗ 不对，再试试？
- **用户原文**："它每一次都不太去检测整个意思...只要我输A，那它就是通过的。但是我说BCD，那它就通过不了...英语同源词放在词首能识别，放在词尾识别不了"
- **教材示例**：`facultad	(英语同源词faculty),系，学院,Fakultät(德语同源词)`
- **根因**：`main.py:1392` 和 `main.py:1435`（在 `_run_one_group_memory_import` 内）用 `re.split(r'[,，、]', item["zh"])[0].strip()` 把全量释义截成 `zh_first`，**然后屏幕展示、TTS 朗读、拼写测验都只用 `zh_first`**——三个环节耦合在同一个变量上
- **巧合**：`_spelling_quiz_phase`（`main.py:680`）**本身**已支持多 variant 匹配（`zh_variants = re.split(...)`），但上游传错了，所以这个能力被浪费
- **影响范围**：**仅**模式 3 记忆导入；其他模式（`_run_one_group_practice` 等，`main.py:1609` 等）直接用 `zh_text` 全量，不受影响
- **Bug 行数**：`main.py:1392, 1397, 1400, 1403, 1429, 1435, 1436`（共 7 处用 `zh_first`）

### 关键：耦合问题

`zh_first` 当前**同时承担**两个职责：
1. **播报**（屏幕 + TTS）：只展示/念第一个
2. **匹配**（中文输入）：只接受第一个

用户原话："播报确实是只要播报第一个中文释义，因为他播报全出来太冗长了，没有问题。**但是在做中文输入的时候，他应该要能够接受更多样性的中文输入**，而不是只有播报出来的那一些的中文输入。"

→ **解耦**：播报继续用 `zh_first`，匹配用全量 `item["zh"]`

### 修复方向（仅记）

| 环节 | 当前传参 | 期望传参 | 改动 |
|------|----------|----------|------|
| 屏幕展示 | `zh_first` | `zh_first` | 不改 |
| TTS 播报 | `zh_first` | `zh_first` | 不改 |
| 中文输入匹配 | `zh_first` | `item["zh"]` | **改 `main.py:1403`** |
| R 重听（TTS） | `zh_first` | `zh_first` | 不改 |
| B 回退（TTS） | `zh_first` | `zh_first` | 不改 |

**关键改动点**：`main.py:1403`（调用 `_spelling_quiz_phase` 的地方）改传 `item["zh"]`（全量）即可。`main.py:1392, 1435` 的 `zh_first` 保留不动（仍给播报用）。`_spelling_quiz_phase` 内部 `zh_variants` 拆分（`main.py:680`）已支持多 variant，零改动即可工作。

- **用户要求**：本次**不修**，仅分析 + 记录
- **提出时间**：2026-06-29
- **会话记录**：`c.markdown §5`
