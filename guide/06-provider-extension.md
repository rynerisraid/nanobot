# Nanobot Agent 开发指南 - 第6章：Provider 扩展系统

## 6.1 Provider 注册机制

### ProviderSpec 结构

[`ProviderSpec`](../nanobot/providers/registry.py:19) 是 Provider 的元数据描述：

```python
@dataclass(frozen=True)
class ProviderSpec:
    """一个 LLM Provider 的元数据。"""

    # 身份
    name: str                    # 配置字段名，如 "dashscope"
    keywords: tuple[str, ...]    # 模型名关键字（小写）
    env_key: str                 # LiteLLM 环境变量，如 "DASHSCOPE_API_KEY"
    display_name: str = ""       # 在 `nanobot status` 中显示

    # 模型前缀
    litellm_prefix: str = ""     # "dashscope" → 模型变为 "dashscope/{model}"
    skip_prefixes: tuple[str, ...] = ()  # 如果模型已有此前缀则不添加

    # 额外环境变量
    env_extras: tuple[tuple[str, str], ...] = ()

    # 网关/本地检测
    is_gateway: bool = False     # 路由任何模型（OpenRouter, AiHubMix）
    is_local: bool = False       # 本地部署（vLLM, Ollama）
    detect_by_key_prefix: str = ""  # 匹配 api_key 前缀，如 "sk-or-"
    detect_by_base_keyword: str = ""  # 匹配 api_base URL 中的关键字
    default_api_base: str = ""   # 回退 base URL

    # 网关行为
    strip_model_prefix: bool = False  # 重新前缀前移除 "provider/"

    # 每模型参数覆盖
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()

    # OAuth-based Provider 使用 OAuth 流而非 API key
    is_oauth: bool = False

    # Direct Provider 完全绕过 LiteLLM（如 CustomProvider）
    is_direct: bool = False

    # Provider 支持在内容块上使用 cache_control（如 Anthropic prompt caching）
    supports_prompt_caching: bool = False
```

### PROVIDERS 注册表

```python
PROVIDERS: tuple[ProviderSpec, ...] = (
    # === 网关（通过 api_key/api_base 检测，非模型名）===
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        litellm_prefix="openrouter",
        is_gateway=True,
        detect_by_key_prefix="sk-or-",
        supports_prompt_caching=True,
    ),

    # === 标准 Provider（通过模型名关键字匹配）===
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),
        env_key="ANTHROPIC_API_KEY",
        display_name="Anthropic",
        litellm_prefix="",  # LiteLLM 原生识别 "claude-*"，无需前缀
        supports_prompt_caching=True,
    ),

    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt"),
        env_key="OPENAI_API_KEY",
        display_name="OpenAI",
        litellm_prefix="",  # LiteLLM 原生识别 "gpt-*"
    ),

    # === 本地部署 ===
    ProviderSpec(
        name="vllm",
        keywords=("vllm",),
        env_key="HOSTED_VLLM_API_KEY",
        display_name="vLLM/Local",
        litellm_prefix="hosted_vllm",
        is_local=True,
    ),

    # === 更多 Provider... ===
)
```

## 6.2 Provider 接口规范

### LLMProvider 基类

```python
class LLMProvider(ABC):
    """LLM Provider 的抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """发送聊天完成请求。"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型标识符。"""
        pass
```

### LLMResponse 结构

```python
@dataclass
class LLMResponse:
    """LLM 响应。"""
    content: str | None                  # 文本响应
    tool_calls: list[ToolCallRequest]    # 工具调用
    finish_reason: str                   # 完成原因
    reasoning_content: str | None        # 推理内容（Kimi, DeepSeek-R1）
    thinking_blocks: list[dict] | None   # 思考块（Anthropic）

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)
```

### LiteLLM Provider 实现

