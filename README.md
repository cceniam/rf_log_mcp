# rf-log-mcp

用于检查 Robot Framework 结果文件的 MCP Server，面向 LLM 提供简洁证据视图。

## 功能概览

支持输入：

- `output.xml`：Robot / Rebot 6.0.x / 6.1+ / 7.x
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
- 正确方式是：MCP 宿主启动 `rf-log-mcp` 进程，再通过 stdio 调用工具和资源

---

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 推荐的 MCP 配置示例

```json
{
  "mcpServers": {
    "rf-log-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "rf_log_mcp"
      ]
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

## 常见问题

### 1. 为什么使用uv 

1. 本地环境的依赖版本可能和 mcp的冲突, 需要venv 来隔离依赖冲突(conda 太慢, uv快)

### 2. `get_view` / `search_messages` 能传文件路径吗？

可以。  
如果该文件已经被解析过，服务会先把路径转换成对应的 `run_id` 再查询。  
但仍然推荐优先使用 `parse_result()` 返回的整数 `run_id`。

### 5. 什么情况下不能直接使用这个项目？

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
