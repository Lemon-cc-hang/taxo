# Taxo

AI 驱动的 CLI 文件分类工具。用最低的 API 成本，智能整理你的 Downloads 文件夹。

## 特性

- **三层分类引擎** — 规则层（零成本）→ AI 层（按需付费）→ 用户层（确认/撤销）
- **规则优先** — 内置 11 类文件扩展名规则，80%+ 文件零 API 调用
- **批量 LLM 分类** — 未匹配文件批量发给 AI 语义分类，30-50 个文件一次调用
- **支持任意 OpenAI 兼容 API** — DeepSeek、GLM、Claude、Ollama 等
- **安全可逆** — 默认 dry-run 预览，所有操作可撤销，完整审计日志
- **跨平台** — macOS / Linux / Windows

## 快速开始

### 安装

```bash
# 从源码安装（需要 Python 3.11+）
git clone https://github.com/diaohang/taxo.git
cd taxo
uv sync --extra dev
uv pip install -e .
```

### 初始化

```bash
# 设置 API Key（必填）
taxo config set llm.api_key sk-your-api-key

# 使用其他 Provider
taxo config set llm.base_url https://api.openai.com/v1
taxo config set llm.model gpt-4o-mini
```

### 使用

```bash
# 扫描预览（不移动文件）
taxo scan ~/Downloads

# 执行整理（先预览，确认后执行）
taxo organize ~/Downloads

# 直接执行
taxo organize ~/Downloads --yes

# 撤销上次操作
taxo undo --force

# 查看操作历史
taxo history
```

## 分类模式

| 模式 | 说明 | API 调用量 |
|------|------|-----------|
| `hybrid` | 规则按类型分，文档类再按语义细分（默认） | 中 |
| `type` | 纯按文件类型分（图片/文档/视频等） | 无（纯规则） |
| `semantic` | 所有文件走 AI 语义分类（财务/工作/个人等） | 高 |
| `project` | AI 推断文件所属项目 | 高 |

```bash
# 切换模式
taxo config set classify.mode semantic

# 单次使用
taxo scan ~/Downloads --mode semantic
```

## 内置规则

11 个类别，覆盖常见文件类型：

| 类别 | 扩展名 |
|------|--------|
| 图片 | .jpg .png .gif .bmp .webp .svg .heic ... |
| 文档 | .pdf .doc .docx .xls .xlsx .ppt .pptx .txt .md ... |
| 电子书 | .epub .mobi .azw3 .fb2 .djvu |
| 代码 | .py .js .ts .java .cpp .go .rs .rb ... |
| 数据 | .json .xml .yaml .csv .sql .sqlite ... |
| 压缩包 | .zip .rar .7z .tar .gz .dmg .iso |
| 安装包 | .exe .msi .pkg .deb .rpm |
| 视频 | .mp4 .avi .mkv .mov .webm ... |
| 音频 | .mp3 .wav .flac .aac .ogg ... |
| 字体 | .ttf .otf .woff .woff2 |
| 设计 | .psd .ai .sketch .fig .xd ... |

规则匹配不上的文件会发送给 LLM 进行语义分类。

## 自定义规则

```bash
# 查看当前规则
taxo rules list

# 按扩展名
taxo rules add "ext:.epub" "电子书"

# 按文件名模式
taxo rules add "pattern:*invoice*" "发票"

# 按正则
taxo rules add "regex:^[0-9]{4}-[0-9]{2}-" "日期文件"

# 组合条件
taxo rules add "ext:.pdf AND pattern:*report*" "报告"
```

## 配置

```bash
taxo config show              # 查看当前配置
taxo config set key value     # 设置配置
taxo config get key            # 获取配置
taxo config reset              # 恢复默认
```

配置文件位于 `~/.taxo/config.yaml`，参考 [config.example.yaml](config.example.yaml)。

也支持环境变量覆盖：

```bash
export TAXO_LLM_API_KEY=sk-xxx
export TAXO_LLM_BASE_URL=https://api.openai.com/v1
export TAXO_LLM_MODEL=gpt-4o-mini
```

## CLI 命令

```
taxo scan <path>              # 扫描预览
  --mode                      # 分类模式
  --output table|json         # 输出格式
  --max-depth                 # 最大扫描深度

taxo organize <path>          # 执行整理
  --yes                       # 跳过确认
  --target <dir>              # 目标目录
  --mode                      # 分类模式
  --conflict-strategy         # 冲突策略

taxo undo                     # 撤销操作
  --step                      # 撤销倒数第 N 次
  --force                     # 跳过确认

taxo history                  # 操作历史
  --last                      # 最近一次
  --since YYYY-MM-DD          # 日期筛选

taxo config <subcommand>      # 配置管理
taxo rules <subcommand>       # 规则管理
```

## 开发

```bash
# 安装开发依赖
uv sync --extra dev

# 运行测试
uv run pytest tests/ -v

# 代码检查
uv run ruff check src/taxo/

# 构建二进制
uv run pyinstaller --onefile --name taxo --clean \
  --collect-all taxo --paths src/ src/taxo/cli.py
```

## 成本估算

以 DeepSeek API 为例，整理 200 个 Downloads 文件：

- 规则引擎处理 ~160 个文件：**$0**
- LLM 批量处理 ~40 个文件：**< $0.01**

## License

MIT