```python
class LiteLLMProvider(LLMProvider):
    """基于 LiteLLM 的 Provider。"""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        provider_name: str | None = None,
        model: str = "gpt-3.5-turbo",
    ):
        self.api_key = api_key
        self.api_base = api_base
        self.provider_name = provider_name
        self.model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """使用 LiteLLM 调用 LLM。"""
        import litellm

        # 准备参数
        kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools

        if reasoning_effort:
            kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}

        if self.api_key:
            kwargs["api_key"] = self.api_key

        if self.api_base:
            kwargs["api_base"] = self.api_base

        # 调用 LiteLLM
        response = await litellm.acompletion(**kwargs)

        # 解析响应
        return self._parse_response(response)

    def _parse_response(self, response) -> LLMResponse:
        """解析 LiteLLM 响应。"""
        choice = response.choices[0]

        # 解析工具调用
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        # 解析内容
        content = choice.message.content

        # 解析扩展内容
        reasoning_content = None
        if hasattr(choice.message, "reasoning_content"):
            reasoning_content = choice.message.reasoning_content

        thinking_blocks = None
        if hasattr(choice.message, "thinking_blocks"):
            thinking_blocks = choice.message.thinking_blocks

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )
```

## 6.3 添加新 Provider

### 两步添加流程

#### 步骤 1：添加 ProviderSpec

在 [`providers/registry.py`](../nanobot/providers/registry.py) 的 `PROVIDERS` 元组中添加：

```python
PROVIDERS: tuple[ProviderSpec, ...] = (
    # 现有 providers...

    # === 新 Provider 示例 ===
    ProviderSpec(
        name="myprovider",
        keywords=("myprovider", "my-model"),
        env_key="MYPROVIDER_API_KEY",
        display_name="My Provider",
        litellm_prefix="myprovider",  # my-model → myprovider/my-model
        skip_prefixes=("myprovider/",),  # 避免双重前缀
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="mykey-",  # 可选：通过 API key 前缀检测
        detect_by_base_keyword="myprovider",  # 可选：通过 API base URL 检测
        default_api_base="https://api.myprovider.com/v1",
        strip_model_prefix=False,
        model_overrides=(
            # 每模型参数覆盖
            ("my-special-model", {"temperature": 1.0}),
        ),
    ),
)
```

#### 步骤 2：添加配置字段

在 [`config/schema.py`](../nanobot/config/schema.py) 的 `ProvidersConfig` 中添加：

```python
class ProvidersConfig(Base):
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    # ... 现有 providers

    # 新增
    myprovider: MyProviderConfig = Field(default_factory=MyProviderConfig)


class MyProviderConfig(Base):
    """My Provider 配置。"""
    enabled: bool = False
    api_key: str = ""
    api_base: str | None = None
    # ... 其他配置
```

### Provider 类型选择

根据 Provider 特性选择合适的类型：

| 类型 | 适用场景 | 示例 |
|------|----------|------|
| Gateway | 支持多种模型的聚合服务 | OpenRouter, AiHubMix |
| Standard | 单一 Provider 的多种模型 | Anthropic, OpenAI |
| Local | 自托管模型服务 | vLLM, Ollama |
| OAuth | 使用 OAuth 认证 | OpenAI Codex, GitHub Copilot |
| Direct | 自定义 OpenAI 兼容端点 | CustomProvider |

## 6.4 多模型支持

### 模型匹配优先级

```
1. 显式 Provider 前缀
   → "anthropic/claude-3-sonnet" 明确使用 Anthropic

2. API key 前缀检测
   → sk-or-v1-... → OpenRouter

3. API base URL 关键字检测
   → https://aihubmix.com/... → AiHubMix

4. 模型名关键字匹配
   → "claude-3-sonnet" → Anthropic (keywords: "claude")

5. 默认回退
   → OpenAI
```

### 模型路由逻辑

