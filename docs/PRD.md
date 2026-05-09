# Taxo - 产品需求文档 (PRD)

## 1. 产品概述

### 1.1 产品名称
Taxo

### 1.2 产品定位
Taxo 是一个面向开发者和高级用户的 AI 驱动 CLI 文件分类工具，专注于用最低成本自动整理 Downloads 文件夹和文档库。

### 1.3 目标用户
- 开发者和技术用户
- 频繁下载文件但缺乏整理习惯的用户
- 希望用 AI 自动化文件管理的效率工具用户
- 注重隐私和成本控制的用户

### 1.4 核心价值主张
- **低成本**: 规则引擎处理 80% 文件，LLM 只处理剩余 20%
- **可配置**: 所有行为（分类维度、规则、API、交互模式）均可配置
- **安全**: 默认不读文件内容，支持撤销，审计日志完整
- **灵活**: 支持任何 OpenAI 兼容 API（DeepSeek、GLM、Claude 等）

### 1.5 竞品分析

| 竞品 | 类型 | 成本 | 隐私 | 可配置性 | 我们的优势 |
|------|------|------|------|----------|-----------|
| AI File Sorter | 桌面应用 | 本地免费/远程付费 | 高 | 低 | Taxo 更轻量、更灵活 |
| Sparkle | macOS 应用 | $30/月 | 低 | 低 | Taxo 支持自定义 API、跨平台 |
| FileNeatAI | 桌面应用 | 付费 | 中 | 低 | Taxo 开源、可配置 |
| AIFiles CLI | Node.js CLI | 免费/付费 | 高 | 中 | Taxo Python 生态、更现代 |

## 2. 功能需求

### 2.1 核心功能模块

#### 2.1.1 文件扫描 (scanner.py)

**需求描述**: 递归扫描指定目录，收集文件元数据，过滤系统文件。

**输入**: 目标目录路径、配置（排除模式、最大深度等）
**输出**: FileItem 列表

**功能细节**:
- 递归扫描目录树
- 收集每个文件的：文件名、扩展名、大小、修改时间、创建时间、完整路径
- 排除系统文件和目录：
  - macOS: .DS_Store, .localized, .Spotlight-V100, .Trashes, .fseventsd
  - Windows: Thumbs.db, desktop.ini, $RECYCLE.BIN
  - Linux: .Trash, .cache
  - 隐藏文件（以 . 开头）默认排除，可配置
  - 符号链接默认不跟随
- 支持配置最大扫描深度（默认无限制）
- 支持配置最小/最大文件大小过滤
- 支持配置排除模式（glob 或 regex）
- 处理文件名编码问题（macOS NFD normalize）
- 输出进度信息（Rich 进度条）

**性能要求**: 扫描 1000 个文件 < 1 秒

#### 2.1.2 规则引擎 (rules.py)

**需求描述**: 基于扩展名和文件名模式的零成本分类引擎。

**输入**: FileItem 列表
**输出**: (规则匹配结果, 未匹配文件列表)

**功能细节**:
- 内置规则集（可覆盖、可扩展）:
  - 图片: .jpg, .jpeg, .png, .gif, .bmp, .webp, .svg, .ico, .raw, .cr2, .nef
  - 文档: .pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx, .odt, .ods, .odp, .txt, .md, .rtf
  - 电子书: .epub, .mobi, .azw3, .fb2, .djvu
  - 代码: .py, .js, .ts, .java, .cpp, .c, .h, .go, .rs, .rb, .php, .swift, .kt, .scala
  - 数据: .json, .xml, .yaml, .yml, .csv, .tsv, .sql, .db, .sqlite
  - 压缩包: .zip, .rar, .7z, .tar, .gz, .bz2, .xz, .dmg, .iso
  - 安装包: .exe, .msi, .pkg, .deb, .rpm, .appimage, .dmg
  - 视频: .mp4, .avi, .mkv, .mov, .wmv, .flv, .webm, .m4v, .mpg, .mpeg
  - 音频: .mp3, .wav, .flac, .aac, .ogg, .m4a, .wma, .opus, .aiff
  - 字体: .ttf, .otf, .woff, .woff2, .eot
  - 设计: .psd, .ai, .sketch, .fig, .xd, .afdesign, .afphoto
