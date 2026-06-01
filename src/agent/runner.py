import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.agent.events import (
    AgentEvent, TurnStartEvent, MessageDeltaEvent,
    ToolCallStartEvent, ToolCallEndEvent, TurnEndEvent
)
from src.models.ai import UserMessage, AgentContext
from src.tools.slack.attach import AttachTool
from src.tools.explorer.manager import ListFilesTool, SafeLsTool
from src.tools.search.manager import SearchTextTool, SearchFilesTool
from src.tools.test_runner import RunTestsTool

class AgentRunner:
    """
    【推理调度中枢 - 跨平台版】
    负责协调不同平台（Slack/Feishu）事件、加载持久化记忆、驱动推理循环并反馈结果。
    """
    
    def __init__(
        self, 
        messaging_client: Any, # 支持 SlackBot 或 FeishuClient
        loop_engine: Any,      # 实际为 ReActLoop
        sessions_dir: str = "sessions"
    ):
        self.messaging = messaging_client
        self.loop = loop_engine
        self.sessions_dir = Path(sessions_dir).resolve()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # 自动识别平台类型：飞书客户端拥有特定的发送方法
        self.platform = "feishu" if hasattr(self.messaging, "send_markdown") else "slack"

    def _translate_to_host_path(self, sandbox_path: str, channel_id: str) -> str:
        """【路径转译】将沙箱路径转换为宿主机真实路径"""
        prefix = "/workspace/"
        if sandbox_path.startswith(prefix):
            relative_path = sandbox_path[len(prefix):]
            return str(self.sessions_dir / channel_id / relative_path)
        return str(self.sessions_dir / channel_id / sandbox_path.lstrip("/"))

    async def _send_or_update(self, channel_id: str, text: str, msg_id: Optional[str] = None) -> Optional[str]:
        """【统一通讯出口】屏蔽 Slack 与飞书的 API 调用差异"""
        try:
            if self.platform == "slack":
                if not msg_id:
                    res = await self.messaging.web_client.chat_postMessage(channel=channel_id, text=text)
                    return res["ts"]
                else:
                    await self.messaging.web_client.chat_update(channel=channel_id, ts=msg_id, text=text)
                    return msg_id
            else:
                # 飞书模式：使用互动卡片展示 Markdown
                # 飞书暂不支持对发送出去的消息进行增量内容追加（Update 部分限制较多），我们采用“关键节点更新卡片”策略
                res = await self.messaging.send_markdown(channel_id, text)
                return getattr(res.data, "message_id", None) if (res and res.success()) else None
        except Exception as e:
            print(f"[Messaging Error] 消息推送失败: {e}")
            return msg_id

    async def run(self, event: Dict[str, Any]):
        """【推理主入口】兼容多平台事件 payload"""
        channel_id = event["channel"]
        text = event["text"]
        
        # 1. 准备上传回调
        async def upload_fn(sandbox_path: str, title: Optional[str] = None):
            host_path = self._translate_to_host_path(sandbox_path, channel_id)
            print(f"[Runner] 正在从宿主机上传文件: {host_path}")
            await self.messaging.upload_file(channel_id, host_path)

        # 2. 动态挂载/更新工具
        self.loop.tools["attach_file"] = AttachTool(upload_fn=upload_fn)
        self.loop.tools["safe_ls"] = SafeLsTool()
        self.loop.tools["list_files"] = ListFilesTool()
        self.loop.tools["search_text"] = SearchTextTool()
        self.loop.tools["search_files"] = SearchFilesTool()
        self.loop.tools["run_tests"] = RunTestsTool()
        
        # 3. 目录与记忆准备
        channel_dir = self.sessions_dir / channel_id
        channel_dir.mkdir(parents=True, exist_ok=True)
        
        # 【沙箱注入核心逻辑】
        for t_name in [
            "read_file",
            "write_file",
            "edit_file",
            "execute_bash",
            "safe_ls",
            "list_files",
            "search_text",
            "search_files",
            "run_tests",
        ]:
            if t_name in self.loop.tools:
                tool_instance = self.loop.tools[t_name]
                target_attr = "cwd" if t_name == "execute_bash" else "base_path"
                if hasattr(tool_instance, target_attr):
                    setattr(tool_instance, target_attr, str(channel_dir))
                    print(f"DEBUG: [全量锁定] 工具 {t_name} 已绑定路径属性 {target_attr}: {channel_dir}")

        # 【记忆持久化核心】：加载或初始化该频道的会话记录
        session_file = self.sessions_dir / f"{channel_id}.jsonl"
        from src.agent.session import SessionManager
        from src.models.messages import UserMessage, TextContent
        
        if session_file.exists():
            print(f"DEBUG: [记忆恢复] 正在加载历史: {session_file.name}")
            manager = SessionManager.load_from_file(str(session_file))
        else:
            print(f"DEBUG: [记忆初始化] 为频道 {channel_id} 创建新会话")
            from src.agent.session import SessionHeader
            manager = SessionManager(str(session_file))
            manager.header = SessionHeader(id=channel_id)
            with open(str(session_file), "w", encoding="utf-8") as f:
                f.write(manager.header.model_dump_json() + "\n")

        # 记录本次请求
        new_user_msg = UserMessage(role="user", content=[TextContent(text=text)])
        manager.append_message(new_user_msg)

        memory_text = self._load_memory(channel_id)
        system_prompt = self._build_system_prompt(channel_id, memory_text, event)
        
        # 4. 初始化具备“历史视野”的任务上下文
        context = manager.get_context(system_prompt=system_prompt)
        context.max_iterations = 10
        persisted_message_ids = {msg.uuid for msg in context.messages}
        
        # 5. [核心] 发起实时交互
        msg_id = await self._send_or_update(channel_id, "_Agent 正在思考中..._ (Thinking)")
        
        final_answer = ""
        try:
            async for ev in self.loop.run_loop(context):
                if isinstance(ev, MessageDeltaEvent):
                    if "[Thinking]" not in ev.content:
                        final_answer += ev.content

                        if self.platform == "slack" and len(final_answer) % 100 == 0:
                            await self._send_or_update(channel_id, final_answer + "...", msg_id)
                
                elif isinstance(ev, ToolCallStartEvent):
                    status_text = f"{final_answer}\n\n_→ 正在调用工具: `{ev.tool_name}`..._"
                    await self._send_or_update(channel_id, status_text, msg_id)
                
                elif isinstance(ev, TurnEndEvent):
                    for message in context.messages:
                        if message.uuid in persisted_message_ids:
                            continue
                        if message.msg_type == "synthetic":
                            continue
                        manager.append_message(message)
                        persisted_message_ids.add(message.uuid)

            # 6. 推理结束，呈现最终结果并落盘记忆
            if final_answer.strip() == "[SILENT]":
                if self.platform == "slack" and msg_id:
                    await self.messaging.web_client.chat_delete(channel=channel_id, ts=msg_id)
            else:
                await self._send_or_update(channel_id, final_answer or "_对话结束_", msg_id)
            
            print(f"DEBUG: [记忆已固化] 频道 {channel_id} 的历史已更新。")
                
        except Exception as e:
            await self._send_or_update(channel_id, f"❌ 系统中断: {str(e)}", msg_id)
            print(f"[Runner Error] {e}")

    def _load_memory(self, channel_id: str) -> str:
        """【分层记忆加载】读取全局记忆和频道私有记忆"""
        memory_parts = []
        global_mem = self.sessions_dir / "MEMORY.md"
        if global_mem.exists():
            memory_parts.append(f"### Global Workspace Memory\n{global_mem.read_text(encoding='utf-8')}")
        
        channel_mem = self.sessions_dir / channel_id / "MEMORY.md"
        if channel_mem.exists():
            memory_parts.append(f"### Channel-Specific Memory\n{channel_mem.read_text(encoding='utf-8')}")
            
        return "\n\n".join(memory_parts) if memory_parts else "(No working memory yet)"

    def _build_system_prompt(self, channel_id: str, memory: str, event: Dict[str, Any]) -> str:
        """【指令工程师】构建 System Prompt"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 动态调整格式化要求：如果是飞书，支持标准 Markdown
        formatting_rule = "Use standard MarkDown." if self.platform == "feishu" else "Use *bold* for bold, _italic_ for italic (Slack mrkdwn)."
        
        return f"""You are LiteAct, a cross-platform AI Assistant.
Current Time: {now}
Target Platform: {self.platform.upper()}

## Formatting Rules
{formatting_rule}

## Memory
{memory}

## Environment
You run in a sandbox. Workspace root: /workspace/
All your files for this channel must stay in /workspace/. 
Use `safe_ls` to explore directory structures (it's cleaner and safer than bare bash `ls`).
Use `edit_file` for small, precise text replacements when the target snippet appears exactly once.
Use `execute_bash` to download resources (e.g., via `git clone` or `curl`) or run complex analysis scripts.
Use `attach_file` to send generated artifacts to the user.

Respond with [SILENT] only if no output text is needed.
"""
