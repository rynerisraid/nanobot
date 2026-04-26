"""ACP (Agent Client Protocol) tool for interacting with Claude Code and other ACP-compatible agents."""

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool


class ACPTool(Tool):
    """Tool for interacting with ACP-compatible agents (Claude Code, etc.)."""

    # ACP 代理类型
    AGENT_CLAUDE = "claude"
    AGENT_CODEX = "codex"

    # 支持的操作
    ACTION_NEW = "new"
    ACTION_PROMPT = "prompt"
    ACTION_LIST = "list"
    ACTION_DELETE = "delete"

    def __init__(
        self,
        acpx_path: str = "acpx",
        agent: str = AGENT_CLAUDE,
        session_timeout: int = 3600,
        default_model: str | None = None,
    ):
        """
        Initialize ACP tool.

        Args:
            acpx_path: Path to acpx executable (or npx command for npm-based ACP)
            agent: ACP agent type (claude, codex, etc.)
            session_timeout: Session timeout in seconds
            default_model: Optional default model to use
        """
        self._acpx_path = acpx_path
        self._agent = agent
        self._session_timeout = session_timeout
        self._default_model = default_model

        # 会话状态管理: {session_key: {"name": session_name, "created": datetime, "last_used": datetime}}
        self._sessions: dict[str, dict[str, Any]] = {}

        # 上下文信息
        self._channel = "cli"
        self._chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the context for session management."""
        self._channel = channel
        self._chat_id = chat_id
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "acp"

    @property
    def description(self) -> str:
        return (
            "Interact with ACP-compatible AI agents (Claude Code, etc.) for code analysis, "
            "review, and documentation. Supports session-based conversations for context continuity."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [self.ACTION_NEW, self.ACTION_PROMPT, self.ACTION_LIST, self.ACTION_DELETE],
                    "description": (
                        f"Action to perform: '{self.ACTION_NEW}' to create a new session, "
                        f"'{self.ACTION_PROMPT}' to send a prompt to existing session, "
                        f"'{self.ACTION_LIST}' to list active sessions, "
                        f"'{self.ACTION_DELETE}' to delete a session."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "The prompt/message to send to the ACP agent (required for 'prompt' action).",
                },
                "session": {
                    "type": "string",
                    "description": "Optional session name. If not provided, uses the current chat session.",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        prompt: str | None = None,
        session: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute the ACP tool action."""
        try:
            # 使用会话参数或当前上下文会话
            session_key = session or self._session_key

            # 清理过期会话
            self._cleanup_expired_sessions()

            if action == self.ACTION_NEW:
                return await self._create_session(session_key)
            elif action == self.ACTION_PROMPT:
                if not prompt:
                    return "Error: 'prompt' parameter is required for 'prompt' action"
                return await self._send_prompt(session_key, prompt)
            elif action == self.ACTION_LIST:
                return self._list_sessions()
            elif action == self.ACTION_DELETE:
                return self._delete_session(session_key)
            else:
                return f"Error: Unknown action '{action}'"
        except Exception as e:
            logger.error("ACP tool error: {}", e)
            return f"Error executing ACP action: {str(e)}"

    async def _create_session(self, session_key: str) -> str:
        """Create a new ACP session."""
        # 检查会话是否已存在
        if session_key in self._sessions:
            return f"Session '{session_key}' already exists. Use action='prompt' to send messages."

        # 生成唯一的会话名称
        session_name = f"nanobot-{self._agent}-{session_key.replace(':', '-')}"

        # 构建 acpx 命令
        cmd = [self._acpx_path, self._agent, "sessions", "new", "--name", session_name]

        try:
            result = await self._run_command(cmd)

            # 保存会话信息
            self._sessions[session_key] = {
                "name": session_name,
                "created": datetime.now(),
                "last_used": datetime.now(),
            }

            logger.info("ACP session created: {}", session_name)
            return f"ACP session created: {session_name}\n{result}"
        except Exception as e:
            logger.error("Failed to create ACP session: {}", e)
            return f"Failed to create ACP session: {str(e)}"

    async def _send_prompt(self, session_key: str, prompt: str) -> str:
        """Send a prompt to an existing ACP session."""
        # 检查会话是否存在
        if session_key not in self._sessions:
            # 尝试自动创建会话
            create_result = await self._create_session(session_key)
            if "Failed to create" in create_result:
                return create_result

        session_info = self._sessions[session_key]
        session_name = session_info["name"]

        # 构建 acpx 命令
        cmd = [self._acpx_path, self._agent, "-s", session_name, prompt]

        try:
            result = await self._run_command(cmd)

            # 更新最后使用时间
            session_info["last_used"] = datetime.now()

            logger.info("ACP prompt sent to session: {}", session_name)
            return result
        except Exception as e:
            logger.error("Failed to send ACP prompt: {}", e)
            return f"Failed to send prompt to ACP session: {str(e)}"

    def _list_sessions(self) -> str:
        """List all active ACP sessions."""
        if not self._sessions:
            return "No active ACP sessions."

        lines = ["Active ACP sessions:"]
        now = datetime.now()

        for session_key, info in self._sessions.items():
            last_used = info["last_used"].strftime("%Y-%m-%d %H:%M:%S")
            age = (now - info["last_used"]).total_seconds()
            lines.append(f"  - {session_key} ({info['name']}): last used {last_used} ({int(age)}s ago)")

        return "\n".join(lines)

    def _delete_session(self, session_key: str) -> str:
        """Delete an ACP session."""
        if session_key not in self._sessions:
            return f"Session '{session_key}' not found."

        session_name = self._sessions[session_key]["name"]
        del self._sessions[session_key]

        logger.info("ACP session deleted: {}", session_name)
        return f"ACP session '{session_name}' deleted."

    def _cleanup_expired_sessions(self) -> None:
        """Remove sessions that have exceeded the timeout."""
        now = datetime.now()
        expired_keys = []

        for session_key, info in self._sessions.items():
            age = (now - info["last_used"]).total_seconds()
            if age > self._session_timeout:
                expired_keys.append(session_key)

        for key in expired_keys:
            logger.info("ACP session expired: {}", self._sessions[key]["name"])
            del self._sessions[key]

    async def _run_command(self, cmd: list[str], timeout: int = 120) -> str:
        """
        Run an acpx command and return its output.

        Args:
            cmd: Command and arguments as a list
            timeout: Command timeout in seconds

        Returns:
            Command output as string
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: Command timed out after {timeout} seconds"

            output_parts = []

            if stdout:
                stdout_text = stdout.decode("utf-8", errors="replace")
                if stdout_text.strip():
                    output_parts.append(stdout_text)

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # 截断过长的输出
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except FileNotFoundError:
            return f"Error: ACP executable not found at '{self._acpx_path}'. Please ensure ACP is installed and configured correctly."
        except Exception as e:
            return f"Error executing command: {str(e)}"