- 支持自定义规则（用户通过 CLI 添加）
- 规则格式支持:
  - 扩展名匹配: `ext:.epub → 电子书`
  - 文件名模式: `pattern:*invoice* → 发票`
  - 正则匹配: `regex:^[0-9]{4}-[0-9]{2}- → 日期文件`
  - 组合条件: `ext:.pdf AND pattern:*report* → 报告`
- 规则优先级：用户自定义规则 > 内置规则
- 规则冲突处理：第一个匹配的规则生效

**性能要求**: 1000 个文件规则匹配 < 100ms

#### 2.1.3 LLM 分类 (classifier.py + llm.py)

**需求描述**: 对规则引擎未匹配的文件，批量调用 LLM 进行语义分类。

**输入**: 未匹配的 FileItem 列表、分类维度配置、LLM 配置
**输出**: 分类结果映射 {category: [files]}

**功能细节**:
- **批量处理**: 一次发送 30-50 个文件（可配置 batch_size）
- **Prompt 设计**:
  - System prompt 包含分类维度定义和输出格式要求
  - User prompt 包含文件列表（文件名、扩展名、大小、修改时间）
  - 要求输出严格 JSON 格式
- **分类维度**（可配置）:
  - **类型模式 (type)**: 按文件类型大类（文档/图片/视频/代码等）
  - **语义模式 (semantic)**: 按内容主题（财务/设计/个人/工作/学习等）
  - **项目模式 (project)**: 按项目归属（需要 LLM 推断项目名）
  - **混合模式 (hybrid)**: 先按类型大类，文档类再按语义细分（默认）
- **LLM 客户端**:
  - 支持任何 OpenAI Chat Completions 兼容 API
  - 可配置 base_url、api_key、model、timeout
  - 支持多 provider 配置（主 provider + 备用 provider）
  - 自动重试 3 次（指数退避）
  - 网络不可达时降级为纯规则模式
- **Token 成本控制**:
  - 每次调用前估算 token 数
  - 支持设置单次调用最大 token 限制
  - 支持设置月度/总预算上限
  - 成本统计和报告
- **响应解析**:
  - 严格 JSON 模式解析
  - 解析失败时标记为未分类
  - 记录 LLM 原始响应用于调试

**Prompt 模板示例**:
```
System: 你是文件分类助手。根据文件名和元数据，将文件分类到以下类别：
{分类维度定义}

要求：
1. 输出严格 JSON 格式
2. 每个文件必须分配到一个类别
3. 如果不确定，放入 "未分类"
4. 不要添加任何解释文字

User: 请分类以下文件：
[
  {"name": "Q4财务报告.pdf", "ext": ".pdf", "size": "2.3MB", "mtime": "2026-05-01"},
  {"name": "Screenshot 2026-05-03.png", "ext": ".png", "size": "340KB", "mtime": "2026-05-03"},
  ...
]

期望输出：
{
  "categories": {
    "财务文档": ["Q4财务报告.pdf"],
    "截图": ["Screenshot 2026-05-03.png"]
  },
  "uncategorized": []
}
```

**性能要求**: 单次 API 调用 < 5 秒（含重试）

#### 2.1.4 整理计划 (planner.py)

**需求描述**: 根据分类结果生成文件移动方案，检测冲突。

**输入**: 分类结果、目标目录结构配置
**输出**: Plan 对象（包含所有移动操作）

**功能细节**:
- **目标目录结构**（可配置）:
  - 扁平结构: 直接在目标目录下创建类别文件夹
  - 日期结构: 类别/年/月/文件名
  - 自定义结构: 用户定义模板
- **冲突检测**:
  - 目标路径已存在同名文件
  - 文件名非法字符
  - 路径长度超过系统限制
