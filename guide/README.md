# Nanobot Agent 开发指南

欢迎阅读 **Nanobot Agent 开发指南**！这是一份全面的开发者文档，帮助你深入理解和使用 nanobot 框架。

## 目录

### 第1章：[概述篇](01-overview.md)
- 项目简介与设计理念
- 核心特性与架构图
- 快速开始指南
- 开发环境搭建
- 项目结构说明
- 关键概念介绍

### 第2章：[核心架构](02-core-architecture.md)
- 消息总线架构
- 数据流详解
- 核心组件概览
- 事件驱动模式
- 组件交互图
- 扩展点说明

### 第3章：[Agent Loop 深度解析](03-agent-loop.md)
- Agent Loop 生命周期
- 消息处理流程
- LLM 交互循环
- 子代理管理
- 内存整合
- 进度回调机制

### 第4章：[工具系统开发](04-tools-development.md)
- 工具基础架构
- 内置工具详解
- 自定义工具开发
- MCP 工具集成
- 工具最佳实践

### 第5章：[Channel 集成指南](05-channel-integration.md)
- Channel 接口设计
- 平台适配模式
- 消息格式转换
- 权限与安全
- 高级特性
- 调试技巧

### 第6章：[Provider 扩展系统](06-provider-extension.md)
- Provider 注册机制
- Provider 接口规范
- 添加新 Provider
- 多模型支持
- OAuth Provider
- 高级特性

### 第7章：[配置系统详解](07-configuration.md)
- 配置文件结构
- 环境变量覆盖
- 各模块配置详解
- 配置验证
- 配置最佳实践

### 第8章：[最佳实践与进阶](08-best-practices.md)
- 内存与会话管理
- 技能系统使用
- Cron 定时任务
- 调试与测试
- 性能优化
- 常见问题与解决方案
- 生产部署

## 快速导航

### 我想...

- **开始使用 nanobot** → [第1章：概述篇](01-overview.md)
- **理解架构和设计** → [第2章：核心架构](02-core-architecture.md)
- **开发自定义工具** → [第4章：工具系统开发](04-tools-development.md)
- **集成新的聊天平台** → [第5章：Channel 集成指南](05-channel-integration.md)
- **添加新的 LLM Provider** → [第6章：Provider 扩展系统](06-provider-extension.md)
- **配置和部署** → [第7章：配置系统详解](07-configuration.md) 和 [第8章：最佳实践与进阶](08-best-practices.md)

## 核心概念

| 概念 | 说明 | 相关章节 |
|------|------|----------|
| Message Bus | 消息总线，解耦平台和 Agent | [第2章](02-core-architecture.md#消息总线架构) |
| Agent Loop | 核心处理引擎 | [第3章](03-agent-loop.md) |
| Tool | Agent 的能力扩展 | [第4章](04-tools-development.md) |
| Channel | 聊天平台集成 | [第5章](05-channel-integration.md) |
| Provider | LLM 提供商抽象 | [第6章](06-provider-extension.md) |
| Session | 会话管理 | [第8章](08-best-practices.md#内存与会话管理) |
| Skill | 技能描述文档 | [第8章](08-best-practices.md#技能系统使用) |

## 代码示例

### 创建自定义工具

```python
from nanobot.agent.tools.base import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "我的工具"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            },
            "required": ["input"]
        }

    async def execute(self, input: str) -> str:
        return f"处理结果: {input}"

# 注册工具
agent_loop.tools.register(MyTool())
```

### 创建自定义 Channel

```python
from nanobot.channels.base import BaseChannel

class MyChannel(BaseChannel):
    name = "mychannel"

    async def start(self) -> None:
        """启动连接。"""
        pass

    async def stop(self) -> None:
        """停止连接。"""
        pass

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息。"""
        pass
```

## 学习路径

### 初学者

1. 阅读 [第1章：概述篇](01-overview.md)
2. 按照快速开始指南安装和运行
3. 阅读 [第2章：核心架构](02-core-architecture.md) 理解基本概念
4. 尝试创建自定义工具（[第4章](04-tools-development.md)）

### 中级开发者

1. 深入学习 [第3章：Agent Loop](03-agent-loop.md)
2. 学习如何集成新平台（[第5章](05-channel-integration.md)）
3. 了解 Provider 系统（[第6章](06-provider-extension.md)）
4. 学习配置管理（[第7章](07-configuration.md)）

### 高级开发者

1. 研究源代码
2. 学习最佳实践（[第8章](08-best-practices.md)）
3. 参与项目贡献
4. 部署生产环境

## 常用命令

```bash
# 初始化配置
nanobot onboard

# 启动网关
nanobot gateway

# 交互式聊天
nanobot agent

# 查看状态
nanobot status

# 运行测试
pytest

# 代码检查
ruff check nanobot/
ruff format nanobot/
```

## 资源链接

- **项目仓库**: [https://github.com/your-repo/nanobot](https://github.com/your-repo/nanobot)
- **问题反馈**: [GitHub Issues](https://github.com/your-repo/nanobot/issues)
- **CLAUDE.md**: [项目开发指南](../CLAUDE.md)
- **README.md**: [用户文档](../README.md)

## 贡献指南

欢迎贡献！请阅读 [CONTRIBUTING.md](../CONTRIBUTING.md) 了解详情。

## 许可证

[MIT License](../LICENSE)

---

**Happy Coding! 🐈**
