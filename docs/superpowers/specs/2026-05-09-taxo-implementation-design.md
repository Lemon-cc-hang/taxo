# Taxo 实现设计文档

> 日期: 2026-05-09
> 状态: Draft

## Context

Taxo 是一个 AI 驱动的 CLI 文件分类工具，通过规则引擎 + LLM 混合策略自动整理 Downloads 文件夹。项目从零开始，需要分阶段实现。本文档覆盖完整实现设计，分为 4 个阶段渐进交付。

## 关键决策

- **Python 环境**: mise + venv 管理
- **默认 LLM Provider**: DeepSeek（可配置切换）
- **目标目录**: 支持原地整理和移动到新目录两种模式
- **实现方式**: 4 阶段，每阶段独立可测

---

## 阶段 1: 基础骨架 + 数据层

### 项目结构

```
taxo/
├── pyproject.toml           # uv 项目配置
├── src/taxo/
│   ├── __init__.py          # 版本号 (__version__)
│   ├── models.py            # Pydantic 数据模型
│   ├── config.py            # 配置管理
│   └── scanner.py           # 文件扫描
├── tests/
│   ├── conftest.py          # 测试 fixtures（临时目录、示例文件）
│   ├── test_models.py
│   ├── test_config.py
│   └── test_scanner.py
└── docs/
```

### models.py — 数据模型

```python
class FileItem(BaseModel):
    path: Path                    # 完整路径
    name: str                     # 文件名（不含扩展名）
    ext: str                      # 扩展名（含 .，小写）
    size: int                     # 字节
    mtime: datetime               # 修改时间
    ctime: datetime               # 创建时间
    is_hidden: bool               # 是否隐藏文件
    is_symlink: bool              # 是否符号链接

class ClassifyResult(BaseModel):
    file: FileItem
    category: str                 # 主类别
    subcategory: str | None       # 子类别
    confidence: float             # 置信度（规则 1.0，LLM 0-1）
    method: Literal["rule", "llm"]
    reason: str

class MoveOperation(BaseModel):
    source: Path
    target: Path
    action: Literal["move", "rename", "skip"]
    reason: str
    status: Literal["pending", "success", "failed", "skipped"] = "pending"

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

class Plan(BaseModel):
    id: str                       # UUID
    timestamp: datetime
    source_dir: Path
    operations: list[MoveOperation]
    stats: PlanStats
    llm_usage: LLMUsage | None = None

class HistoryEntry(BaseModel):
    id: str                       # UUID
    timestamp: datetime
    command: str
    plan_id: str
    status: Literal["success", "partial", "failed"]
    operations: list[MoveOperation]
    undo_available: bool = True
    undo_timestamp: datetime | None = None
```

### config.py — 配置管理

**配置文件**: `~/.taxo/config.yaml`

```python
class LLMProviderConfig(BaseModel):
    name: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout: int = 30
    max_retries: int = 3

class LLMConfig(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout: int = 30
    max_retries: int = 3
    providers: list[LLMProviderConfig] = []

class ClassifyConfig(BaseModel):
    mode: Literal["type", "semantic", "project", "hybrid"] = "hybrid"
    content_analysis: bool = False
    batch_size: int = 30
    max_tokens_per_call: int = 4000
    categories: list[dict] = []  # 自定义分类维度

class RuleConfig(BaseModel):
    use_builtin: bool = True
    custom: list[dict] = []      # [{pattern: str, category: str}]

class OrganizeConfig(BaseModel):
    target_dir: str | None = None  # None = 原地整理
    structure: Literal["flat", "date", "custom"] = "flat"
    date_template: str = "{category}/{year}/{month}"
    conflict_strategy: Literal["skip", "rename", "overwrite", "ask"] = "rename"
    rename_template: str = "{name}_{timestamp}{ext}"

class ScanConfig(BaseModel):
    exclude: list[str] = [".*", "*.tmp", "*.part", "*.crdownload"]
    exclude_dirs: list[str] = [".git", "node_modules", "__pycache__"]
    max_depth: int | None = None
    min_size: int = 0
    max_size: int | None = None

class WatchConfig(BaseModel):
    debounce_seconds: int = 5
    delay_seconds: int = 30

class CostConfig(BaseModel):
    monthly_budget: float = 5.0
    max_cost_per_call: float = 0.01
    over_budget_action: Literal["warn", "block"] = "warn"

class TaxoConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    classify: ClassifyConfig = ClassifyConfig()
    rules: RuleConfig = RuleConfig()
    organize: OrganizeConfig = OrganizeConfig()
    scan: ScanConfig = ScanConfig()
    watch: WatchConfig = WatchConfig()
    cost: CostConfig = CostConfig()
```

**核心函数**:
- `load_config() → TaxoConfig` — 从 YAML 加载，不存在则返回默认
- `save_config(config: TaxoConfig)` — 保存到 YAML
- `get_default_config() → TaxoConfig` — 返回默认配置
- 环境变量覆盖：`TAXO_LLM_API_KEY`, `TAXO_LLM_BASE_URL`, `TAXO_LLM_MODEL`