- **冲突解决策略**（可配置）:
  - skip: 跳过，保留原文件
  - rename: 自动重命名（添加序号或时间戳）
  - overwrite: 覆盖（不推荐，需确认）
  - ask: 交互式询问
- **计划预览**:
  - 生成人类可读的操作列表
  - 显示每个操作的源路径和目标路径
  - 显示文件数量和总大小
  - 标记冲突和解决策略

**Plan 数据结构**:
```python
class Plan(BaseModel):
    operations: list[MoveOperation]
    stats: PlanStats
    conflicts: list[Conflict]

class MoveOperation(BaseModel):
    source: Path
    target: Path
    action: str  # move, rename, skip
    reason: str  # 分类结果或冲突说明

class PlanStats(BaseModel):
    total_files: int
    total_size: int
    by_category: dict[str, int]
    api_calls: int
    estimated_cost: float  # 估算成本
```

#### 2.1.5 执行器 (executor.py)

**需求描述**: 执行整理计划，记录操作历史，支持撤销。

**输入**: Plan 对象、确认标志
**输出**: 执行结果

**功能细节**:
- **执行模式**:
  - dry-run: 模拟执行，不实际移动文件（默认）
  - 确认后执行: 显示计划，用户输入 y/n
  - --yes 直接执行: 跳过确认
- **文件操作**:
  - 移动文件（shutil.move）
  - 创建目标目录（自动创建多级目录）
  - 保留原文件元数据（修改时间等）
- **错误处理**:
  - 单个文件操作失败不中断整体流程
  - 记录失败文件和原因
  - 最后汇总报告（成功/失败/跳过统计）
- **审计日志**:
  - 每次操作记录到 ~/.taxo/history.jsonl
  - 记录内容：时间戳、操作类型、源路径、目标路径、文件大小、分类结果、LLM 调用信息
  - 支持按日期/目录/操作类型查询

#### 2.1.6 撤销系统 (history.py + executor.py)

**需求描述**: 精确撤销 taxo 执行过的文件移动操作。

**输入**: 历史记录 ID 或步骤数
**输出**: 撤销结果

**功能细节**:
- **撤销粒度**:
  - `taxo undo`: 撤销最近一次 organize 操作
  - `taxo undo --step 3`: 撤销倒数第 3 次操作
  - `taxo undo --id <uuid>`: 撤销指定 ID 的操作
- **撤销机制**:
  - 读取历史记录中的操作列表
  - 反向执行：将文件从目标路径移回源路径
  - 如果源目录已不存在，自动创建
  - 如果目标位置已有新文件（被覆盖），无法撤销，报错提示
- **撤销记录**:
  - 撤销操作本身也记录到历史日志
  - 防止重复撤销
- **历史查看**:
  - `taxo history`: 显示所有操作历史（Rich 表格）
  - `taxo history --last`: 最近一次详情
  - `taxo history --since 2026-05-01`: 日期范围筛选

#### 2.1.7 文件监控 (watcher.py)

**需求描述**: 可选的后台守护进程，监控目录新文件并自动整理。

**输入**: 监控目录、配置
**输出**: 后台进程

**功能细节**:
- **监控模式**:
  - `taxo watch ~/Downloads`: 前台运行，Ctrl+C 停止
  - `taxo watch ~/Downloads --daemon`: 后台守护进程
  - `taxo watch --stop`: 停止守护进程
- **事件处理**:
  - 监控文件创建事件（watchdog）
  - 防抖处理（debounce）：同一文件 5 秒内多次事件只处理一次
  - 延迟处理：新文件创建后等待 30 秒再整理（避免下载未完成）
- **自动整理**:
  - 新文件触发时自动执行 scan + organize（--yes 模式）
  - 使用与手动整理相同的分类配置
  - 记录到历史日志
- **进程管理**:
  - 守护进程 PID 写入 ~/.taxo/watch.pid
  - 支持查看状态：`taxo watch --status`
  - 日志输出到 ~/.taxo/logs/watch.log

### 2.2 配置系统 (config.py)

