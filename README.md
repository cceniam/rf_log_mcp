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

通用返回字段：

- `run_id`：整数运行编号，推荐后续调用都使用它
- `estimated_tokens`：当前返回体的估算 token 数
- `truncated`：兼容字段，只表示返回内容发生过任意截断
- `message_truncated`：长消息被缩短
- `budget_truncated`：为了满足 `budget` 限制裁剪了返回内容
- `page_truncated`：当前页后面还有更多数据
- `next_cursor`：分页游标；为空表示没有下一页

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

如果失败用例较多，可以指定分页大小：

```text
get_view(run_id=1, view="summary", page_size=10)
get_view(run_id=1, view="summary", cursor="<next_cursor>", page_size=10)
```

### 第三步：获取失败路径

```text
get_view(run_id=1, view="failure_path")
get_view(run_id=1, view="failure_path", selector="s1-t2")
```

`failure_path` 会从失败测试中选择更短、更关键的失败分支；当同层分支长度相同，会优先返回包含更高严重级别消息的分支。

### 第四步：查看步骤窗口

```text
get_view(run_id=1, view="step_window", selector="s1-t2")
```

`step_window` 的 `selector` 可以传测试节点，也可以传关键字/步骤节点。传步骤节点时，返回会自动定位到所属测试，并尽量把该节点放在窗口中间。

分页示例：

```text
get_view(run_id=1, view="step_window", selector="s1-t2-k13", page_size=20)
get_view(run_id=1, view="step_window", selector="s1-t2-k13", cursor="<next_cursor>", page_size=20)
```

### 第五步：检索消息

```text
search_messages(run_id=1, query="timeout")
```

`search_messages` 按普通文本匹配。`%`、`_`、`\` 会作为字面量处理，不会被当成 SQL LIKE 通配符。

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

### 2. `truncated` 和三个细分字段有什么区别？

`truncated` 是总开关，任意一种截断都会为 `true`。

- `message_truncated=true`：消息字段太长，被缩短显示
- `budget_truncated=true`：返回体超过 `budget`，服务主动裁剪了条目或消息
- `page_truncated=true`：还有下一页，应继续传 `next_cursor`

排查失败链时优先关注 `budget_truncated`。如果它为 `true`，可以调大 `budget` 或缩小 `page_size` 后重新查询。

### 3. `get_view` / `search_messages` 能传文件路径吗？

可以。  
如果该文件已经被解析过，服务会先把路径转换成对应的 `run_id` 再查询。  
但仍然推荐优先使用 `parse_result()` 返回的整数 `run_id`。

### 4. Windows 上推荐用哪种启动方式？

开发临时验证可以使用：

```bash
uv run python -m rf_log_mcp
```

接入 MCP 宿主时，更推荐使用虚拟环境里的解释器直接启动，减少 `uv` 或 `.exe` 启动器额外进程带来的文件占用问题：

```json
{
  "mcpServers": {
    "rf-log-mcp": {
      "command": "D:\\project\\rf_log_mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "rf_log_mcp"
      ]
    }
  }
}
```

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
