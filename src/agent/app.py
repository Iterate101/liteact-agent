import asyncio
import os
from typing import AsyncGenerator, Optional, List
from src.agent.session import SessionManager
from src.agent.loop import ReActLoop
from src.agent.events import AgentEvent, TurnEndEvent, FinalEvent
from src.agent.trace import TaskTraceRecorder
from src.models.messages import (
    AgentContext, AgentMessage, UserMessage, 
    AssistantMessage, TextContent
)

class AgentSession:
    """
    【智能体入口门面】
    将 SessionManager (记忆) 与 ReActLoop (大脑) 完美融合。
    让你可以通过简单的 `session.prompt("任务")` 驱动复杂的 ReAct 循环。
    """
    
    def __init__(
        self, 
        session_id: str, 
        storage_path: str = "sessions",
        model_id: str = "gpt-4o",
        api_type: str = "openai-responses",
        system_prompt: Optional[str] = None
    ):
        self.system_prompt = system_prompt or ""

        # 1. 确保存储目录存在
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
            
        # 2. 构造完整的文件路径
        file_path = f"{storage_path}/{session_id}.jsonl"
        
        # 3. 初始化记忆引擎
        if os.path.exists(file_path):
            self.manager = SessionManager.load_from_file(file_path)
        else:
            # 【核心修正】：手动初始化一个干净的 Manager 并写入 Header
            from src.agent.session import SessionHeader
            self.manager = SessionManager(file_path)
            self.manager.header = SessionHeader(id=session_id)
            # 立即写入头部行，建立文件规范
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(self.manager.header.model_dump_json() + "\n")

        # 4. 初始化核心逻辑循环（大脑）
        # 将选定的模型配置注入到大脑中
        self.loop = ReActLoop(model_id=model_id, api_type=api_type)

    async def prompt(self, text: str) -> AsyncGenerator[AgentEvent, None]:
        """
        主交互接口。
        """
        # A. 准备上下文
        context = self.manager.get_context(system_prompt=self.system_prompt)
        
        # B. 记录并追加用户的新提问
        # 【修正】：必须使用具体的 UserMessage 类实例化
        user_msg = UserMessage(
            role="user", 
            content=[TextContent(text=text)]
        )
        # 将用户消息存入内存上下文
        context.messages.append(user_msg)
        # 立即落盘持久化，确保万一断电也能找回
        self.manager.append_message(user_msg)
        persisted_message_ids = {msg.uuid for msg in context.messages}
        trace_recorder = TaskTraceRecorder(
            trace_dir=os.path.join(os.path.dirname(self.manager.file_path), "traces"),
            session_id=self.manager.header.id if self.manager.header else "unknown",
            task=text,
        )

        # C. 驱动循环
        # 我们使用异步迭代器来监听 Loop 产生的每一个事件
        try:
            async for event in self.loop.run_loop(context):
                trace_recorder.append_event(event)
                
                # --- 自动持久化钩子 (Persistence Hooks) ---
                # 如果一轮推理结束了，我们需要把 Loop 新增的助手消息和工具结果都记录下来。
                if isinstance(event, TurnEndEvent):
                    for message in context.messages:
                        if message.uuid in persisted_message_ids:
                            continue
                        if message.msg_type == "synthetic":
                            continue
                        self.manager.append_message(message)
                        persisted_message_ids.add(message.uuid)
                elif isinstance(event, FinalEvent):
                    trace_recorder.close(status=event.status, summary=event.summary)
                
                # 将事件抛给外层调用者（如 CLI 或 Web UI）
                yield event
        finally:
            trace_recorder.close(status="done")

    def load_history(self) -> List[AgentMessage]:
        """获取当前会话的全部历史消息"""
        return self.manager.get_context().messages