#### 2.2.1 配置文件位置
- 主配置: ~/.taxo/config.yaml
- 历史记录: ~/.taxo/history.jsonl
- 日志目录: ~/.taxo/logs/
- PID 文件: ~/.taxo/watch.pid

#### 2.2.2 配置结构

```yaml
# LLM 配置
llm:
  provider: openai  # 或自定义名称
  base_url: https://api.deepseek.com/v1  # 自定义 API 地址
  api_key: sk-xxx  # 通过 CLI 设置，可加密存储
  model: deepseek-chat
  timeout: 30
  max_retries: 3
  
  # 多 provider 支持（备用）
  providers:
    - name: primary
      base_url: https://api.deepseek.com/v1
      api_key: sk-xxx
      model: deepseek-chat
    - name: backup
      base_url: https://api.glm.cn/v1
      api_key: sk-yyy
      model: glm-4

# 分类配置
classify:
  mode: hybrid  # type | semantic | project | hybrid
  content_analysis: false  # 是否读取文件内容（默认关闭）
  batch_size: 30  # LLM 批量分类数量
  max_tokens_per_call: 4000  # 单次调用最大 token
  
  # 分类维度定义（根据 mode 变化）
  categories:
    # hybrid 模式：先按类型大类，文档再细分
    - name: 文档
      subcategories:
        - 财务
        - 报告
        - 合同
        - 个人
        - 工作
    - name: 图片
    - name: 视频
    - name: 代码
    - name: 压缩包
    - name: 安装包

# 规则配置
rules:
  # 内置规则开关
  use_builtin: true
  # 用户自定义规则
  custom:
    - pattern: "ext:.epub"
      category: 电子书
    - pattern: "name:*invoice*"
      category: 发票
    - pattern: "regex:^[0-9]{4}-[0-9]{2}-"
      category: 日期文件
  # 规则优先级：custom > builtin

# 整理配置
organize:
  # 目标目录结构
  structure: flat  # flat | date | custom
  # 日期结构模板（structure=date 时使用）
  date_template: "{category}/{year}/{month}"
  # 冲突解决策略
  conflict_strategy: rename  # skip | rename | overwrite | ask
  # 重命名模板（conflict_strategy=rename 时使用）
  rename_template: "{name}_{timestamp}{ext}"
  # 交互模式
  interactive: true  # true: dry-run + 确认 | false: 直接执行

# 扫描配置
scan:
  # 排除模式
  exclude:
    - ".*"  # 隐藏文件
    - "*.tmp"
    - "*.part"
    - "*.crdownload"
  # 排除目录
  exclude_dirs:
    - ".git"
    - "node_modules"
    - "__pycache__"
  # 最大扫描深度（null 表示无限制）
  max_depth: null
  # 文件大小限制（字节）
  min_size: 0
  max_size: null

# 监控配置
watch:
  enabled: false
  debounce_seconds: 5
  delay_seconds: 30
  log_level: info

# 成本限制
cost:
  # 月度预算（美元）
  monthly_budget: 5.0
  # 单次调用最大成本（美元）
  max_cost_per_call: 0.01
  # 超出预算时行为：warn | block
  over_budget_action: warn
```

#### 2.2.3 配置管理 CLI

```bash
taxo config init                    # 交互式初始化
taxo config show                    # 显示当前配置
taxo config set llm.api_key sk-xxx  # 设置值
taxo config get llm.model           # 获取值
taxo config reset                   # 恢复默认
taxo config edit                    # 打开编辑器编辑 yaml
```

### 2.3 CLI 命令总览

```
taxo --help                           # 显示帮助
taxo --version                        # 显示版本

# 核心命令
taxo scan <path> [options]            # 扫描预览
taxo organize <path> [options]        # 执行整理
taxo undo [options]                   # 撤销操作

# 监控命令
taxo watch <path> [options]             # 文件监控
taxo watch --stop                     # 停止监控
taxo watch --status                   # 查看状态

# 配置命令
taxo config <subcommand>              # 配置管理

# 历史命令
taxo history [options]                # 操作历史

# 规则命令
taxo rules <subcommand>               # 规则管理
```

