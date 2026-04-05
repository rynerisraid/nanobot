# Nanobot Agent 开发指南 - 第7章：配置系统详解

## 7.1 配置文件结构

### 配置位置

```
~/.nanobot/
├── config.json          # 主配置文件
└── workspace/           # 工作空间
    ├── memory/
    │   ├── MEMORY.md    # 长期记忆
    │   └── HISTORY.md   # 历史日志
    ├── skills/          # 自定义技能
    └── templates/       # 工作空间模板
```

### 配置 Schema

nanobot 使用 Pydantic 进行配置验证：

```python
class Base(BaseModel):
    """接受 camelCase 和 snake_case 的基础模型。"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra='ignore'  # 向前兼容：忽略额外字段
    )
```

## 7.2 环境变量覆盖

### 环境变量语法

使用 `NANOBOT__` 前缀和双下划线分隔路径：

```bash
# Provider 配置
export NANOBOT__PROVIDERS__ANTHROPIC__API_KEY="sk-ant-..."
export NANOBOT__PROVIDERS__OPENAI__API_KEY="sk-openai-..."

# Channel 配置
export NANOBOT__CHANNELS__TELEGRAM__TOKEN="your-bot-token"

# Agent 配置
export NANOBOT__AGENTS__MODEL="claude-3-sonnet-20240229"
export NANOBOT__AGENTS__TEMPERATURE="0.7"

# 工具配置
export NANOBOT__TOOLS__WEB_SEARCH__API_KEY="your-brave-key"
```

### 优先级

```
环境变量 > 配置文件 > 默认值
```

## 7.3 各模块配置详解

### Agents 配置

```json
{
  "agents": {
    "workspace": "~/.nanobot/workspace",
    "model": "claude-3-sonnet-20240229",
    "temperature": 0.1,
    "maxTokens": 4096,
    "memoryWindow": 100,
    "maxIterations": 40,
    "reasoningEffort": null
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| workspace | string | ~/.nanobot/workspace | 工作空间路径 |
| model | string | - | LLM 模型标识符 |
| temperature | float | 0.1 | 采样温度 (0-2) |
| maxTokens | int | 4096 | 最大生成 token 数 |
| memoryWindow | int | 100 | 触发内存整合的消息数 |
| maxIterations | int | 40 | 最大工具调用迭代次数 |
| reasoningEffort | string | null | 推理强度 (low/medium/high) |

### Providers 配置

```json
{
  "providers": {
    "anthropic": {
      "enabled": true,
      "apiKey": "sk-ant-...",
      "apiBase": null
    },
    "openai": {
      "enabled": false,
      "apiKey": "",
      "apiBase": null,
      "organization": null
    },
    "custom": {
      "enabled": false,
      "apiKey": "",
      "apiBase": "https://..."
    }
  }
}
```

### Channels 配置

#### Telegram

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "your-bot-token",
      "allowFrom": ["*"],
      "proxy": null,
      "replyToMessage": false
    }
  }
}
```

#### Discord

```json
{
  "channels": {
    "discord": {
      "enabled": true,
      "token": "your-bot-token",
      "allowFrom": ["*"],
      "gatewayUrl": "wss://gateway.discord.gg/?v=10&encoding=json",
      "intents": 37377,
      "groupPolicy": "mention"
    }
  }
}
```

#### Slack

```json
{
  "channels": {
    "slack": {
      "enabled": true,
      "mode": "socket",
      "webhookPath": "/slack/events",
      "botToken": "xoxb-...",
      "appToken": "xapp-...",
      "replyInThread": true,
      "reactEmoji": "eyes",
      "allowFrom": ["*"],
      "groupPolicy": "mention"
    }
  }
}
```

### Tools 配置

```json
{
  "tools": {
    "webSearch": {
      "apiKey": "your-brave-api-key",
      "proxy": null
    },
    "exec": {
      "timeout": 30,
      "pathAppend": ["/usr/local/bin"],
      "restrictToWorkspace": false
    },
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"]
      }
    }
  }
}
```

