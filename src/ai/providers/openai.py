import os
import json
from typing import List, AsyncGenerator, Optional, Dict, Any
from openai import AsyncOpenAI
import openai
from src.models.ai import (
    AgentMessage, UserMessage, AssistantMessage, ToolResultMessage,
    TextDelta, ThinkingDelta, ToolCallDelta, UsageEvent, StreamEvent,
    Usage, CostInfo, ToolCall
)

class OpenAIProvider:
    """
    【OpenAI 适配器】
    负责将 LiteAct 的统一协议与 OpenAI 的 API 进行双向翻译。
    """

    def __init__(
        self, 
        api_key: Optional[str] = None, 
        base_url: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None
    ):
        # 1. 客户端初始化：优先从参数读取，其次环境变量
        self.client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            default_headers=default_headers
        )

    def _convert_messages(
        self, 
        messages: List[AgentMessage], 
        system_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        【消息翻译器】将通用消息转换为 OpenAI 格式。
        """
        openai_msgs = []
        
        # 1. 优先注入系统提示词 (System Prompt)
        if system_prompt:
            openai_msgs.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if isinstance(msg, UserMessage):
                # 用户消息：如果是列表 content，必须转换为纯字典列表
                if isinstance(msg.content, list):
                    # 关键修复：DashScope 拒绝接收 Pydantic 对象，必须是纯 Dict
                    converted_content = [
                        block.model_dump() if hasattr(block, "model_dump") else block 
                        for block in msg.content
                    ]
                    openai_msgs.append({"role": "user", "content": converted_content})
                else:
                    openai_msgs.append({"role": "user", "content": msg.content})
            
            elif isinstance(msg, AssistantMessage):
                # 助手消息：需要处理内容块
                content_text = ""
                tool_calls = []
                for block in msg.content:
                    if block.type == "text":
                        content_text += block.text
                    elif block.type == "toolCall":
                        # OpenAI 格式：tool_calls 必须是一个特定的列表
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.arguments)
                            }
                        })
                
                # 处理空内容（有些 API 报错 content 不能为空）
                entry = {"role": "assistant", "content": content_text or ""}
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                openai_msgs.append(entry)

            elif isinstance(msg, ToolResultMessage):
                # 工具结果：OpenAI 要求 role 必须为 'tool'，且带上 tool_call_id
                # 将 content 转换为纯文本字符串（OpenAI 的 tool 角色通常只接受字符串）
                text_content = ""
                for block in msg.content:
                    if block.type == "text":
                        text_content += block.text
                
                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": text_content
                })
        
        return openai_msgs

    async def stream(
        self, 
        model: str, 
        messages: List[AgentMessage], 
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning_effort: Optional[str] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        【核心流式接口】驱动模型输出并产出统一事件。
        """
        openai_msgs = self._convert_messages(messages, system_prompt=system_prompt)
        
        # 构造请求参数
        params = {
            "model": model,
            "messages": openai_msgs,
            "stream": True,
            "stream_options": {"include_usage": True} # 确保最后一帧有 Token 统计
        }
        if tools:
            params["tools"] = tools
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort

        # 准备缓存，用于累加 Tool Call 的碎片
        # key 是 tool_call 的 index (0, 1, 2...)
        tool_call_buffer: Dict[int, Dict[str, Any]] = {}

        try:
            response = await self.client.chat.completions.create(**params)
            
            async for chunk in response:
                if not chunk.choices:
                    # 这通常是最后一帧，包含了 usage 数据
                    if chunk.usage:
                        yield UsageEvent(usage=Usage(
                            input=chunk.usage.prompt_tokens,
                            output=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens
                        ))
                    continue

                delta = chunk.choices[0].delta
                
                # 1. 捕获文本增量
                if delta.content:
                    yield TextDelta(delta=delta.content)
                
                # 2. 捕获推理逻辑增量 (针对 o1/o3 模型)
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    yield ThinkingDelta(delta=delta.reasoning_content)

                # 3. 捕获并累加工具调用增量
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_buffer:
                            # 第一次见到这个索引的工具调用
                            tool_call_buffer[idx] = {
                                "id": tc_delta.id,
                                "name": tc_delta.function.name,
                                "arguments": ""
                            }
                        
                        if tc_delta.function.arguments:
                            # 累加 JSON 字符串片段
                            tool_call_buffer[idx]["arguments"] += tc_delta.function.arguments
                            
                        # (可选) 如果你想在最后才发送，可以等所有结束后循环 buffer
                        # 在这里，我们选择在每一次 arguments 入账时，发送一份“快照”
                        # 确保前端/逻辑层能实时看到进度
                        try:
                            # 尝试解析 JSON，如果还没收全，loads 会失败，我们暂不发送
                            args_json = json.loads(tool_call_buffer[idx]["arguments"])
                            yield ToolCallDelta(tool_call=ToolCall(
                                id=tool_call_buffer[idx]["id"],
                                name=tool_call_buffer[idx]["name"],
                                arguments=args_json
                            ))
                        except json.JSONDecodeError:
                            # JSON 片段尚不完整，继续等待后续 chunks
                            pass

        except Exception as e:
            # 交给上层 ReActLoop 统一转换为用户可读的错误信息。
            raise e