#### 2.3.1 scan 命令选项

```bash
taxo scan ~/Downloads
  --mode {type,semantic,project,hybrid}  # 分类维度（默认 hybrid）
  --content                               # 读取文件内容分析
  --output {table,json,csv}               # 输出格式（默认 table）
  --save-plan <file>                      # 保存计划到文件
  --max-depth <n>                         # 最大扫描深度
  --exclude <pattern>                     # 额外排除模式
```

#### 2.3.2 organize 命令选项

```bash
taxo organize ~/Downloads
  --mode {type,semantic,project,hybrid}  # 分类维度
  --content                               # 读取文件内容
  --yes                                   # 跳过确认直接执行
  --dry-run                               # 仅预览不执行（默认行为）
  --plan <file>                           # 从文件加载计划执行
  --conflict-strategy {skip,rename,overwrite,ask}
```

#### 2.3.3 undo 命令选项

```bash
taxo undo
  --step <n>              # 撤销倒数第 n 次（默认 1）
  --id <uuid>             # 撤销指定 ID
  --force                 # 强制撤销（不确认）
```

#### 2.3.4 watch 命令选项

```bash
taxo watch ~/Downloads
  --daemon                # 后台守护进程
  --stop                  # 停止守护进程
  --status                # 查看守护进程状态
  --interval <seconds>    # 检查间隔（默认 5）
```

## 3. 非功能需求

### 3.1 性能
- 扫描 1000 个文件 < 1 秒
- 规则匹配 1000 个文件 < 100ms
- LLM 单次调用 < 5 秒（含重试）
- 整体整理 100 个文件 < 10 秒（含 API 调用）

### 3.2 成本
- 规则引擎处理 80%+ 文件，零 API 成本
- LLM 批量处理，单次调用覆盖 30-50 个文件
- 估算：整理 200 个 Downloads 文件，API 成本 < 0.05 元

### 3.3 可靠性
- API 调用失败重试 3 次，不中断整体流程
- 文件操作失败记录原因，继续处理其他文件
- 所有操作可审计、可撤销

### 3.4 安全性
- 默认不读取文件内容
- API 密钥加密存储（或至少权限控制 600）
- 只操作用户指定的目录
- 撤销机制防止误操作

### 3.5 兼容性
- Python 3.11+
- macOS / Linux / Windows
- 支持任何 OpenAI Chat Completions 兼容 API

### 3.6 可维护性
- 模块化设计，每个功能独立模块
- 完整类型注解
- 单元测试覆盖核心逻辑
- 清晰的日志和错误信息

## 4. 数据模型

### 4.1 FileItem
```python
class FileItem(BaseModel):
    path: Path                    # 完整路径
    name: str                   # 文件名（不含扩展名）
    ext: str                    # 扩展名（含 .）
    size: int                   # 文件大小（字节）
    mtime: datetime             # 修改时间
    ctime: datetime             # 创建时间
    is_hidden: bool             # 是否隐藏文件
    is_symlink: bool            # 是否符号链接
    content_hash: str | None    # 内容哈希（可选，用于去重）
```

### 4.2 ClassifyResult
```python
class ClassifyResult(BaseModel):
    file: FileItem
    category: str               # 主类别
    subcategory: str | None     # 子类别
    confidence: float           # 置信度（规则匹配为 1.0，LLM 为 0-1）
    method: str                 # 分类方法：rule | llm
    reason: str                 # 分类理由
```

### 4.3 Plan
```python
class Plan(BaseModel):
    id: str                     # UUID
    timestamp: datetime
    source_dir: Path
    operations: list[MoveOperation]
    stats: PlanStats
    llm_usage: LLMUsage | None

class MoveOperation(BaseModel):
    source: Path
    target: Path
    action: str                 # move | rename | skip
    reason: str
    status: str                 # pending | success | failed | skipped

class PlanStats(BaseModel):
    total_files: int
    total_size: int
    by_category: dict[str, int]
    api_calls: int
    estimated_cost: float
    duration_ms: int

class LLMUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
```

