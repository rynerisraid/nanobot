# Nanobot Agent 开发指南 - 第5章：Channel 集成

## 5.1 Channel 接口设计

### BaseChannel 抽象类

所有 Channel 实现都继承自 [`BaseChannel`](../nanobot/channels/base.py:12)：

```python
class BaseChannel(ABC):
    """聊天频道实现的抽象基类。"""

    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """启动频道并开始监听消息。"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止频道并清理资源。"""
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """通过此频道发送消息。"""
        pass
```

### 权限控制

```python
def is_allowed(self, sender_id: str) -> bool:
    """检查 sender_id 是否被允许。空列表→拒绝所有；"*"→允许所有。"""
    allow_list = getattr(self.config, "allow_from", [])
    if not allow_list:
        logger.warning("{}: allow_from is empty — all access denied", self.name)
        return False
    if "*" in allow_list:
        return True
    sender_str = str(sender_id)
    return sender_str in allow_list or any(
        p in allow_list for p in sender_str.split("|") if p
    )
```

### 消息处理

```python
async def _handle_message(
    self,
    sender_id: str,
    chat_id: str,
    content: str,
    media: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    session_key: str | None = None,
) -> None:
    """处理来自聊天平台的入站消息。"""
    if not self.is_allowed(sender_id):
        logger.warning("Access denied for sender {} on channel {}", sender_id, self.name)
        return

    msg = InboundMessage(
        channel=self.name,
        sender_id=str(sender_id),
        chat_id=str(chat_id),
        content=content,
        media=media or [],
        metadata=metadata or {},
        session_key_override=session_key,
    )

    await self.bus.publish_inbound(msg)
```

## 5.2 平台适配模式

### Telegram Channel 示例

```python
"""Telegram 频道实现。"""

from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters

class TelegramChannel(BaseChannel):
    name = "telegram"

    def __init__(self, config: TelegramConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.token = config.token
        self.proxy = config.proxy
        self.reply_to_message = config.reply_to_message
        self._app: Application | None = None

    async def start(self) -> None:
        """启动 Telegram bot。"""
        # 创建应用
        builder = Application.builder()
        builder.token(self.token)

        if self.proxy:
            builder.proxy_url(self.proxy)

        self._app = builder.build()

        # 注册消息处理器
        self._app.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO | filters.Document.ALL,
            self._on_message,
        ))

        # 启动轮询
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._running = True
        logger.info("Telegram channel started")

    async def stop(self) -> None:
        """停止 Telegram bot。"""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        self._running = False
        logger.info("Telegram channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 Telegram。"""
        if not self._app:
            return

        bot = self._app.bot
        chat_id = msg.chat_id

        try:
            # Markdown 到 HTML 转换
            html_content = self._markdown_to_html(msg.content)

            # 发送消息
            await bot.send_message(
                chat_id=chat_id,
                text=html_content,
                parse_mode="HTML",
                reply_to_message_id=msg.reply_to if self.reply_to_message else None,
            )
        except Exception as e:
            logger.error("Failed to send Telegram message: {}", e)

    async def _on_message(self, update: Update) -> None:
        """处理 Telegram 更新。"""
        if not update.message or not update.effective_user:
            return

        # 提取媒体
        media = []
        if update.message.photo:
            # 获取最大尺寸的照片
            photo = update.message.photo[-1]
            file = await photo.get_file()
            media_path = f"/tmp/{file.file_id}.jpg"
            await file.download_to_drive(media_path)
            media.append(media_path)

        # 处理消息
        await self._handle_message(
            sender_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            content=update.message.text or "",
            media=media,
            metadata={"message_id": update.message.message_id},
        )

    @staticmethod
    def _markdown_to_html(md: str) -> str:
        """简单 Markdown 到 HTML 转换。"""
        html = md
        html = html.replace("**", "<b>").replace("**", "</b>")
        html = html.replace("__", "<b>").replace("__", "</b>")
        html = html.replace("*", "<i>").replace("*", "</i>")
        html = html.replace("_", "<i>").replace("_", "</i>")
        html = html.replace("`", "<code>").replace("`", "</code>")
        return html
```

### Discord Channel 示例

```python
"""Discord 频道实现。"""

import discord

class DiscordChannel(BaseChannel):
    name = "discord"

    def __init__(self, config: DiscordConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.token = config.token
        self.group_policy = config.group_policy
        self._client: discord.Client | None = None

    async def start(self) -> None:
        """启动 Discord bot。"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.direct_messages = True

        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            logger.info("Discord bot logged in as {}", self._client.user)

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return

            # 检查群组策略
            if isinstance(message.channel, discord.DMChannel):
                should_respond = True
            else:
                if self.group_policy == "mention":
                    should_respond = self._client.user in message.mentions
                else:  # open
                    should_respond = True

            if should_respond:
                await self._handle_message(
                    sender_id=str(message.author.id),
                    chat_id=str(message.channel.id),
                    content=message.content,
                    metadata={
                        "message_id": str(message.id),
                        "jump_url": message.jump_url,
                    },
                )

        await self._client.start(self.token)
        self._running = True

    async def stop(self) -> None:
        """停止 Discord bot。"""
        if self._client:
            await self._client.close()
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 Discord。"""
        if not self._client:
            return

        try:
            channel = self._client.get_channel(int(msg.chat_id))
            if channel:
                await channel.send(msg.content)
        except Exception as e:
            logger.error("Failed to send Discord message: {}", e)
```

