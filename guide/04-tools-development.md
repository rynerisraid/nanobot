# Nanobot Agent 开发指南 - 第4章：工具系统开发

## 4.1 工具基础架构

### Tool 基类

所有工具都继承自 [`Tool`](../nanobot/agent/tools/base.py:7) 抽象基类：

```python
class Tool(ABC):
    """agent 工具的抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """函数调用中使用的工具名称。"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能的描述。"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """工具参数的 JSON Schema。"""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """使用给定参数执行工具。"""
        pass
```

### 参数验证

工具基类内置 JSON Schema 验证：

```python
def validate_params(self, params: dict[str, Any]) -> list[str]:
    """根据 JSON Schema 验证工具参数。返回错误列表（空表示有效）。"""
    if not isinstance(params, dict):
        return [f"parameters must be an object, got {type(params).__name__}"]

    schema = self.parameters or {}
    if schema.get("type", "object") != "object":
        raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")

    return self._validate(params, {**schema, "type": "object"}, "")
```

### Schema 转换

```python
def to_schema(self) -> dict[str, Any]:
    """转换为 OpenAI 函数 schema 格式。"""
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        },
    }
```

## 4.2 内置工具详解

### 文件系统工具

#### ReadFileTool

```python
class ReadFileTool(Tool):
    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "读取文件内容"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对或绝对）"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从0开始）"
                },
                "limit": {
                    "type": "integer",
                    "description": "读取行数"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, offset: int = 0, limit: int = 0) -> str:
        # 路径解析和安全检查
        full_path = self._resolve_path(path)
        if not self._is_allowed(full_path):
            return "Error: Path outside workspace"

        # 读取文件
        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            if offset or limit:
                lines = lines[offset:offset + limit] if limit else lines[offset:]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"
```

#### WriteFileTool

```python
class WriteFileTool(Tool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "写入内容到文件"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str) -> str:
        full_path = self._resolve_path(path)
        if not self._is_allowed(full_path):
            return "Error: Path outside workspace"

        try:
            full_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {full_path}"
        except Exception as e:
            return f"Error: {e}"
```

#### EditFileTool

```python
class EditFileTool(Tool):
    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "执行精确字符串替换编辑文件"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"}
            },
            "required": ["path", "old_string", "new_string"]
        }

    async def execute(self, path: str, old_string: str, new_string: str) -> str:
        full_path = self._resolve_path(path)
        if not self._is_allowed(full_path):
            return "Error: Path outside workspace"

        try:
            content = full_path.read_text(encoding="utf-8")
            if old_string not in content:
                return f"Error: old_string not found in file"
            new_content = content.replace(old_string, new_string, 1)
            full_path.write_text(new_content, encoding="utf-8")
            return f"Successfully edited {full_path}"
        except Exception as e:
            return f"Error: {e}"
```

### Shell 工具

```python
class ExecTool(Tool):
    def __init__(
        self,
        working_dir: str,
        timeout: int = 30,
        restrict_to_workspace: bool = False,
        path_append: list[str] | None = None,
    ):
        self.working_dir = working_dir
        self.timeout = timeout
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append or []

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "执行 shell 命令"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                }
            },
            "required": ["command"]
        }

    async def execute(self, command: str) -> str:
        # 危险命令检查
        if self._is_dangerous(command):
            return "Error: Command not allowed for security reasons"

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
            output = stdout.decode() + stderr.decode()
            return output or f"Command exited with code {proc.returncode}"
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: Command timed out after {self.timeout}s"
        except Exception as e:
            return f"Error: {e}"

    def _is_dangerous(self, command: str) -> bool:
        dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/", "curl | bash"]
        return any(d in command for d in dangerous)
```

### Web 工具

```python
class WebSearchTool(Tool):
    def __init__(self, api_key: str | None = None, proxy: str | None = None):
        self.api_key = api_key
        self.proxy = proxy

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "使用 Brave Search API 进行网络搜索"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }

    async def execute(self, query: str, count: int = 5) -> str:
        if not self.api_key:
            return "Error: Brave API key not configured"

        import aiohttp

        url = "https://api.search.brave.com/res/v1/web/search"
        params = {"q": query, "count": count}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers={"X-Subscription-Token": self.api_key},
                ) as resp:
                    data = await resp.json()
                    results = data.get("web", {}).get("results", [])
                    return "\n\n".join([
                        f"{r.get('title')}\n{r.get('url')}\n{r.get('description')}"
                        for r in results
                    ])
        except Exception as e:
            return f"Error: {e}"


class WebFetchTool(Tool):
    def __init__(self, proxy: str | None = None):
        self.proxy = proxy

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "获取网页内容"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"}
            },
            "required": ["url"]
        }

    async def execute(self, url: str) -> str:
        import aiohttp
        from bs4 import BeautifulSoup

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    # 移除脚本和样式
                    for tag in soup(["script", "style"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n", strip=True)
                    return text[:10000]  # 限制长度
        except Exception as e:
            return f"Error: {e}"
```

## 4.3 自定义工具开发

### 完整示例：数据库查询工具