### scanner.py — 文件扫描

**核心函数**: `scan_files(directory: Path, config: ScanConfig) → list[FileItem]`

逻辑：
1. 校验目录存在性
2. 递归遍历目录树（`os.scandir` + 递归）
3. 对每个文件：
   - 跳过符号链接
   - 跳过隐藏文件（以 . 开头，可配置）
   - 跳过系统文件（.DS_Store, Thumbs.db 等）
   - 跳过排除模式匹配的文件
   - 检查 max_depth / min_size / max_size
   - 收集元数据：name, ext（小写）, size, mtime, ctime
   - macOS NFD normalize 文件名
4. 返回 `list[FileItem]`

---

## 阶段 2: 分类引擎

### rules.py — 规则引擎

**内置规则**: 11 个类别，每个映射一组扩展名（PRD 9.1 节完整列表）

**Rule 模型**:
```python
class Rule(BaseModel):
    pattern_type: Literal["ext", "pattern", "regex", "compound"]
    pattern: str
    category: str
```

**RuleEngine 类**:
- `__init__(config: RuleConfig)`
- `load_builtin_rules() → dict[str, list[str]]` — 加载内置扩展名映射
- `load_custom_rules(custom: list[dict]) → list[Rule]` — 解析用户自定义规则
- `match(file: FileItem) → str | None` — 单文件匹配，返回类别或 None
- `classify(files: list[FileItem]) → tuple[dict[str, list[FileItem]], list[FileItem]]`
  - 返回 (matched_results, unmatched_files)
  - 自定义规则优先于内置规则
  - 第一个匹配的规则生效

**规则解析**:
- `ext:.epub` → Rule(pattern_type="ext", pattern=".epub", category="电子书")
- `pattern:*invoice*` → Rule(pattern_type="pattern", pattern="*invoice*")
- `regex:^[0-9]{4}-[0-9]{2}-` → Rule(pattern_type="regex", pattern="...")
- `ext:.pdf AND pattern:*report*` → Rule(pattern_type="compound", ...)

### llm.py — LLM 客户端

**LLMClient 类**:
- `__init__(config: LLMConfig)`
- `classify_batch(files: list[FileItem], categories: list[str], mode: str) → dict[str, list[str]]`
  - 构建 system prompt（包含分类维度定义和输出格式）
  - 构建 user prompt（文件列表 JSON）
  - 调用 OpenAI Chat Completions API
  - 解析 JSON 响应 → {category: [filenames]}
  - 解析失败标记为 "未分类"

**内部方法**:
- `_build_system_prompt(categories, mode) → str`
- `_build_user_prompt(files) → str`
- `_call_api(messages) → str` — httpx POST 请求
- `_parse_response(raw: str) → dict[str, list[str]]` — JSON 解析

**错误处理**:
- httpx.TimeoutException → 重试
- httpx.ConnectError → 抛出 LLMUnavailableError
- JSON 解析失败 → 返回空分类，记录 raw response
- 重试 3 次，指数退避 (1s, 2s, 4s)

### classifier.py — 分类协调器

**Classifier 类**:
- `__init__(config: TaxoConfig)` — 初始化 RuleEngine 和 LLMClient
- `classify(files: list[FileItem]) → list[ClassifyResult]`

**流程**:
1. `rule_engine.classify(files)` → (matched, unmatched)
2. matched → `ClassifyResult(method="rule", confidence=1.0)`
3. 如果 unmatched 非空：
   - 按 `batch_size` 分批
   - 每批调用 `llm_client.classify_batch()`
   - 结果 → `ClassifyResult(method="llm", confidence=0.8)`
4. LLMUnavailableError → 自动降级，unmatched 全部标记 "未分类"
5. 合并返回完整结果列表

**分类模式**:
- `type`: 只按文件类型分（图片/文档/代码等）
- `semantic`: 所有文件送 LLM，按内容主题分
- `project`: LLM 推断项目名
- `hybrid`（默认）: 规则按类型分，文档类再送 LLM 按语义细分

---

## 阶段 3: 执行与历史

### planner.py — 整理计划

**Planner 类**:
- `create_plan(results: list[ClassifyResult], source_dir: Path, target_dir: Path | None, config: OrganizeConfig) → Plan`

**逻辑**:
1. 确定目标根目录：`target_dir or source_dir`
2. 按 structure 模式生成目标路径：
   - `flat`: `{target_root}/{category}/{filename}`
   - `date`: `{target_root}/{category}/{year}/{month}/{filename}`
3. 冲突检测：目标路径已存在 → 按 conflict_strategy 处理
   - `skip`: 标记 action="skip"
   - `rename`: 添加序号或时间戳
   - `overwrite`: 标记 action="move"（危险）
   - `ask`: 收集冲突列表等待交互处理
4. 生成 Plan 对象（含 UUID、时间戳、统计信息）

### executor.py — 执行器

**Executor 类**:
- `__init__(history_manager: HistoryManager)`
- `execute(plan: Plan, dry_run: bool = True) → ExecuteResult`