## 5.3 消息格式转换

### Markdown 处理

不同平台支持不同的 Markdown 变体：

```python
class MarkdownConverter:
    """Markdown 格式转换器。"""

    @staticmethod
    def to_telegram_html(md: str) -> str:
        """转换为 Telegram HTML 格式。"""
        # Telegram 支持的标签：b, i, u, s, code, pre, a
        html = md
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'__(.+?)__', r'<b>\1</b>', html)
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
        html = re.sub(r'_(.+?)_', r'<i>\1</i>', html)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
        # 代码块
        html = re.sub(
            r'```(\w+)?\n(.+?)```',
            r'<pre><code class="\1">\2</code></pre>',
            html,
            flags=re.DOTALL
        )
        return html

    @staticmethod
    def to_discord(md: str) -> str:
        """转换为 Discord Markdown 格式。"""
        # Discord 原生支持大部分 CommonMarkdown
        return md

    @staticmethod
    def to_slack(md: str) -> str:
        """转换为 Slack Markdown 格式。"""
        # Slack 使用特殊语法
        md = re.sub(r'\*\*(.+?)\*\*', r'*\1*', md)  # 粗体
        md = re.sub(r'__(.+?)__', r'_\1_', md)      # 斜体
        md = re.sub(r'`(.+?)`', r'`\1`', md)         # 代码
        return md
```

### 媒体处理

```python
class MediaHandler:
    """统一的媒体处理接口。"""

    async def download_media(self, url: str, dest_dir: Path) -> str:
        """下载媒体文件到本地。"""
        import aiohttp

        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = hashlib.md5(url.encode()).hexdigest()
        dest_path = dest_dir / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    dest_path.write_bytes(data)

        return str(dest_path)

    async def upload_media(self, file_path: str, channel) -> str:
        """上传媒体文件到平台。"""
        raise NotImplementedError
```

## 5.4 权限与安全

### allowFrom 列表

```python
class TelegramConfig(Base):
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    # ...
```

配置示例：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "your-bot-token",
      "allowFrom": ["*"]  // 允许所有用户
      // 或 ["123456789", "@username"]  // 仅允许特定用户
    }
  }
}
```

### 用户 ID 获取

不同平台的用户 ID 格式：

| 平台 | 用户 ID 格式 | 示例 |
|------|--------------|------|
| Telegram | 数字 ID | `123456789` |
| Discord | 数字 ID | `123456789012345678` |
| Slack | 成员 ID | `U123AB456` |
| WhatsApp | 手机号 | `+8613800138000` |
| Feishu | open_id | `ou_xxxxxxxxx` |

## 5.5 高级特性

### 输入指示器

```python
async def send_typing_indicator(self, chat_id: str) -> None:
    """发送"正在输入"指示器。"""
    if self.name == "telegram":
        await self._app.bot.send_chat_action(
            chat_id=chat_id,
            action="typing"
        )
    elif self.name == "discord":
        # Discord 使用异步触发
        async with channel.typing():
            await asyncio.sleep(2)
```

### 线程回复

```python
async def send_threaded(self, msg: OutboundMessage, thread_id: str) -> None:
    """发送到特定线程。"""
    if self.name == "slack":
        await self._client.chat_postMessage(
            channel=msg.chat_id,
            text=msg.content,
            thread_ts=thread_id,
        )
```

### 进度更新

```python
async def send_progress(self, chat_id: str, content: str) -> str:
    """发送临时进度消息，返回消息 ID 用于更新。"""
    if self.name == "telegram":
        msg = await self._app.bot.send_message(
            chat_id=chat_id,
            text=content,
        )
        return str(msg.message_id)

async def update_progress(self, chat_id: str, message_id: str, content: str) -> None:
    """更新现有进度消息。"""
    if self.name == "telegram":
        await self._app.bot.edit_message_text(
            chat_id=chat_id,
            message_id=int(message_id),
            text=content,
        )
```

## 5.6 调试技巧

### 消息日志

```python
async def _handle_message(self, ...) -> None:
    # 记录入站消息
    logger.debug(
        "Inbound: channel={}, sender={}, chat={}, content={}",
        self.name, sender_id, chat_id, content[:100]
    )

    # 处理消息...

async def send(self, msg: OutboundMessage) -> None:
    # 记录出站消息
    logger.debug(
        "Outbound: channel={}, chat={}, content={}",
        self.name, msg.chat_id, msg.content[:100]
    )

    # 发送消息...
```

### 错误恢复

```python
async def send_with_retry(self, msg: OutboundMessage, max_retries: int = 3) -> None:
    """带重试的消息发送。"""
    for attempt in range(max_retries):
        try:
            await self.send(msg)
            return
        except Exception as e:
            logger.warning(
                "Send attempt {} failed: {}",
                attempt + 1, e
            )
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避
```

## 5.7 下一步

阅读完本章后，建议继续阅读：
- [第6章：Provider 扩展](06-provider-extension.md) - 学习 LLM 集成
- [第7章：配置系统](07-configuration.md) - 学习配置管理
