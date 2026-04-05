# Nanobot Agent 开发指南 - 第2章：核心架构

## 2.1 消息总线架构

消息总线（Message Bus）是 nanobot 的核心抽象，实现了聊天平台与 agent 逻辑的解耦。

### 设计理念

采用异步队列模式实现生产者-消费者架构：

```
Channel (生产者) → inbound_queue → Agent Loop (消费者)
Agent Loop (生产者) → outbound_queue → Channel (消费者)
```

### 核心组件

#### MessageBus ([`bus/queue.py`](../nanobot/bus/queue.py))

```python
class MessageBus:
    """异步消息总线，解耦 channels 和 agent loop。"""

    def __init__(self):
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """发布入站消息。"""
        await self._inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """消费入站消息（阻塞）。"""
        return await self._inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """发布出站消息。"""
        await self._outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """消费出站消息（阻塞）。"""
        return await self._outbound.get()
```

### 优势

1. **解耦**：Channel 和 Agent Loop 独立开发和测试
2. **异步**：支持高并发消息处理
3. **可观测性**：易于在队列层添加监控和调试
4. **扩展性**：支持多个 channel 和多个 agent 实例

## 2.2 数据流详解

### 完整数据流

```
┌──────────────┐
│ 用户输入      │
│  (Telegram)  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│  TelegramChannel                     │
│  1. 接收平台消息                     │
│  2. 权限检查 (allowFrom)             │
│  3. 创建 InboundMessage              │
│  4. 发布到 inbound_queue             │
└──────┬───────────────────────────────┘
       │
       ▼ InboundMessage
┌──────────────────────────────────────┐
│  MessageBus.inbound_queue            │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  AgentLoop                           │
│  1. 消费 inbound_queue               │
│  2. 获取/创建 Session                │
│  3. ContextBuilder.build_messages()  │
│  4. LLM 调用循环 (max 40 次)         │
│     - 调用 provider.chat()           │
│     - 执行工具调用                    │
│     - 处理结果                        │
│  5. 保存到 Session                   │
│  6. 创建 OutboundMessage             │
└──────┬───────────────────────────────┘
       │
       ▼ OutboundMessage
┌──────────────────────────────────────┐
│  MessageBus.outbound_queue           │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  TelegramChannel                     │
│  1. 消费 outbound_queue              │
│  2. 格式转换 (Markdown → HTML)       │
│  3. 发送到平台                       │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────┐
│ 用户看到响应  │
└──────────────┘
```

### 关键数据结构

#### InboundMessage ([`bus/events.py`](../nanobot/bus/events.py:8))

```python
@dataclass
class InboundMessage:
    """从聊天频道接收的消息。"""
    channel: str                          # telegram, discord, slack...
    sender_id: str                        # 用户标识符
    chat_id: str                          # 聊天/频道标识符
    content: str                          # 消息文本
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # 媒体文件路径
    metadata: dict[str, Any] = field(default_factory=dict)  # 频道特定数据
    session_key_override: str | None = None  # 会话键覆盖（线程作用域）

    @property
    def session_key(self) -> str:
        """会话唯一标识符。"""
        return self.session_key_override or f"{self.channel}:{self.chat_id}"
```

#### OutboundMessage ([`bus/events.py`](../nanobot/bus/events.py:27))

