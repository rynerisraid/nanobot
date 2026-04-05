# Nanobot Agent 开发指南 - 第8章：最佳实践与进阶

## 8.1 内存与会话管理

### 内存整合策略

```python
class MemoryConsolidationStrategy:
    """内存整合策略。"""

    # 触发阈值
    MEMORY_WINDOW = 100  # 消息数

    # 整合时机
    def should_consolidate(self, session: Session) -> bool:
        """判断是否应该整合。"""
        unconsolidated = len(session.messages) - session.last_consolidated
        return unconsolidated >= self.MEMORY_WINDOW

    # 整合内容
    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
    ) -> bool:
        """执行内存整合。"""
        messages_to_consolidate = session.messages[session.last_consolidated:]

        # 构建整合提示
        prompt = f"""请将以下对话历史总结为关键信息点，保存到长期记忆中。

对话历史：
{format_messages(messages_to_consolidate)}

请提取：
1. 重要的决策和结论
2. 用户偏好和设置
3. 项目相关的关键信息
4. 需要记住的上下文

输出格式：Markdown 格式的事实列表
"""

        # 调用 LLM
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )

        if response.content:
            # 保存到 MEMORY.md
            memory_store = MemoryStore(session.workspace)
            await memory_store.append_long_term(response.content)
            return True

        return False
```

### 会话隔离

```python
class SessionIsolation:
    """会话隔离管理。"""

    # 会话键格式
    SESSION_KEY_FORMAT = "{channel}:{chat_id}"

    # 线程作用域会话
    def get_thread_session_key(
        self,
        base_chat_id: str,
        thread_id: str,
    ) -> str:
        """获取线程作用域会话键。"""
        return f"{base_chat_id}:{thread_id}"

    # 用户作用域会话
    def get_user_session_key(
        self,
        channel: str,
        user_id: str,
    ) -> str:
        """获取用户作用域会话键（跨所有聊天）。"""
        return f"{channel}:user:{user_id}"
```

## 8.2 技能系统使用

### 技能模板

```markdown
---
name: my-skill
description: "我的技能描述"
metadata: {
  "nanobot": {
    "emoji": "🔧",
    "requires": {
      "bins": ["python"],
      "env": ["MY_API_KEY"]
    },
    "always": false
  }
}
---

# 技能名称

## 功能描述

这个技能用于...

## 使用方法

1. 前置条件
2. 执行步骤
3. 注意事项

## 示例

\`\`\`
用户：请执行 X
Agent：[使用本技能执行]
\`\`\`
```

### 动态技能加载

```python
class SkillsLoader:
    """技能加载器。"""

    def load_skill(self, skill_name: str) -> str | None:
        """加载单个技能。"""
        # 工作空间技能优先
        workspace_skill = self.workspace / "skills" / skill_name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text()

        # 内置技能回退
        builtin_skill = Path(__file__).parent / "skills" / skill_name / "SKILL.md"
        if builtin_skill.exists():
            return builtin_skill.read_text()

        return None

    def check_requirements(self, skill_metadata: dict) -> bool:
        """检查技能依赖。"""
        requires = skill_metadata.get("requires", {})

        # 检查二进制依赖
        for bin_name in requires.get("bins", []):
            if not shutil.which(bin_name):
                return False

        # 检查环境变量
        for env_var in requires.get("env", []):
            if not os.environ.get(env_var):
                return False

        return True
```

## 8.3 Cron 定时任务

### Cron 表达式

```python
from nanobot.cron.service import CronService

# 创建 cron 服务
cron = CronService(workspace=workspace)

# 添加定时任务
await cron.add_job(
    schedule="0 9 * * 1-5",  # 工作日上午 9 点
    prompt="早报摘要",
    chat_id="telegram:123456789",
)
```

### 三种调度类型

```python
# 1. at - 一次性任务
await cron.add_job(
    schedule="at:2024-01-01T00:00:00",
    prompt="新年快乐！",
    chat_id="telegram:123456789",
)

# 2. every - 间隔任务
await cron.add_job(
    schedule="every:3600000",  # 每小时（毫秒）
    prompt="检查系统状态",
    chat_id="telegram:123456789",
)

# 3. cron - Cron 表达式
await cron.add_job(
    schedule="0 */2 * * *",  # 每 2 小时
    prompt="同步数据",
    chat_id="telegram:123456789",
)
```

### 时区处理

```python
# 带时区的 cron
await cron.add_job(
    schedule="0 9 * * *",  # 使用本地时区
    schedule_timezone="Asia/Shanghai",  # 指定时区
    prompt="早安新闻",
    chat_id="telegram:123456789",
)
```

## 8.4 调试与测试

### 日志配置

```python
from loguru import logger

# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

# 添加文件日志
logger.add(
    "~/.nanobot/logs/nanobot.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)
```

### 调试模式

```bash
# 启用调试日志
export NANOBOT__DEBUG="true"
nanobot gateway

# 查看详细日志
tail -f ~/.nanobot/logs/nanobot.log
```

### 单元测试

```python
import pytest
from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus

@pytest.fixture
async def agent_loop():
    """创建测试用的 Agent Loop。"""
    bus = MessageBus()
    # Mock provider
    provider = MockLLMProvider()

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace="/tmp/nanobot-test",
        model="test-model",
    )
    return loop

@pytest.mark.asyncio
async def test_message_processing(agent_loop):
    """测试消息处理。"""
    # 创建测试消息
    from nanobot.bus.events import InboundMessage
    msg = InboundMessage(
        channel="test",
        sender_id="user1",
        chat_id="chat1",
        content="Hello",
    )

    # 处理消息
    response = await agent_loop._process_message(msg)

    # 断言
    assert response is not None
    assert "hello" in response.content.lower()
```

