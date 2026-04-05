# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**nanobot** is an ultra-lightweight personal AI assistant framework (~4,000 lines of core agent code). It's an event-driven system that connects LLMs to multiple chat platforms (Telegram, Discord, Slack, WhatsApp, Feishu, DingTalk, QQ, Email, Matrix) through a message bus architecture.

## Development Commands

### Installation
```bash
# From source (development)
pip install -e .

# With uv (recommended for speed)
uv tool install nanobot-ai

# Install optional dependencies
pip install -e ".[matrix]"  # For Matrix/E2EE support
pip install -e ".[dev]"     # For development/testing
```

### Building
```bash
# Build wheel
python -m build
# or
uv build
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_commands.py

# Tests use pytest-asyncio with async_mode = "auto"
```

### Linting
```bash
# Lint code (line length: 100, target: py311)
ruff check nanobot/

# Format code
ruff format nanobot/
```

### Running
```bash
# Initialize config & workspace
nanobot onboard

# Interactive CLI chat
nanobot agent

# Single message
nanobot agent -m "Hello!"

# Start gateway (for chat channels)
nanobot gateway

# Check status
nanobot status

# Verify core line count
bash core_agent_lines.sh
```

## Architecture

The architecture follows an **event-driven message bus pattern** with these core components:

### Data Flow
```
Chat Platform → Channel → MessageBus → AgentLoop → LLM → Tools → Response → MessageBus → Channel → Chat Platform
```

### Key Components

**Agent Loop** (`nanobot/agent/loop.py`)
- Central processing engine that orchestrates the entire agent lifecycle
- Receives `InboundMessage` from the bus
- Builds context using `ContextBuilder` (identity, bootstrap files, memory, skills)
- Calls LLM and executes tool calls iteratively (max 40 iterations by default)
- Sends `OutboundMessage` back through the bus

**Message Bus** (`nanobot/bus/`)
- `queue.py`: Async queue-based message routing between channels and agent
- `events.py`: Defines `InboundMessage` and `OutboundMessage` dataclasses
- Decouples channel implementations from agent logic

**Channels** (`nanobot/channels/`)
- Base class interface in `base.py` with `start()`, `stop()`, `send()` methods
- Each channel implements the interface and has permission checking via `allowFrom` lists
- Channels push `InboundMessage` to bus and receive `OutboundMessage` to send

**Providers** (`nanobot/providers/`)
- `registry.py`: Provider registry with metadata - the single source of truth for provider configuration
- `base.py`: LLM provider interface
- `litellm_provider.py`: LiteLLM-based provider for multi-provider support
- Custom providers: OpenAI Codex (OAuth), direct OpenAI-compatible endpoints

**Tools** (`nanobot/agent/tools/`)
- `registry.py`: Dynamic tool management with JSON schema validation
- Built-in tools: filesystem (read, write, edit, list), shell exec, web search/fetch, message, spawn (subagents), cron
- MCP integration in `mcp.py` for external tool servers

**Memory & Sessions** (`nanobot/agent/memory.py`, `nanobot/session/`)
- Two-layer memory: `MEMORY.md` (long-term facts) + `HISTORY.md` (grep-searchable log)
- `SessionManager` with JSONL storage (append-only for LLM cache efficiency)
- Memory consolidation via LLM when session reaches `memory_window` (default: 100 messages)

**Skills** (`nanobot/agent/skills.py`, `nanobot/skills/`)
- Markdown-based skill loading from `SKILL.md` files
- Built-in skills: github, weather, tmux, cron, memory, clawhub, summarize
- Workspace skills override built-in skills

**Context Builder** (`nanobot/agent/context.py`)
- Builds system prompt from identity (`SOUL.md`), bootstrap files (`AGENTS.md`, `USER.md`), memory, skills
- Adds runtime context (time, channel, chat_id)
- Handles multimodal content (images)

**Subagent Manager** (`nanobot/agent/subagent.py`)
- Spawns isolated agent instances for parallel background task execution
- Task cancellation support via `/stop` command

**Cron Service** (`nanobot/cron/`)
- Scheduled job execution with three schedule types: "at", "every", "cron"
- JSONL persistence with auto-reload on external changes

**Heartbeat Service** (`nanobot/heartbeat/`)
- Periodic task execution (default: 30 minutes)
- Reads `HEARTBEAT.md` for task list and delivers results to most recent active channel

### Configuration

- **Config file**: `~/.nanobot/config.json` (schema-based with Pydantic, supports both camelCase and snake_case)
- **Workspace**: `~/.nanobot/workspace/`
- **Environment variable overrides** supported
- Key config sections: `providers`, `channels`, `agents`, `tools`, `security`

### Adding New Features

**New Provider** (2 steps):
1. Add `ProviderSpec` to `PROVIDERS` in `nanobot/providers/registry.py`
2. Add field to `ProvidersConfig` in `nanobot/config/schema.py`

**New Channel**:
1. Inherit from `BaseChannel` in `nanobot/channels/base.py`
2. Implement `start()`, `stop()`, `send()` methods
3. Add config to `ChannelsConfig` in `nanobot/config/schema.py`
4. Register in gateway startup logic

**New Tool**:
1. Inherit from `Tool` base class in `nanobot/agent/tools/base.py`
2. Implement JSON schema for parameters
3. Register in `AgentLoop.__init__()` or via MCP

### Security Model

- `restrictToWorkspace`: Sandboxes agent tools to workspace directory
- `allowFrom` lists on all channels (deny-by-default in newer versions - use `["*"]` to allow all)
- Dangerous command blocking in exec tool
- Session isolation with session keys

### Multi-Instance Support

Multiple nanobot instances can run simultaneously with different workspaces, configs, and ports:
```bash
nanobot gateway -w ~/.nanobot/botA -p 18791
nanobot gateway -w ~/.nanobot/botB -p 18792
```

### Workspace Templates

Auto-synced to workspace on `nanobot onboard`:
- `AGENTS.md` - Agent instructions
- `SOUL.md` - Agent personality/identity
- `USER.md` - User preferences
- `TOOLS.md` - Tool usage notes
- `HEARTBEAT.md` - Periodic tasks