```python
"""数据库查询工具示例。"""

import sqlite3
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class DatabaseQueryTool(Tool):
    """SQLite 数据库查询工具。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @property
    def name(self) -> str:
        return "db_query"

    @property
    def description(self) -> str:
        return "执行只读 SQL 查询并返回结果"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT 查询语句"
                },
                "limit": {
                    "type": "integer",
                    "description": "最大返回行数",
                    "default": 100
                }
            },
            "required": ["query"]
        }

    def _is_safe_query(self, query: str) -> bool:
        """检查查询是否安全（只读）。"""
        query_upper = query.strip().upper()
        dangerous_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE"]
        return not any(kw in query_upper for kw in dangerous_keywords)

    async def execute(self, query: str, limit: int = 100) -> str:
        """执行 SQL 查询。"""
        if not self._is_safe_query(query):
            return "Error: Only SELECT queries are allowed"

        if not self.db_path.exists():
            return f"Error: Database file not found: {self.db_path}"

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 添加 LIMIT
            if "LIMIT" not in query.upper():
                query += f" LIMIT {limit}"

            cursor.execute(query)
            rows = cursor.fetchall()

            if not rows:
                return "Query returned no results"

            # 格式化结果
            columns = [desc[0] for desc in cursor.description]
            result = [" | ".join(columns)]
            result.append("-" * len(result[0]))

            for row in rows:
                result.append(" | ".join(str(v) for v in row))

            return "\n".join(result)

        except sqlite3.Error as e:
            return f"Database error: {e}"
        finally:
            conn.close()
```

### 注册自定义工具

```python
# 在 AgentLoop.__init__ 中
from nanobot.agent.tools.base import Tool

# 创建自定义工具
db_tool = DatabaseQueryTool(db_path="/path/to/database.db")

# 注册到工具注册表
self.tools.register(db_tool)
```

### 动态工具注册

```python
class DynamicToolRegistry:
    """支持运行时添加/移除工具。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
        logger.info("Registered tool: {}", tool.name)

    def unregister(self, name: str) -> bool:
        """注销工具。"""
        if name in self._tools:
            del self._tools[name]
            logger.info("Unregistered tool: {}", name)
            return True
        return False

    def get(self, name: str) -> Tool | None:
        """获取工具。"""
        return self._tools.get(name)

    def get_definitions(self) -> list[dict]:
        """获取所有工具的 OpenAI 格式定义。"""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """执行工具。"""
        tool = self.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'"

        # 验证参数
        errors = tool.validate_params(arguments)
        if errors:
            return f"Error: Invalid parameters: {', '.join(errors)}"

        # 执行工具
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            logger.exception("Tool {} failed", name)
            return f"Error: {e}"
```

## 4.4 MCP 工具集成

### MCP 简介

MCP (Model Context Protocol) 是一个开放协议，用于连接 AI 应用和外部数据源。

### 配置 MCP 服务器

```json
{
  "tools": {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"],
        "env": {}
      },
      "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "your-token"
        }
      }
    }
  }
}
```

### MCP 连接

```python
async def connect_mcp_servers(
    servers_config: dict,
    tools: ToolRegistry,
    stack: AsyncExitStack,
) -> None:
    """连接到配置的 MCP 服务器。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    for name, config in servers_config.items():
        try:
            # 创建服务器参数
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("env", {}),
            )

            # 连接到服务器
            stdio, write = await stdio_client(server_params)
            session = ClientSession(stdio, write)

            await stack.enter_async_context(session)
            await session.initialize()

            # 获取工具列表
            response = await session.list_tools()

            # 包装 MCP 工具
            for tool in response.tools:
                mcp_tool = MCPTool(session, tool)
                tools.register(mcp_tool)

                logger.info("Registered MCP tool: {} from {}", tool.name, name)

        except Exception as e:
            logger.error("Failed to connect MCP server {}: {}", name, e)


class MCPTool(Tool):
    """MCP 工具包装器。"""

    def __init__(self, session: ClientSession, tool_schema: dict):
        self.session = session
        self._schema = tool_schema

    @property
    def name(self) -> str:
        return self._schema.name

    @property
    def description(self) -> str:
        return self._schema.description

    @property
    def parameters(self) -> dict:
        return self._schema.inputSchema

    async def execute(self, **kwargs) -> str:
        result = await self.session.call_tool(self.name, kwargs)
        # 格式化结果
        if hasattr(result, "content"):
            return "\n".join(c.text for c in result.content if hasattr(c, "text"))
        return str(result)
```

## 4.5 工具最佳实践

### 安全性

1. **路径验证**：限制文件访问范围
2. **命令过滤**：阻止危险的 shell 命令
3. **输入清理**：防止注入攻击
4. **资源限制**：设置超时和大小限制

### 错误处理

```python
async def execute(self, **kwargs) -> str:
    try:
        # 执行逻辑
        result = await self._do_work(**kwargs)
        return result
    except PermissionError:
        return "Error: Permission denied"
    except FileNotFoundError:
        return "Error: File not found"
    except ValueError as e:
        return f"Error: Invalid input - {e}"
    except Exception as e:
        logger.exception("Tool {} failed", self.name)
        return f"Error: {type(e).__name__}: {e}"
```

### 参数验证

```python
@property
def parameters(self) -> dict:
    return {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "format": "uri",
                "description": "有效的 URL"
            },
            "timeout": {
                "type": "integer",
                "minimum": 1,
                "maximum": 300,
                "default": 30,
                "description": "超时秒数（1-300）"
            }
        },
        "required": ["url"]
    }
```

### 文档和描述

```python
@property
def description(self) -> str:
    """清晰描述工具的功能和使用场景。"""
    return """搜索最近的代码提交历史。

使用场景：
- 查找特定功能的实现
- 理解代码变更历史
- 追踪 bug 修复

示例：
- search_commits("authentication", limit=10)
- search_commits(author="john", since="2024-01-01")
"""
```

## 4.6 下一步

阅读完本章后，建议继续阅读：
- [第5章：Channel 集成](05-channel-integration.md) - 学习平台集成
- [第6章：Provider 扩展](06-provider-extension.md) - 学习 LLM 集成
