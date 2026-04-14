# rf-log-mcp

用于检查 Robot Framework 结果文件的 MCP Server，面向 LLM 提供简洁证据视图。

## 功能概览

支持输入：

- `output.xml`：Robot / Rebot 6.1.1
- `output.json`：Robot / Rebot 7.2+

暴露的 MCP 能力：

- Tools
  - `parse_result`
  - `get_view`
  - `search_messages`
- Resources
  - `rf://runs/{run_id}/summary`
  - `rf://runs/{run_id}/tests/{test_id}`

支持的视图：

- `summary`
- `failure_path`
- `step_window`

## 关键说明

- 这个项目是 **MCP stdio server**
- **LLM 不会直接调用 wheel**
- 正确方式是：MCP 宿主启动 `rf-log-mcp` 进程，再通过 stdio 调用工具和资源

## 标识设计

- 对外 `run_id`：**整数主键**
- 对内 `content_hash`：**文件内容哈希，仅用于服务内部去重**

推荐做法：

1. 先调用 `parse_result(path)`
2. 保存返回的整数 `run_id`
3. 后续统一使用这个 `run_id`

---

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 直接从源码启动

```bash
uv run python -m rf_log_mcp
```

### 3. MCP 配置示例

```json
{
  "mcpServers": {
    "rf-log-mcp": {
      "command": "uv",
      "args": ["run", "python", "-m", "rf_log_mcp"]
    }
  }
}
```

---

## 打包与安装

### 构建

```bash
uv build
```

构建后生成：

- `dist/rf_log_mcp-0.1.0-py3-none-any.whl`
- `dist/rf_log_mcp-0.1.0.tar.gz`

### 安装 wheel

```bash
uv pip install dist/rf_log_mcp-0.1.0-py3-none-any.whl
```

安装后可直接启动：

```bash
rf-log-mcp
```

### 已安装包的 MCP 配置示例

```json
{
  "mcpServers": {
    "rf-log-mcp": {
      "command": "rf-log-mcp",
      "args": []
    }
  }
}
```

### Windows 显式路径示例

```json
{
  "mcpServers": {
    "rf-log-mcp": {
      "command": "D:\\project\\rf_log_mcp\\.venv\\Scripts\\rf-log-mcp.exe",
      "args": []
    }
  }
}
```

---

## 典型调用流程

### 第一步：解析结果文件

```text
parse_result(path="tests/fixtures/single_failure_611.xml")
```

典型返回：

```json
{
  "ok": true,
  "run_id": 1,
  "source_format": "xml"
}
```

### 第二步：获取摘要

```text
get_view(run_id=1, view="summary")
```

### 第三步：获取失败路径或检索消息

```text
get_view(run_id=1, view="failure_path")
search_messages(run_id=1, query="timeout")
```

---

## 环境变量

### `RF_LOG_MCP_DB`

用于覆盖默认 SQLite 数据库路径。

PowerShell 示例：

```powershell
$env:RF_LOG_MCP_DB="D:\data\rf-log-mcp\store.sqlite3"
rf-log-mcp
```

MCP 配置示例：

```json
{
  "mcpServers": {
    "rf-log-mcp": {
      "command": "rf-log-mcp",
      "args": [],
      "env": {
        "RF_LOG_MCP_DB": "D:\\data\\rf-log-mcp\\store.sqlite3"
      }
    }
  }
}
```

---

## 本地调试

如果只想检查服务输出，不想启动 stdio 传输，可使用：

```bash
uv run python debug_service.py --fixture tests/fixtures/single_failure_611.xml --action summary
uv run python debug_service.py --fixture tests/fixtures/single_failure_72.json --action failure_path --selector s1-t2
uv run python debug_service.py --fixture tests/fixtures/errors_and_long_72.json --action search --query "collected line" --limit 2
```

---

## 常见问题

### 1. 为什么不能把 wheel 直接给 LLM？

因为 LLM 调用的是 **MCP server 进程**，不是 Python 包文件本身。

### 2. 为什么推荐用整数 `run_id`？

因为它更短，更适合 LLM、多轮对话和人工排查；长 hash 仅保留在内部用于去重。

### 3. `get_view` / `search_messages` 能传文件路径吗？

可以。  
如果该文件已经被解析过，服务会先把路径转换成对应的 `run_id` 再查询。  
但仍然推荐优先使用 `parse_result()` 返回的整数 `run_id`。

### 4. 什么情况下不能直接使用这个项目？

如果你的 LLM 平台：

- 不支持 MCP
- 或不支持启动本地进程

那就不能直接接入，需要额外做一层集成。

---

## 开发检查

```bash
uv run ruff check .
uv run pytest
```