### 4.4 HistoryEntry
```python
class HistoryEntry(BaseModel):
    id: str                     # UUID
    timestamp: datetime
    command: str                # 执行的命令
    plan_id: str                # 关联的计划 ID
    status: str                 # success | partial | failed
    undo_available: bool        # 是否可撤销
    undo_timestamp: datetime | None
```

## 5. 用户流程

### 5.1 首次使用流程

```
1. 安装: pip install taxo
2. 初始化: taxo config init
   - 交互式询问 API 配置
   - 选择分类模式
   - 选择目标目录结构
3. 测试扫描: taxo scan ~/Downloads
   - 查看预览结果
   - 确认分类准确度
4. 执行整理: taxo organize ~/Downloads --yes
   - 或先 dry-run 再确认
5. 查看历史: taxo history
```

### 5.2 日常使用流程

```
1. 手动整理: taxo organize ~/Downloads
2. 发现错误: taxo undo
3. 添加规则: taxo rules add "ext:.epub → 电子书"
4. 自动监控: taxo watch ~/Downloads --daemon
```

### 5.3 异常处理流程

```
API 失败:
  → 自动重试 3 次
  → 仍失败则降级为纯规则模式
  → 提示用户检查网络/API 配置

文件操作失败:
  → 记录失败原因
  → 继续处理其他文件
  → 最后汇总报告

撤销失败:
  → 检查目标位置是否已有新文件
  → 提示用户手动处理
```

## 6. 界面设计

### 6.1 终端输出风格
- 使用 Rich 库美化输出
- 扫描结果：表格形式，显示文件名、大小、分类结果
- 整理计划：diff 风格，显示源路径 → 目标路径
- 进度条：扫描和 API 调用时显示进度
- 颜色编码：
  - 绿色：成功
  - 黄色：警告/跳过
  - 红色：错误
  - 蓝色：信息

### 6.2 输出示例

**scan 输出**:
```
┌─────────────────────────┬────────┬──────────┬─────────────┐
│ File                    │ Size   │ Category │ Method      │
├─────────────────────────┼────────┼──────────┼─────────────┤
│ Q4财务报告.pdf          │ 2.3 MB │ 财务文档 │ llm         │
│ Screenshot 2026-05.png  │ 340 KB │ 截图     │ rule        │
│ node-v20.pkg            │ 45 MB  │ 安装包   │ rule        │
│ project-ideas.md        │ 12 KB  │ 工作     │ llm         │
└─────────────────────────┴────────┴──────────┴─────────────┘

Stats: 4 files, 1 rule-classified, 2 llm-classified, 1 uncategorized
API calls: 1, Estimated cost: $0.003
```

**organize dry-run 输出**:
```
Plan: move 4 files from ~/Downloads to organized folders

~/Downloads/Q4财务报告.pdf → ~/Downloads/财务文档/Q4财务报告.pdf
~/Downloads/Screenshot 2026-05.png → ~/Downloads/截图/Screenshot 2026-05.png
~/Downloads/node-v20.pkg → ~/Downloads/安装包/node-v20.pkg
~/Downloads/project-ideas.md → ~/Downloads/工作/project-ideas.md

Execute? [y/N]: 
```

## 7. 技术实现计划

### 7.1 第一阶段：MVP（2 周）
- [ ] 项目骨架（pyproject.toml、目录结构）
- [ ] 配置系统（config.py）
- [ ] 文件扫描（scanner.py）
- [ ] 规则引擎（rules.py）
- [ ] LLM 客户端（llm.py）
- [ ] 基础 CLI（scan、organize）
- [ ] 测试框架

### 7.2 第二阶段：核心功能（2 周）
- [ ] 整理计划（planner.py）
- [ ] 执行器（executor.py）
- [ ] 撤销系统（history.py）
- [ ] 配置管理 CLI（config）
- [ ] 规则管理 CLI（rules）
- [ ] 历史查看 CLI（history）