### Gateway 配置

```json
{
  "gateway": {
    "host": "localhost",
    "port": 18791,
    "heartbeat": {
      "enabled": true,
      "intervalMinutes": 30
    }
  }
}
```

## 7.4 配置验证

### Pydantic 验证

```python
from nanobot.config.schema import NanobotConfig

# 加载并验证配置
with open(config_path) as f:
    config_data = json.load(f)

config = NanobotConfig(**config_data)

# 访问配置
model = config.agents.model
temperature = config.agents.temperature
```

### 配置错误示例

```json
{
  "agents": {
    "temperature": 3.0  // 错误：超出范围 (0-2)
  }
}
```

```
ValidationError: 1 validation error for AgentsConfig
temperature
  Input should be less than or equal to 2 [type=less_than_equal, input_value=3.0]
```

## 7.5 配置最佳实践

### 安全性

1. **不要在配置文件中存储敏感信息**
   ```json
   {
     "providers": {
       "anthropic": {
         "apiKey": "sk-ant-..."  // ❌ 不要提交到版本控制
       }
     }
   }
   ```

2. **使用环境变量**
   ```bash
   export NANOBOT__PROVIDERS__ANTHROPIC__API_KEY="sk-ant-..."
   ```

3. **使用配置模板**
   ```json
   {
     "providers": {
       "anthropic": {
         "enabled": true,
         "apiKey": "${ANTHROPIC_API_KEY}"  // 使用占位符
       }
     }
   }
   ```

### 多环境配置

```bash
# 开发环境
export NANOBOT__AGENTS__MODEL="claude-3-haiku-20240307"
export NANOBOT__AGENTS__TEMPERATURE="0.7"

# 生产环境
export NANOBOT__AGENTS__MODEL="claude-3-sonnet-20240229"
export NANOBOT__AGENTS__TEMPERATURE="0.1"
```

### 配置片段

```bash
# ~/.nanobot/config.d/telegram.json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}"
    }
  }
}

# ~/.nanobot/config.d/slack.json
{
  "channels": {
    "slack": {
      "enabled": true,
      "botToken": "${SLACK_BOT_TOKEN}"
    }
  }
}
```

## 7.6 配置热加载

### 文件监控

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, reload_callback):
        self.reload_callback = reload_callback

    def on_modified(self, event):
        if event.src_path.endswith("config.json"):
            logger.info("Config file modified, reloading...")
            self.reload_callback()

# 使用
def reload_config():
    config = load_config()
    # 应用新配置...

observer = Observer()
observer.schedule(
    ConfigReloadHandler(reload_config),
    path="~/.nanobot",
)
observer.start()
```

## 7.7 配置调试

### 查看当前配置

```bash
nanobot status
```

输出示例：

```
=== Nanobot Status ===

Agents:
  Model: claude-3-sonnet-20240229
  Temperature: 0.1
  Max Tokens: 4096
  Memory Window: 100

Providers:
  ✓ Anthropic (enabled)
  ✓ OpenRouter (gateway detected)

Channels:
  ✓ Telegram (enabled)
  ✓ Discord (enabled)

Tools:
  ✓ Web Search (Brave API)
  ✓ MCP Servers (2 connected)
```

### 配置验证

```python
from nanobot.config.schema import NanobotConfig

def validate_config(config_path: str) -> bool:
    """验证配置文件。"""
    try:
        with open(config_path) as f:
            config_data = json.load(f)
        NanobotConfig(**config_data)
        return True
    except ValidationError as e:
        print(f"配置错误: {e}")
        return False
    except Exception as e:
        print(f"加载失败: {e}")
        return False
```

## 7.8 下一步

阅读完本章后，建议继续阅读：
- [第8章：最佳实践](08-best-practices.md) - 学习生产部署和优化
