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
