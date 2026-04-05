# Nanobot Agent 开发指南 - 第1章：概述

## 1.1 项目简介

**nanobot** 是一个超轻量级的个人 AI 助手框架，核心代码仅约 4,000 行。它采用事件驱动架构，通过消息总线模式将大型语言模型（LLM）与多个聊天平台连接起来。

### 核心特性

- **超轻量级**：核心 agent 代码仅约 4,000 行
- **事件驱动**：基于消息总线的异步架构
- **多平台支持**：支持 10+ 聊天平台（Telegram、Discord、Slack、WhatsApp、飞书、钉钉、QQ、Matrix、Email 等）
- **多 Provider 支持**：通过 LiteLLM 支持 Anthropic、OpenAI、DeepSeek、Kimi 等多种 LLM
- **可扩展**：插件化的工具系统、通道和 Provider
- **生产就绪**：支持会话管理、内存持久化、安全控制等企业级特性

### 适用场景

- 个人 AI 助手搭建
- 多平台聊天机器人开发
- LLM 应用研究
- 自动化任务执行
- 知识管理和问答系统

## 1.2 设计理念

### 简洁性优先

nanobot 的设计哲学是"做减法"：
- 核心功能保持最小化
- 清晰的抽象和接口
- 避免过度工程化

### 事件驱动架构

采用异步消息总线模式解耦各组件：

```
聊天平台 → Channel → MessageBus → AgentLoop → LLM → Tools → Response → MessageBus → Channel → 聊天平台
```

### 插件化扩展

所有核心组件都支持插件式扩展：
- **Channel**：添加新的聊天平台支持
- **Provider**：添加新的 LLM Provider
- **Tool**：添加新的工具能力
- **Skill**：添加新的技能描述

## 1.3 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           nanobot 架构                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐                │
│  │  Telegram  │    │  Discord   │    │   Slack    │  ...           │
│  └─────┬──────┘    └─────┬──────┘    └─────┬──────┘                │
│        │                 │                  │                       │
│        ▼                 ▼                  ▼                       │
│  ┌─────────────────────────────────────────────────────┐           │
│  │                   Channel Layer                     │           │
│  │  (平台适配、消息格式转换、权限控制)                   │           │
│  └─────────────────────────────────────────────────────┘           │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────┐           │
│  │                   Message Bus                       │           │
│  │              (异步队列、消息路由)                    │           │
│  └─────────────────────────────────────────────────────┘           │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────┐           │
│  │                   Agent Loop                        │           │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │           │
│  │  │   Context   │  │   Memory    │  │  Skills   │  │           │
│  │  │   Builder   │  │   Store     │  │  Loader   │  │           │
│  │  └─────────────┘  └─────────────┘  └───────────┘  │           │
│  │  ┌─────────────────────────────────────────────┐  │           │
│  │  │              Tool Registry                  │  │           │
│  │  │  Filesystem | Shell | Web | Message | Spawn │  │           │
│  │  └─────────────────────────────────────────────┘  │           │
│  └─────────────────────────────────────────────────────┘           │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────┐           │
│  │                   Provider Layer                    │           │
│  │     (LLM Provider 抽象、模型路由、API 调用)          │           │
│  └─────────────────────────────────────────────────────┘           │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────┐           │
│  │              LLM Services                           │           │
│  │  Anthropic | OpenAI | DeepSeek | Kimi | ...        │           │
│  └─────────────────────────────────────────────────────┘           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 1.4 快速开始

### 环境要求

- Python 3.11+
- pip 或 uv（推荐）

### 安装

```bash
# 从源码安装（开发模式）
pip install -e .

# 使用 uv 安装（推荐，速度更快）
uv tool install nanobot-ai

# 安装可选依赖
pip install -e ".[matrix]"  # Matrix/E2EE 支持
pip install -e ".[dev]"     # 开发/测试
```

### 初始化配置

```bash
# 初始化配置和工作空间
nanobot onboard

# 启动网关（用于聊天渠道）
nanobot gateway

# 交互式 CLI 聊天
nanobot agent

# 单条消息测试
nanobot agent -m "你好！"

# 查看状态
nanobot status
```

### 配置文件位置

- **配置文件**：`~/.nanobot/config.json`
- **工作空间**：`~/.nanobot/workspace/`
- **内存文件**：`~/.nanobot/workspace/memory/MEMORY.md`
- **历史记录**：`~/.nanobot/workspace/memory/HISTORY.md`