### 7.3 第三阶段：增强功能（1 周）
- [ ] 文件监控（watcher.py）
- [ ] Rich 终端输出（display.py）
- [ ] 成本统计
- [ ] 多 provider 支持
- [ ] 完善测试

### 7.4 第四阶段：发布（1 周）
- [ ] README 和文档
- [ ] PyPI 发布
- [ ] Homebrew 公式（可选）

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| LLM 分类不准确 | 高 | 规则引擎兜底、置信度阈值、用户确认 |
| API 成本超预期 | 中 | 预算限制、批量处理、规则优先 |
| 文件误移动/丢失 | 高 | dry-run 默认、撤销系统、审计日志 |
| 大文件/大量文件处理慢 | 中 | 进度条、异步处理、分批处理 |
| 跨平台兼容性 | 中 | pathlib、watchdog、CI 多平台测试 |

## 9. 附录

### 9.1 内置规则集

```yaml
builtin_rules:
  图片:
    exts: [.jpg, .jpeg, .png, .gif, .bmp, .webp, .svg, .ico, .raw, .cr2, .nef, .heic]
  
  文档:
    exts: [.pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx, .odt, .ods, .odp, .txt, .md, .rtf]
  
  电子书:
    exts: [.epub, .mobi, .azw3, .fb2, .djvu]
  
  代码:
    exts: [.py, .js, .ts, .java, .cpp, .c, .h, .go, .rs, .rb, .php, .swift, .kt, .scala, .sh, .bash, .zsh]
  
  数据:
    exts: [.json, .xml, .yaml, .yml, .csv, .tsv, .sql, .db, .sqlite, .parquet]
  
  压缩包:
    exts: [.zip, .rar, .7z, .tar, .gz, .bz2, .xz, .dmg, .iso]
  
  安装包:
    exts: [.exe, .msi, .pkg, .deb, .rpm, .appimage, .dmg]
    patterns: ["*setup*", "*install*"]
  
  视频:
    exts: [.mp4, .avi, .mkv, .mov, .wmv, .flv, .webm, .m4v, .mpg, .mpeg, .mts, .m2ts]
  
  音频:
    exts: [.mp3, .wav, .flac, .aac, .ogg, .m4a, .wma, .opus, .aiff, .m4p]
  
  字体:
    exts: [.ttf, .otf, .woff, .woff2, .eot]
  
  设计:
    exts: [.psd, .ai, .sketch, .fig, .xd, .afdesign, .afphoto, .afpub]
```

### 9.2 分类维度模板

**type 模式**:
```
图片 / 文档 / 电子书 / 代码 / 数据 / 压缩包 / 安装包 / 视频 / 音频 / 字体 / 设计 / 未分类
```

**semantic 模式**:
```
财务 / 报告 / 合同 / 发票 / 个人 / 工作 / 学习 / 娱乐 / 截图 / 备份 / 临时 / 未分类
```

**project 模式**:
```
由 LLM 根据文件名推断项目名，如：
- "order-system-api.md" → order-system
- "客服培训.pptx" → 客服系统
- "Q4财务报告.pdf" → 财务部门
```

**hybrid 模式**（默认）:
```
先按 type 分大类，文档类再按 semantic 细分：
文档/财务 / 文档/报告 / 文档/合同 / 文档/个人 / 文档/工作
图片 / 视频 / 代码 / ...
```

### 9.3 术语表

| 术语 | 定义 |
|------|------|
| Rule | 基于扩展名或文件名模式的分类规则 |
| LLM | 大语言模型，用于语义分类 |
| Batch | LLM 批量处理的文件组（默认 30-50 个） |
| Plan | 整理计划，包含所有文件移动操作 |
| Dry-run | 预览模式，不实际移动文件 |
| Undo | 撤销操作，将文件移回原位置 |
| Watch | 文件系统监控，自动整理新文件 |
| Provider | LLM API 提供商配置 |