```python
@dataclass
class OutboundMessage:
    """发送到聊天频道的消息。"""
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 2.3 核心组件概览

### AgentLoop ([`agent/loop.py`](../nanobot/agent/loop.py))

**职责**：核心处理引擎，协调整个 agent 生命周期

**关键方法**：
- `run()` - 主事件循环
- `_process_message()` - 处理单条消息
- `_run_agent_loop()` - LLM 交互循环
- `_consolidate_memory()` - 内存整合

**扩展点**：
- `_register_default_tools()` - 注册自定义工具
- 子类化覆盖消息处理逻辑

### ContextBuilder ([`agent/context.py`](../nanobot/agent/context.py))

**职责**：构建系统提示词和消息上下文

**上下文组装顺序**：
1. Identity（运行时信息、工作空间路径）
2. Bootstrap 文件（AGENTS.md、SOUL.md、USER.md、TOOLS.md）
3. 长期内存（MEMORY.md）
4. 始终激活的技能
5. 技能摘要（渐进式加载）

**关键方法**：
- `build_system_prompt()` - 构建系统提示词
- `build_messages()` - 构建完整消息列表
- `_build_runtime_context()` - 运行时元数据

### MemoryStore ([`agent/memory.py`](../nanobot/agent/memory.py))

**职责**：两层内存架构

**组件**：
- **MEMORY.md** - 长期事实（持久化）
- **HISTORY.md** - 可 grep 搜索的日志，带时间戳
- **Session-based** - JSONL 存储，LLM 缓存效率

**内存整合**：
- 触发条件：达到 `memory_window`（默认 100 条消息）
- LLM 驱动的摘要
- 后台整合，不阻塞处理

### SkillsLoader ([`agent/skills.py`](../nanobot/agent/skills.py))

**职责**：Markdown 格式的技能加载

**技能格式**：
```yaml
---
name: github
description: "与 GitHub 交互"
metadata: {
  "nanobot": {
    "emoji": "🐙",
    "requires": {"bins": ["gh"]},
    "always": true
  }
}
---
# agent 的使用说明
```

**技能发现顺序**：
1. 工作空间技能（`~/.nanobot/workspace/skills/`）- 最高优先级
2. 内置技能（`nanobot/skills/`）- 回退
3. 需求检查（bins、env vars）

### ToolRegistry ([`agent/tools/registry.py`](../nanobot/agent/tools/registry.py))

**职责**：动态工具管理

**特性**：
- 运行时注册/注销
- JSON Schema 验证
- 错误处理和提示
- 工具发现

**内置工具**：
- **文件系统** - read_file, write_file, edit_file, list_dir
- **Shell** - exec（带超时和工作空间限制）
- **Web** - web_search, web_fetch
- **消息** - 发送到聊天频道
- **生成** - 创建子代理
- **Cron** - 调度任务
- **MCP** - 外部工具服务器

### SubagentManager ([`agent/subagent.py`](../nanobot/agent/subagent.py))

**职责**：后台任务执行，隔离的 agent 实例

**特性**：
- 并行任务执行
- 通过 `/stop` 命令取消任务
- 会话作用域任务跟踪
- 通过消息总线发送结果
- 受限工具集（无 message/spawn 工具）

## 2.4 事件驱动模式

### 异步处理

nanobot 全面使用 `async/await` 模式：

```python
async def run(self) -> None:
    """运行 agent 循环。"""
    self._running = True
    await self._connect_mcp()
    logger.info("Agent loop started")

    while self._running:
        try:
            msg = await asyncio.wait_for(
                self.bus.consume_inbound(),
                timeout=1.0
            )
        except asyncio.TimeoutError:
            continue

        # 异步分派消息
        task = asyncio.create_task(self._dispatch(msg))
        self._active_tasks.setdefault(msg.session_key, []).append(task)
```

### 并发控制

- **全局处理锁**：`_processing_lock` 确保单条消息完整处理
- **会话级任务跟踪**：`_active_tasks` 支持按会话取消
- **内存整合锁**：防止并发整合同一会话

### 错误处理

```python
async def _dispatch(self, msg: InboundMessage) -> None:
    """在全局锁下处理消息。"""
    async with self._processing_lock:
        try:
            response = await self._process_message(msg)
            if response is not None:
                await self.bus.publish_outbound(response)
        except asyncio.CancelledError:
            logger.info("Task cancelled for session {}", msg.session_key)
            raise
        except Exception:
            logger.exception("Error processing message for session {}", msg.session_key)
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Sorry, I encountered an error.",
            ))
```

## 2.5 组件交互图

```
┌─────────────────────────────────────────────────────────────────┐
│                         Gateway 启动                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  MessageBus                                                      │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │   inbound_queue     │    │  outbound_queue     │             │
│  └─────────────────────┘    └─────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
         │                                    ▲
         │ consume                            │ publish
         ▼                                    │
┌─────────────────────────────────────────────────────────────────┐
│  AgentLoop                                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  ContextBuilder  │  MemoryStore  │  SkillsLoader        │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   ToolRegistry                          │    │
│  │  File │ Shell │ Web │ Message │ Spawn │ Cron │ MCP      │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 SubagentManager                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 SessionManager                          │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼ chat()
┌─────────────────────────────────────────────────────────────────┐
│  LLMProvider                                                     │
│  (LiteLLM-based, supports multiple providers)                   │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ publish
         │
┌─────────────────────────────────────────────────────────────────┐
│  Channels (Telegram, Discord, Slack, ...)                        │
└─────────────────────────────────────────────────────────────────┘
```

## 2.6 扩展点

### 1. 添加新 Channel

继承 [`BaseChannel`](../nanobot/channels/base.py:12)：

```python
class MyChannel(BaseChannel):
    name: str = "mychannel"

    async def start(self) -> None:
        """连接并监听消息。"""
        pass

    async def stop(self) -> None:
        """断开并清理资源。"""
        pass

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息。"""
        pass
```

### 2. 添加新 Tool

继承 [`Tool`](../nanobot/agent/tools/base.py:7)：

```python
class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "我的工具描述"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数1"}
            },
            "required": ["param1"]
        }

    async def execute(self, **kwargs) -> str:
        return "执行结果"
```

### 3. 添加新 Provider

1. 添加 `ProviderSpec` 到 [`PROVIDERS`](../nanobot/providers/registry.py:72)
2. 添加字段到 `ProvidersConfig`

### 4. 自定义 Skill

在工作空间创建 `~/.nanobot/workspace/skills/my-skill/SKILL.md`：

```markdown
---
name: my-skill
description: "我的技能"
metadata: {
  "nanobot": {
    "emoji": "🔧"
  }
}
---

# 使用说明

这里写技能的详细说明...
```

## 2.7 下一步

阅读完本章后，建议继续阅读：
- [第3章：Agent Loop](03-agent-loop.md) - 深入了解 agent 处理流程
- [第4章：工具开发](04-tools-development.md) - 学习工具开发
- [第5章：Channel 集成](05-channel-integration.md) - 学习平台集成
