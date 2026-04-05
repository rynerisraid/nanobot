# Nanobot Agent 开发指南 - 第3章：Agent Loop 深度解析

## 3.1 Agent Loop 生命周期

Agent Loop 是 nanobot 的核心处理引擎，负责协调整个 agent 的生命周期。

### 初始化

```python
class AgentLoop:
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
        # ... 更多参数
    ):
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()

        # 核心组件
        self.context = ContextBuilder(workspace)
        self.sessions = SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(...)

        # 状态管理
        self._running = False
        self._processing_lock = asyncio.Lock()

        # 注册默认工具
        self._register_default_tools()
```

### 运行循环

```python
async def run(self) -> None:
    """运行 agent 循环，将消息分派为任务以保持响应。"""
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

        if msg.content.strip().lower() == "/stop":
            await self._handle_stop(msg)
        else:
            # 异步分派，保持响应
            task = asyncio.create_task(self._dispatch(msg))
            self._active_tasks.setdefault(msg.session_key, []).append(task)
```

### 停止

```python
def stop(self) -> None:
    """停止 agent 循环。"""
    self._running = False
    logger.info("Agent loop stopping")
```

## 3.2 消息处理流程

### 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│  InboundMessage 到达                                         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  _dispatch() - 异步分派                                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  1. 获取全局处理锁 (_processing_lock)               │    │
│  │  2. 调用 _process_message()                         │    │
│  │  3. 发布 OutboundMessage 到 bus                     │    │
│  │  4. 错误处理和恢复                                   │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  _process_message() - 核心处理逻辑                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  斜杠命令处理                                                 │
│  /new → 清空会话，整合内存                                   │
│  /stop → 取消当前任务                                        │
│  /help → 显示帮助                                            │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  内存整合检查                                                 │
│  if unconsolidated >= memory_window:                        │
│      → 触发后台整合任务                                      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  构建上下文                                                   │
│  1. 设置工具上下文 (channel, chat_id)                        │
│  2. 获取会话历史                                             │
│  3. ContextBuilder.build_messages()                         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM 交互循环                                                 │
│  _run_agent_loop()                                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  for iteration in range(max_iterations):            │    │
│  │    1. provider.chat(messages, tools)               │    │
│  │    2. if has_tool_calls:                           │    │
│  │         - 发送进度更新                              │    │
│  │         - 执行工具调用                              │    │
│  │         - 添加工具结果到 messages                   │    │
│  │       else:                                         │    │
│  │         - 保存最终内容                              │    │
│  │         - break                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  保存会话                                                     │
│  _save_turn(session, messages, skip)                         │
│  - 添加新消息到 session.messages                             │
│  - 截断过大的工具结果                                        │
│  - 去除运行时上下文前缀                                      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  返回 OutboundMessage                                        │
└─────────────────────────────────────────────────────────────┘
```

### 关键方法详解

#### `_process_message()` - 消息处理核心

```python
async def _process_message(
    self,
    msg: InboundMessage,
    session_key: str | None = None,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> OutboundMessage | None:
    """处理单条入站消息并返回响应。"""

    # 1. 处理系统消息
    if msg.channel == "system":
        channel, chat_id = msg.chat_id.split(":", 1)
        session = self.sessions.get_or_create(f"{channel}:{chat_id}")
        # ... 系统消息特殊处理

    # 2. 斜杠命令
    cmd = msg.content.strip().lower()
    if cmd == "/new":
        session.clear()
        return OutboundMessage(..., content="New session started.")
    if cmd == "/help":
        return OutboundMessage(..., content="🐈 nanobot commands:...")

    # 3. 内存整合检查
    unconsolidated = len(session.messages) - session.last_consolidated
    if unconsolidated >= self.memory_window:
        # 触发后台整合
        _task = asyncio.create_task(self._consolidate_memory(session))

    # 4. 构建上下文
    self._set_tool_context(msg.channel, msg.chat_id)
    history = session.get_history(max_messages=self.memory_window)
    initial_messages = self.context.build_messages(
        history=history,
        current_message=msg.content,
        media=msg.media,
        channel=msg.channel,
        chat_id=msg.chat_id,
    )

    # 5. LLM 交互
    final_content, _, all_msgs = await self._run_agent_loop(
        initial_messages,
        on_progress=on_progress or self._bus_progress_callback(msg)
    )

    # 6. 保存会话
    self._save_turn(session, all_msgs, 1 + len(history))
    self.sessions.save(session)

    # 7. 返回响应
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=final_content,
    )