```python
def route_model(
    model: str,
    provider_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> tuple[str, ProviderSpec | None]:
    """路由模型到合适的 Provider。"""

    # 1. 检查网关/本地 Provider（优先）
    gateway_spec = find_gateway(
        provider_name=provider_name,
        api_key=api_key,
        api_base=api_base,
    )
    if gateway_spec:
        model = apply_prefix(model, gateway_spec)
        return model, gateway_spec

    # 2. 匹配标准 Provider
    if provider_name:
        spec = find_by_name(provider_name)
        if spec:
            model = apply_prefix(model, spec)
            return model, spec

    # 3. 通过模型名自动检测
    spec = find_by_model(model)
    if spec:
        model = apply_prefix(model, spec)
        return model, spec

    # 4. 无法匹配
    return model, None


def apply_prefix(model: str, spec: ProviderSpec) -> str:
    """应用 Provider 前缀到模型。"""
    if not spec.litellm_prefix:
        return model

    # 检查是否需要跳过前缀
    if spec.skip_prefixes and any(
        model.startswith(p) for p in spec.skip_prefixes
    ):
        return model

    # 移除旧前缀（如果 strip_model_prefix=True）
    if spec.strip_model_prefix and "/" in model:
        model = model.split("/", 1)[1]

    return f"{spec.litellm_prefix}/{model}"
```

## 6.5 OAuth Provider

### OAuth 流程

```python
class OAuthProvider(LLMProvider):
    """使用 OAuth 认证的 Provider。"""

    def __init__(
        self,
        token_path: str | None = None,
        token: str | None = None,
    ):
        self.token_path = token_path or self._default_token_path()
        self._token = token

    @property
    def token(self) -> str:
        """获取访问令牌。"""
        if self._token:
            return self._token

        # 从文件读取
        if Path(self.token_path).exists():
            return Path(self.token_path).read_text().strip()

        raise ValueError(
            f"OAuth token not found. Please authenticate first."
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs
    ) -> LLMResponse:
        """使用 OAuth 令牌调用。"""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        # API 调用...
        pass

    @staticmethod
    def _default_token_path() -> str:
        """获取默认令牌路径。"""
        config_dir = Path.home() / ".nanobot"
        return str(config_dir / "oauth_tokens")
```

### 认证命令

```bash
# OpenAI Codex 认证
nanobot auth openai-codex

# GitHub Copilot 认证
nanobot auth github-copilot
```

## 6.6 高级特性

### Prompt Caching

某些 Provider（如 Anthropic）支持提示缓存：

```python
class CacheControlMixin:
    """提示缓存控制。"""

    def add_cache_control(
        self,
        messages: list[dict[str, Any]],
        cache_breakpoints: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """添加缓存控制到消息。"""
        if not cache_breakpoints:
            return messages

        result = []
        for i, msg in enumerate(messages):
            new_msg = dict(msg)
            if i in cache_breakpoints:
                # 在系统提示和最后一条用户消息处缓存
                if msg.get("role") in ("system", "user"):
                    if isinstance(new_msg["content"], str):
                        new_msg["content"] = [
                            {"type": "text", "text": new_msg["content"], "cache_control": {"type": "ephemeral"}}
                        ]
                    elif isinstance(new_msg["content"], list):
                        new_msg["content"][-1]["cache_control"] = {"type": "ephemeral"}
            result.append(new_msg)

        return result
```

### 流式响应

```python
async def chat_stream(
    self,
    messages: list[dict[str, Any]],
    on_progress: Callable[[str], Awaitable[None]],
    **kwargs
) -> LLMResponse:
    """流式聊天完成。"""
    import litellm

    full_content = ""
    async for chunk in litellm.acompletion_stream(
        model=self.model,
        messages=messages,
        **kwargs
    ):
        if delta := chunk.choices[0].delta.content:
            full_content += delta
            await on_progress(delta)

    return LLMResponse(content=full_content, ...)
```

## 6.7 下一步

阅读完本章后，建议继续阅读：
- [第7章：配置系统](07-configuration.md) - 学习配置管理
- [第8章：最佳实践](08-best-practices.md) - 学习生产部署