**逻辑**:
- `dry_run=True`: 打印所有 MoveOperation，不实际操作
- `dry_run=False`:
  1. 遍历 operations
  2. 对每个 operation：创建目标目录 → `shutil.move(source, target)`
  3. 单个失败记录原因，继续处理
  4. 全部完成后记录到 history
  5. 返回 ExecuteResult（成功/失败/跳过统计 + 失败详情）

**ExecuteResult**:
```python
class ExecuteResult(BaseModel):
    plan_id: str
    total: int
    success: int
    failed: int
    skipped: int
    errors: list[str]
```

### history.py — 历史记录

**存储**: `~/.taxo/history.jsonl`，每行一条 JSON

**HistoryManager 类**:
- `record(entry: HistoryEntry)` — 追加一行 JSONL
- `list_entries(limit: int = 20, since: datetime | None = None) → list[HistoryEntry]`
- `get_last() → HistoryEntry | None`
- `get_by_id(id: str) → HistoryEntry | None`
- `undo(step: int = 1) → ExecuteResult` — 反向执行最近第 step 次操作
  - 检查 undo_available 标志
  - 检查目标位置是否被覆盖
  - 反向移动（target → source）
  - 更新原记录的 undo_timestamp
  - 记录撤销操作到历史

---

## 阶段 4: CLI + 增强

### cli.py — Click CLI 入口

**命令结构**:
```
taxo
├── scan <path>              # 扫描预览
│   ├── --mode               # type|semantic|project|hybrid
│   ├── --content            # 读取内容
│   ├── --output             # table|json|csv
│   └── --max-depth
├── organize <path>          # 执行整理
│   ├── --mode
│   ├── --content
│   ├── --yes                # 跳过确认
│   ├── --dry-run
│   ├── --target             # 目标目录
│   └── --conflict-strategy
├── undo                     # 撤销
│   ├── --step
│   ├── --id
│   └── --force
├── history                  # 操作历史
│   ├── --last
│   └── --since
├── config                   # 配置管理
│   ├── init
│   ├── show
│   ├── set <key> <value>
│   ├── get <key>
│   ├── reset
│   └── edit
├── rules                    # 规则管理
│   ├── list
│   ├── add <rule>
│   └── remove <index>
└── watch <path>             # 文件监控
    ├── --daemon
    ├── --stop
    └── --status
```

### display.py — Rich 终端输出

**函数列表**:
- `print_scan_table(results)` — Rich Table，列：文件名/大小/分类/方法
- `print_plan_preview(plan)` — diff 风格，`source → target`
- `print_execute_result(result)` — 成功/失败/跳过统计
- `print_history(entries)` — Rich Table，时间/命令/状态/可撤销
- `print_config(config)` — YAML 格式化输出
- `print_rules(rules)` — 规则表格
- 颜色：绿=成功，黄=警告/跳过，红=错误，蓝=信息

### watcher.py — 文件监控

**基于 watchdog**:
- `FileEventHandler(watchdog.FileSystemEventHandler)`:
  - `on_created(event)` — 收集文件创建事件
  - debounce 5 秒内同一文件只处理一次
  - 延迟 30 秒后执行整理（确保下载完成）
- 前台模式：`taxo watch ~/Downloads`，Ctrl+C 停止
- 后台模式：`taxo watch ~/Downloads --daemon`
  - fork 子进程
  - PID 写入 `~/.taxo/watch.pid`
  - 日志输出到 `~/.taxo/logs/watch.log`
- `taxo watch --stop` — 读 PID，发送 SIGTERM
- `taxo watch --status` — 检查 PID 是否存活

---

## 依赖清单

```toml
[project]
name = "taxo"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "click>=8.1",
    "pydantic>=2.0",
    "httpx>=0.27",
    "rich>=13.0",
    "pyyaml>=6.0",
    "watchdog>=4.0",
]

[project.optional-dependencies]
content = [
    "pdfplumber>=0.10",
    "python-docx>=1.0",
]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.scripts]
taxo = "taxo.cli:cli"
```

---

## 验证计划

### 阶段 1 验证
- `uv run pytest tests/ -v` — models, config, scanner 单测全过
- `python -c "from taxo.models import FileItem; print('OK')"` — import 测试
- `python -c "from taxo.config import load_config; print(load_config())"` — 默认配置生成

### 阶段 2 验证
- 规则引擎单测：覆盖内置规则匹配、自定义规则、未匹配场景
- LLM 客户端单测：mock httpx，验证 prompt 构建、响应解析、重试逻辑
- 分类协调器单测：mock LLM，验证规则优先 → LLM 兜底流程、降级场景

### 阶段 3 验证
- Planner 单测：验证路径生成、冲突检测、rename 策略
- Executor 单测：使用 tmp_path，验证文件移动、dry-run 模式、错误处理
- History 单测：验证 JSONL 读写、撤销逻辑、重复撤销防护

### 阶段 4 验证
- CLI 集成测试：`click.testing.CliRunner`，验证各命令输入输出
- 端到端测试：创建临时目录 + 示例文件 → `taxo scan` → `taxo organize` → `taxo undo`
- 手动验证：`taxo scan ~/Downloads` 查看实际输出效果