```

## 3.3 LLM 交互循环

### 循环逻辑

```python
async def _run_agent_loop(
    self,
    initial_messages: list[dict],
    on_progress: Callable[..., Awaitable[None]] | None = None,
) -> tuple[str | None, list[str], list[dict]]:
    """运行 agent 迭代循环。返回 (最终内容, 使用工具, 消息列表)。"""
    messages = initial_messages
    iteration = 0
    final_content = None
    tools_used: list[str] = []

    while iteration < self.max_iterations:
        iteration += 1

        # 1. 调用 LLM
        response = await self.provider.chat(
            messages=messages,
            tools=self.tools.get_definitions(),
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
        )

        # 2. 处理工具调用
        if response.has_tool_calls:
            # 发送进度更新
            if on_progress:
                await on_progress(self._tool_hint(response.tool_calls))

            # 添加 assistant 消息（含 tool_calls）
            tool_call_dicts = [self._format_tool_call(tc) for tc in response.tool_calls]
            messages = self.context.add_assistant_message(
                messages, response.content, tool_call_dicts
            )

            # 执行每个工具调用
            for tool_call in response.tool_calls:
                tools_used.append(tool_call.name)
                result = await self.tools.execute(tool_call.name, tool_call.arguments)
                messages = self.context.add_tool_result(
                    messages, tool_call.id, tool_call.name, result
                )
        else:
            # 3. 没有工具调用，保存最终响应
            clean = self._strip_think(response.content)
            if response.finish_reason == "error":
                logger.error("LLM returned error: {}", clean[:200])
                final_content = clean or "Sorry, I encountered an error."
                break

            messages = self.context.add_assistant_message(messages, clean)
            final_content = clean
            break

    # 4. 检查是否达到最大迭代次数
    if final_content is None and iteration >= self.max_iterations:
        logger.warning("Max iterations ({}) reached", self.max_iterations)
        final_content = f"I reached the maximum number of iterations..."

    return final_content, tools_used, messages
```

### 思考块处理

某些模型（如 DeepSeek-R1, Kimi）返回推理内容：

```python
@staticmethod
def _strip_think(text: str | None) -> str | None:
    """移除某些模型嵌入在内容中的思考块。"""
    if not text:
        return None
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None
```

### 工具提示格式化

```python
@staticmethod
def _tool_hint(tool_calls: list) -> str:
    """将工具调用格式化为简洁提示，如 'web_search("query")'。"""
    def _fmt(tc):
        args = tc.arguments or {}
        val = next(iter(args.values()), None)
        if not isinstance(val, str):
            return tc.name
        return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
    return ", ".join(_fmt(tc) for tc in tool_calls)
```

## 3.4 子代理管理

### SubagentManager

子代理管理器支持并行后台任务执行：

```python
class SubagentManager:
    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        # ... LLM 配置
    ):
        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self._tasks: dict[str, asyncio.Task] = {}

    async def spawn(
        self,
        prompt: str,
        session_key: str,
        channel: str,
        chat_id: str,
    ) -> str:
        """生成新的子代理任务。"""
        task_id = str(uuid.uuid4())

        async def _run_subagent():
            # 创建隔离的 agent 实例
            loop = AgentLoop(...)
            result = await loop.process_direct(prompt, session_key)

            # 发送结果
            await self.bus.publish_outbound(OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=f"[Task {task_id}] {result}",
            ))

        task = asyncio.create_task(_run_subagent())
        self._tasks[task_id] = task
        return task_id

    async def cancel_by_session(self, session_key: str) -> int:
        """取消会话的所有子代理任务。"""
        cancelled = 0
        for task_id, task in list(self._tasks.items()):
            if not task.done() and task.cancel():
                cancelled += 1
        return cancelled
```

### Spawn 工具

```python
class SpawnTool(Tool):
    def __init__(self, manager: SubagentManager):
        self.manager = manager

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return "生成子代理在后台执行任务"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "任务描述"},
            },
            "required": ["prompt"],
        }

    async def execute(self, prompt: str) -> str:
        # 从上下文获取 session 信息
        task_id = await self.manager.spawn(
            prompt=prompt,
            session_key=self._session_key,
            channel=self._channel,
            chat_id=self._chat_id,
        )
        return f"Task {task_id} started."
```

## 3.5 内存整合

### 整合触发

```python
# 在 _process_message 中
unconsolidated = len(session.messages) - session.last_consolidated
if (unconsolidated >= self.memory_window
        and session.key not in self._consolidating):
    self._consolidating.add(session.key)
    lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

    async def _consolidate_and_unlock():
        try:
            async with lock:
                await self._consolidate_memory(session)
        finally:
            self._consolidating.discard(session.key)

    _task = asyncio.create_task(_consolidate_and_unlock())
    self._consolidation_tasks.add(_task)
```

### 整合执行

```python
async def _consolidate_memory(
    self,
    session: Session,
    archive_all: bool = False,
) -> bool:
    """委托给 MemoryStore.consolidate()。成功返回 True。"""
    return await MemoryStore(self.workspace).conssolidate(
        session,
        self.provider,
        self.model,
        archive_all=archive_all,
        memory_window=self.memory_window,
    )
```

## 3.6 进度回调

### 总线进度回调

```python
async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
    """通过消息总线发送进度更新。"""
    meta = dict(msg.metadata or {})
    meta["_progress"] = True
    meta["_tool_hint"] = tool_hint
    await self.bus.publish_outbound(OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=content,
        metadata=meta,
    ))
```

### 进度处理

Channel 可以根据 `_progress` 元数据以不同方式处理消息：

```python
# 在 Channel 实现中
async def send(self, msg: OutboundMessage) -> None:
    if msg.metadata.get("_progress"):
        # 显示为"正在输入..."或临时消息
        await self._send_temporary(msg.chat_id, msg.content)
    elif msg.metadata.get("_tool_hint"):
        # 显示工具调用提示
        await self._update_status(msg.chat_id, msg.content)
    else:
        # 正常消息
        await self._send_message(msg.chat_id, msg.content)
```

## 3.7 下一步

阅读完本章后，建议继续阅读：
- [第4章：工具开发](04-tools-development.md) - 学习如何扩展工具系统
- [第8章：最佳实践](08-best-practices.md) - 学习调试和优化技巧
