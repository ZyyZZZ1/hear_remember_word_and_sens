# Sharplingo 教材扒取与提取 Skill

从 sharplingo.cn 扒取课程内容 → 保存原生教材 → 按规范提取为三段式教材 → 审计补漏 → 标注动词变位。

## 前置条件

- Chrome 浏览器（已登录 sharplingo.cn）
- Python 环境 + `websocket-client` 包
- Chrome 必须以调试模式启动：
  ```
  "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=*
  ```
  或使用临时配置（解决企业策略干扰）：
  ```
  "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=C:\Temp\chrome-scrape
  ```

## 工具文件

| 文件 | 作用 |
|------|------|
| `scrape_sharplingo.py` | Chrome CDP 直连扒取脚本，将课程页面全部文本 dump 到 原生教材/ |
| `../教材提取规范.md` | 教材三段式提取规范（生词/例句/语法点） |
| `scrape_sharplingo.py` 中的 `quick_debug.py` 逻辑 | 用于调试单个页面加载问题 |

## 完整工作流

### 阶段 1：扒取原生教材

1. **确认 Chrome 调试端口可用**：
   ```
   Invoke-WebRequest -Uri "http://127.0.0.1:9222/json/version" -UseBasicParsing
   ```
   如果返回 404 或连接失败 → 参考前置条件重启 Chrome

2. **确认用户已登录**：在 Chrome 中打开 https://sharplingo.cn ，确认已切换到对应课程（西班牙语课）

3. **运行扒取脚本**：
   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   & python scrape_sharplingo.py
   ```
   脚本自动：
   - 连接 Chrome CDP WebSocket
   - 从模块页面提取所有课程链接
   - 逐个导航到课程页面，dump `document.body.innerText`
   - 以 `01-XX.txt` / `02-XX.txt` 命名保存到 `原生教材/`
   - 跳过已存在的文件

4. **验证**：检查 `原生教材/` 文件数和内容完整性

### 阶段 2：提取教材（三段式）

**关键**：必须用 LLM Agent 逐课处理，禁止脚本硬解析。

1. **检查现有教材**：
   ```powershell
   Get-ChildItem "教材/" -Filter "*.txt"
   ```

2. **分批并行启动 Agent**：
   每批 ~8-18 个文件，给每个 Agent：
   - 教材提取规范（三段式规则）
   - 已学词汇库（来自前面课程的生词区汇总）
   - 要处理的原生教材文件列表

3. **Agent prompt 关键要素**：
   - 输出格式：`# 生词` / `# 例句` / `# 语法点`
   - 西语-中文 Tab 分隔
   - 生词 = 不在已学词汇库中的所有实词
   - 动词列原形，人名不列，地名国名要列
   - 固定搭配（2词及以上）放生词区
   - 例句按原文顺序、去重

4. **顺序处理**：Agent 内按课号从小到大处理，每课生成后将其生词加入词汇库

### 阶段 3：审计补漏

1. **启动审计 Agent**：
   - 从 01-01 开始逐课累积生词
   - 检查每课例句中的实词是否都在已学词汇库中
   - 标记「漏词」——出现在例句但从未列入生词的实词

2. **修复漏词**：
   - 将漏词补入首次出现的课
   - 从后出课中删除重复条目

3. **常见漏词类型**：
   - 名词：casa, familia, hospital, instituto, médico, padre, ventana
   - 形容词/副词：bien, hoy, mejor
   - 原因：Agent 并行处理时词汇库共享不完整

### 阶段 4：拆出动词变位独立条目

1. **运行拆解脚本**：
   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   & python unpack_conjugations.py
   ```
   脚本自动将 `[...]` 括号变位拆成独立生词条目。

2. **变位格式**（已写入规范 4.3.1）：每个变位是独立的一行，Tab 分隔：
   ```
   hablar	说，讲
   hablo	我说
   hablas	你说
   habla	他说/她说
   hablamos	我们说
   habláis	你们说
   hablan	他们说/她们说
   ```

3. **自复动词**：以 -se 形式列出原形，变位包含自复代词：
   ```
   levantarse	起床
   me levanto	我起床
   te levantas	你起床
   se levanta	他/她起床
   nos levantamos	我们起床
   os levantáis	你们起床
   se levantan	他们/她们起床
   ```

4. **中文翻译规则**：
   - 人称代词 + 核心含义（如「我说」「你洗澡」「他/她带上」）
   - 取动词的第一个核心含义，不加注释修饰

5. **西班牙语变位速查**：
   - **规则 -ar**: o, as, a, amos, áis, an
   - **规则 -er**: o, es, e, emos, éis, en
   - **规则 -ir**: o, es, e, imos, ís, en
   - **常用不规则**：ser, estar, ir, tener(e→ie), hacer, decir(e→i), venir(e→ie), querer(e→ie), poder(o→ue), poner, saber, salir, dar, ver, oír, traer, haber
   - **自复**：me/te/se/nos/os/se + 动词变位

## 模块-课程对应关系

- 模块 01 URL: `https://sharplingo.cn/courses/60182ef4343d07c8ad9a2e73/module/663f25e1b826335d890c83e9/show`
- 模块 02 URL: `https://sharplingo.cn/courses/60182ef4343d07c8ad9a2e73/module/66cd90ee8a23e70015fe9584/show`
- 文件名格式：`{模块号}-{课程号:02d}.txt`（如 `01-14.txt`）
- 模块 01：第01~28讲 → 文件 01-01 ~ 01-28
- 模块 02：第01~37讲 → 文件 02-01 ~ 02-37

## 两种课程页面类型

| 类型 | URL 模式 | 特点 | 课程号获取 |
|------|----------|------|-----------|
| Lecture（语法课） | `/courses/show-lecture/...` | 语法讲解+例句，无音频控制栏 | body 中有 "模块XX - 第XX讲" |
| Article（阅读课） | `/courses/show-article/...` | 阅读文章+对话，有音频播放器 | body 中有 "模块XX - 第XX讲"，需搜索全文 |

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 扒取结果全是登录页文字 | Cookie 丢失或课程被切换 | 在 Chrome 中重新登录，确认切换到西班牙语课 |
| Article 页面重定向到 classroom | 课程未切换到西班牙语 | 切换到西班牙语课程 |
| 调试端口 404 | Chrome 企业策略或旧 DevToolsActivePort 残留 | 使用临时配置 `--user-data-dir=C:\Temp\chrome-scrape` |
| WebSocket 403 Forbidden | 缺少 `--remote-allow-origins=*` 标志 | 重启 Chrome 加上该标志 |
| Agent 生成的教材漏词 | 并行 Agent 词汇库不完整 | 跑阶段 3 审计补漏 |
