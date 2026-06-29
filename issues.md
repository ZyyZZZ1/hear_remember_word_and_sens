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
