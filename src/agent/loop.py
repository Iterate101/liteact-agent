import asyncio
import json
from typing import AsyncGenerator, List, Optional, Dict, Literal, Any
from src.models.ai import (
    AgentContext, AgentMessage, UserMessage, AssistantMessage, 
    ToolResultMessage, ToolCall, TextContent, ThinkingContent,
    TextDelta, ThinkingDelta, ToolCallDelta, UsageEvent
)
from src.agent.events import (
    AgentEvent, TurnStartEvent, MessageDeltaEvent,
    ToolCallStartEvent, ToolCallEndEvent, TurnEndEvent
)
from src.tools.base import AgentTool, AgentToolResult
from src.tools.registry import build_default_tools
from src.ai.stream import stream_chat
from src.ai.transformer import transform_messages

class ReActLoop:
    """
    【推理中枢 - 工业集成版】
    实现真实的推理与行动循环。
    """
    
    def __init__(
        self, 
        model_id: str = "gpt-4o", 
        api_type: str = "openai-responses"
    ):
        self.model_id = model_id
        self.api_type = api_type
        # 建立默认工具注册表。这样 ReActLoop、测试和文档都能围绕同一个默认工具来源对齐。
        self.tools: Dict[str, AgentTool] = build_default_tools()

    def _get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """将本地 AgentTool 协议转换为 OpenAI 定义格式"""
        openai_tools = []
        for name, tool in self.tools.items():
            # 假设 AgentTool 协议包含 name, description 和 parameters (JSON Schema)
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return openai_tools

    def _format_inference_error(self, error: Exception) -> str:
        """将底层模型异常转换成面向用户的中文提示"""
        raw_message = str(error)
        if (
            self.api_type == "dashscope"
            and (
                "AllocationQuota.FreeTierOnly" in raw_message
                or "free tier of the model has been exhausted" in raw_message
            )
        ):
            return (
                "DashScope 返回 403：当前模型的免费额度已经用完。\n\n"
                "你可以选择其中一种处理方式：\n"
                "1. 在 DashScope 控制台关闭 use free tier only 模式，并开通付费调用。\n"
                "2. 切换到还有额度的 DashScope 模型，例如设置 $env:MODEL_ID=\"qwen-plus\" 后重启。\n"
                "3. 如果你有 OpenAI Key，可以设置 $env:API_TYPE=\"openai-responses\" 和 $env:MODEL_ID=\"gpt-4o\" 后重启。\n\n"
                f"原始错误: {raw_message}"
            )
        return raw_message

    async def run_loop(
        self, 
        context: AgentContext, 
        max_turns: int = 10,
        timeout_per_frame: int = 60
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        异步生成器：驱动真实的 AI 思考、工具调用与结果反馈闭环。
        """
        turn_count = 0
        
        while turn_count < max_turns:
            turn_count += 1
            yield TurnStartEvent()

            # 1. 对话历史自愈与修补 (Self-Healing)
            # 在喂给 AI 之前，先修补因为中断导致的孤儿工具调用
            context.messages = transform_messages(
                context.messages,
                self.model_id,
                self.api_type
            )

            # 准备本次推理产生的收集桶
            current_assistant_content = []
            current_usage = None
            
            # 2. 启动流式推理 (Call Real AI)
            try:
                # 转换工具规格
                openai_tools = self._get_openai_tools_schema()
                
                # 启动真正的流式连接
                ai_stream = stream_chat(
                    model_id=self.model_id,
                    api_type=self.api_type,
                    messages=context.messages,
                    system_prompt=context.system_prompt,
                    tools=openai_tools,
                    timeout=timeout_per_frame
                )
                
                async for event in ai_stream:
                    # 捕获 4 种统一事件
                    if isinstance(event, TextDelta):
                        # 文本增量：发送给 UI，并存入当前消息块
                        yield MessageDeltaEvent(content=event.delta)
                        # 为了演示简单，我们假设每一轮只产生一个文本块，这里进行累加
                        if not current_assistant_content or current_assistant_content[-1].type != "text":
                            current_assistant_content.append(TextContent(text=event.delta))
                        else:
                            current_assistant_content[-1].text += event.delta
                            
                    elif isinstance(event, ThinkingDelta):
                        # 思考增量：让用户看到 AI 的心路历程
                        yield MessageDeltaEvent(content=f"\n[Thinking] {event.delta}")
                        if not current_assistant_content or current_assistant_content[-1].type != "thinking":
                            current_assistant_content.append(ThinkingContent(thinking=event.delta))
                        else:
                            current_assistant_content[-1].thinking += event.delta
                            
                    elif isinstance(event, ToolCallDelta):
                        # 工具调用：如果是最后一个更新，记录它
                        # 在流式中，我们会收到多次同一个工具的快照，我们只关心最新的
                        tc = event.tool_call
                        # 查找是否已经存在这个 ID 的调用，存在则替换
                        found = False
                        for i, block in enumerate(current_assistant_content):
                            if block.type == "toolCall" and block.id == tc.id:
                                current_assistant_content[i] = tc
                                found = True
                                break
                        if not found:
                            current_assistant_content.append(tc)
                            # 广播：AI 决定要动真格的了！
                            yield ToolCallStartEvent(
                                tool_call_id=tc.id, 
                                tool_name=tc.name, 
                                arguments=json.dumps(tc.arguments)
                            )
                            
                    elif isinstance(event, UsageEvent):
                        current_usage = event.usage

            except Exception as e:
                yield MessageDeltaEvent(content=f"\n[Error] 推理异常: {self._format_inference_error(e)}")
                break

            # 3. 构造本次的助手消息对象
            assistant_msg = AssistantMessage(
                role="assistant",
                content=current_assistant_content,
                usage=current_usage if current_usage else None,
                model=self.model_id,
                provider=self.api_type
            )
            
            # 将 AI 的回复存入上下文
            context.messages.append(assistant_msg)

            # 4. 判断是否需要执行工具
            tool_calls = [c for c in assistant_msg.content if c.type == "toolCall"]
            
            if not tool_calls:
                # 活干完了，退出循环
                yield TurnEndEvent(message=assistant_msg)
                break

            # 5. 统一调度 (Structured Executing)
            # 每个工具调用都保留自己的 ToolCall 引用，避免未知工具导致结果错位。
            tool_jobs = []
            for tc in tool_calls:
                tool = self.tools.get(tc.name)
                if tool:
                    tool_jobs.append(
                        (tc, tool.execute(tc.id, tc.arguments))
                    )
                else:
                    tool_jobs.append((tc, None))

            # 并发执行。return_exceptions=True 可以把单个工具异常转成结果，
            # 避免一个工具失败就打断整轮 Agent 流程。
            runnable_jobs = [job for _, job in tool_jobs if job is not None]
            raw_results = await asyncio.gather(*runnable_jobs, return_exceptions=True)
            result_iter = iter(raw_results)

            # 6. 将结果塞回上下文，并广播事件
            for tc, job in tool_jobs:
                if job is None:
                    res = AgentToolResult(
                        content=[TextContent(text=f"未知工具: {tc.name}")],
                        is_error=True
                    )
                else:
                    raw_result = next(result_iter)
                    if isinstance(raw_result, Exception):
                        res = AgentToolResult(
                            content=[TextContent(text=f"工具执行异常: {str(raw_result)}")],
                            is_error=True
                        )
                    else:
                        res = raw_result

                yield ToolCallEndEvent(
                    tool_call_id=tc.id,
                    result=res.content,
                    is_error=res.is_error
                )
                
                context.messages.append(ToolResultMessage(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=res.content,
                    details=res.details,
                    is_error=res.is_error
                ))

            yield TurnEndEvent(message=assistant_msg)