## 1.5 开发环境搭建

### 获取源码

```bash
git clone https://github.com/your-repo/nanobot.git
cd nanobot
```

### 开发模式安装

```bash
# 使用 pip
pip install -e ".[dev]"

# 使用 uv
uv pip install -e ".[dev]"
```

### 代码质量工具

```bash
# Lint 检查（行长度：100，目标：py311）
ruff check nanobot/

# 格式化代码
ruff format nanobot/

# 运行测试
pytest

# 运行特定测试文件
pytest tests/test_commands.py
```

### 核心代码行数验证

```bash
bash core_agent_lines.sh
```

## 1.6 项目结构

```
nanobot/
├── agent/              # 核心 agent 逻辑
│   ├── loop.py         # Agent 主循环
│   ├── context.py      # 上下文构建
│   ├── memory.py       # 内存管理
│   ├── skills.py       # 技能加载
│   ├── subagent.py     # 子代理管理
│   └── tools/          # 工具系统
│       ├── base.py     # 工具基类
│       ├── registry.py # 工具注册表
│       ├── filesystem.py
│       ├── shell.py
│       ├── web.py
│       ├── message.py
│       ├── spawn.py
│       ├── cron.py
│       ├── mcp.py
│       └── acp.py
├── channels/           # 聊天平台集成
│   ├── base.py         # 基础接口
│   ├── telegram.py
│   ├── discord.py
│   ├── slack.py
│   ├── whatsapp.py
│   ├── feishu.py
│   ├── dingtalk.py
│   ├── matrix.py
│   ├── email.py
│   ├── qq.py
│   └── mochat.py
├── bus/                # 消息总线
│   ├── queue.py        # 消息队列
│   └── events.py       # 事件定义
├── config/             # 配置管理
│   └── schema.py       # 配置 Schema
├── providers/          # LLM Provider
│   ├── base.py         # Provider 基类
│   ├── registry.py     # Provider 注册表
│   └── litellm_provider.py
├── session/            # 会话管理
│   └── manager.py
├── cron/               # 定时任务
│   └── service.py
├── heartbeat/          # 心跳服务
│   └── service.py
├── skills/             # 内置技能
│   ├── github/
│   ├── weather/
│   ├── tmux/
│   ├── cron/
│   ├── memory/
│   └── ...
├── templates/          # 工作空间模板
│   ├── AGENTS.md
│   ├── SOUL.md
│   ├── USER.md
│   ├── TOOLS.md
│   └── HEARTBEAT.md
├── cli/                # 命令行接口
├── utils/              # 工具函数
└── tests/              # 测试
```

## 1.7 关键概念

### 消息总线（Message Bus）

消息总线是 nanobot 的核心抽象，用于解耦聊天平台和 agent 逻辑：

- **InboundMessage**：从聊天平台接收的消息
- **OutboundMessage**：发送到聊天平台的消息
- **异步队列**：支持高并发消息处理

### Agent Loop

Agent Loop 是核心处理引擎，负责：
1. 从消息总线接收消息
2. 构建上下文（历史、内存、技能）
3. 调用 LLM
4. 执行工具调用
5. 发送响应

### 会话管理

每个对话（channel:chat_id）都有独立的会话：
- **Session**：JSONL 存储，支持 LLM 缓存
- **内存整合**：定期将历史整合到长期内存
- **会话隔离**：不同对话互不干扰

### 工具系统

工具是 agent 的能力扩展：
- **内置工具**：文件系统、Shell、Web、消息发送、子代理等
- **MCP 工具**：支持外部工具服务器
- **自定义工具**：继承 Tool 基类实现

### 技能系统

技能是 Markdown 格式的指导文档：
- **工作空间技能**：`~/.nanobot/workspace/skills/`
- **内置技能**：`nanobot/skills/`
- **渐进式加载**：需要时动态加载

## 1.8 下一步

阅读完本章后，建议继续阅读：
- [第2章：核心架构](02-core-architecture.md) - 深入了解消息总线和数据流
- [第3章：Agent Loop](03-agent-loop.md) - 学习 agent 处理流程
- [第4章：工具开发](04-tools-development.md) - 学习如何扩展工具

## 1.9 参考资源

- [项目 README](../README.md)
- [CLAUDE.md](../CLAUDE.md) - 项目开发指南
- [测试文件](../tests/) - 示例用法
- [示例配置](../examples/)