### 集成测试

```python
@pytest.mark.asyncio
async def test_tool_execution():
    """测试工具执行。"""
    from nanobot.agent.tools.filesystem import ReadFileTool

    tool = ReadFileTool(workspace="/tmp")
    result = await tool.execute(path="test.txt")

    assert isinstance(result, str)
```

## 8.5 性能优化

### 提示缓存

```python
class CachedContextBuilder(ContextBuilder):
    """带缓存的上下文构建器。"""

    def __init__(self, workspace: Path):
        super().__init__(workspace)
        self._system_prompt_cache: str | None = None
        self._cache_timestamp: float | None = None
        self._cache_ttl = 300  # 5 分钟

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """构建系统提示（带缓存）。"""
        now = time.time()

        # 检查缓存
        if self._system_prompt_cache and self._cache_timestamp:
            if now - self._cache_timestamp < self._cache_ttl:
                return self._system_prompt_cache

        # 重建并缓存
        prompt = super().build_system_prompt(skill_names)
        self._system_prompt_cache = prompt
        self._cache_timestamp = now

        return prompt
```

### 并发处理

```python
class ConcurrentMessageProcessor:
    """并发消息处理器。"""

    def __init__(self, max_concurrent: int = 10):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task] = set()

    async def process(self, msg: InboundMessage) -> None:
        """并发处理消息。"""
        async with self._semaphore:
            task = asyncio.create_task(self._process_single(msg))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            await task

    async def _process_single(self, msg: InboundMessage) -> None:
        """处理单条消息。"""
        # 实际处理逻辑...
        pass
```

### 资源清理

```python
class ResourceCleanup:
    """资源清理管理。"""

    async def cleanup_session(self, session_key: str) -> None:
        """清理会话资源。"""
        # 取消进行中的任务
        await self._cancel_tasks(session_key)

        # 清理临时文件
        await self._cleanup_temp_files(session_key)

        # 整合内存
        session = self.sessions.get(session_key)
        if session:
            await self._consolidate_memory(session)

    async def _cleanup_temp_files(self, session_key: str) -> None:
        """清理临时文件。"""
        temp_dir = self.workspace / "temp" / session_key
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
```

## 8.6 常见问题与解决方案

### 问题 1：消息重复处理

```python
# 原因：消息队列中的消息未被正确确认

# 解决：添加消息 ID 去重
class MessageDeduplicator:
    def __init__(self, ttl: int = 300):
        self._seen: dict[str, float] = {}
        self._ttl = ttl

    def is_seen(self, message_id: str) -> bool:
        """检查消息是否已处理。"""
        if message_id in self._seen:
            return True
        self._seen[message_id] = time.time()
        return False

    def cleanup(self):
        """清理过期记录。"""
        now = time.time()
        self._seen = {
            k: v for k, v in self._seen.items()
            if now - v < self._ttl
        }
```

### 问题 2：内存泄漏

```python
# 原因：会话消息无限增长

# 解决：自动限制会话大小
class SessionLimiter:
    def __init__(self, max_messages: int = 1000):
        self.max_messages = max_messages

    def enforce_limit(self, session: Session) -> None:
        """强制执行会话大小限制。"""
        if len(session.messages) > self.max_messages:
            # 保留最近的消息
            session.messages = session.messages[-self.max_messages:]
```

### 问题 3：工具执行超时

```python
# 原因：工具执行时间过长

# 解决：添加超时和取消
async def execute_with_timeout(
    coro,
    timeout: float,
) -> Any:
    """带超时的执行。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Tool execution timed out after {}s", timeout)
        return "Error: Execution timed out"
```

### 问题 4：LLM API 限流

```python
# 解决：指数退避重试
class RetryWithBackoff:
    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute(self, func: Callable, *args, **kwargs):
        """带重试的执行。"""
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except RateLimitError:
                if attempt == self.max_retries - 1:
                    raise
                delay = min(
                    self.base_delay * (2 ** attempt),
                    self.max_delay
                )
                logger.warning(
                    "Rate limited, retrying in {}s (attempt {})",
                    delay, attempt + 1
                )
                await asyncio.sleep(delay)
```

## 8.7 生产部署

### Docker 部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY pyproject.toml ./
RUN pip install -e ".[dev]"

# 复制代码
COPY nanobot/ ./nanobot/

# 创建工作空间
RUN mkdir -p /root/.nanobot/workspace

# 暴露端口
EXPOSE 18791

# 启动服务
CMD ["nanobot", "gateway", "-h", "0.0.0.0"]
```

### Systemd 服务

```ini
[Unit]
Description=Nanobot Gateway
After=network.target

[Service]
Type=simple
User=nanobot
WorkingDirectory=/home/nanobot
Environment="NANOBOT__AGENTS__MODEL=claude-3-sonnet-20240229"
Environment="NANOBOT__PROVIDERS__ANTHROPIC__API_KEY=%i"
ExecStart=/usr/local/bin/nanobot gateway
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 健康检查

```python
from aiohttp import web

class HealthCheckServer:
    def __init__(self, port: int = 18792):
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/health", self.health)

    async def health(self, request):
        """健康检查端点。"""
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
        })

    async def start(self):
        """启动健康检查服务器。"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()
```

## 8.8 资源链接

- [项目仓库](https://github.com/your-repo/nanobot)
- [问题反馈](https://github.com/your-repo/nanobot/issues)
- [贡献指南](CONTRIBUTING.md)

---

恭喜！您已经完成了 Nanobot Agent 开发指南的全部内容。现在您可以：

1. 开发自定义工具和技能
2. 集成新的聊天平台
3. 添加新的 LLM Provider
4. 部署生产环境

祝您开发愉快！🐈
