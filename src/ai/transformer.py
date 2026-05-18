import time
from typing import List, Optional, Callable, Dict, Set
from src.models.ai import (
    AgentMessage, UserMessage, AssistantMessage, ToolResultMessage,
    TextContent, ThinkingContent, ToolCall
)

def transform_messages(
    messages: List[AgentMessage],
    current_model_id: str,
    current_provider: str,
    normalize_id_func: Optional[Callable[[str], str]] = None
) -> List[AgentMessage]:
    """
    【消息变形器】
    1. 标准化：调整不同厂商间的工具 ID 长度限制。
    2. 降级：处理跨模型切换时的推理内容 (Thinking) 兼容性。
    3. 补全：修复因为中断导致的孤立工具请求 (Orphaned calls)。
    """
    
    # 步骤 A：Pass 1 - 内容降级与 ID 映射建立
    # -----------------------------------------------
    tool_id_map: Dict[str, str] = {}
    phase1_messages: List[AgentMessage] = []

    for msg in messages:
        if isinstance(msg, UserMessage):
            phase1_messages.append(msg)
            continue

        if isinstance(msg, ToolResultMessage):
            # 如果我们有 ID 映射（比如从长 ID 映射到短 ID），这里需要对齐
            new_id = tool_id_map.get(msg.tool_call_id, msg.tool_call_id)
            # 创建新副本来保持不可变性
            new_msg = msg.model_copy(update={"tool_call_id": new_id})
            phase1_messages.append(new_msg)
            continue

        if isinstance(msg, AssistantMessage):
            # 判定：是否是同一个厂商同一个模型？
            is_same_model = (
                msg.provider == current_provider and 
                msg.model == current_model_id
            )

            new_content = []
            for block in msg.content:
                if block.type == "thinking":
                    # 规则：加密的推理内容 (redacted) 只能给原模型看
                    if block.redacted:
                        if is_same_model:
                            new_content.append(block)
                        continue # 跨模型则丢弃加密内容

                    if is_same_model:
                        new_content.append(block)
                    else:
                        # 降级：将推理内容转为普通文本，让新模型也能懂思绪
                        if block.thinking and block.thinking.strip():
                            new_content.append(TextContent(text=block.thinking))

                elif block.type == "toolCall":
                    # ID 标准化处理
                    new_id = block.id
                    if not is_same_model and normalize_id_func:
                        new_id = normalize_id_func(block.id)
                        tool_id_map[block.id] = new_id
                    
                    new_content.append(block.model_copy(update={"id": new_id}))
                
                else:
                    new_content.append(block)

            phase1_messages.append(msg.model_copy(update={"content": new_content}))

    # 步骤 B：Pass 2 - 结构拓扑补全 (Orphaned Calls Fix)
    # -----------------------------------------------
    final_result: List[AgentMessage] = []
    pending_calls: List[ToolCall] = []        # 尚未收到反馈的工具调用
    received_result_ids: Set[str] = set()    # 当前轮次已收到的结果 ID

    def push_synthetic_results():
        """闭包函数：为那些掉队的工具调用生成‘占位’结果"""
        nonlocal pending_calls, received_result_ids
        for tc in pending_calls:
            if tc.id not in received_result_ids:
                final_result.append(ToolResultMessage(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=[TextContent(text="No result provided due to session interruption.")],
                    is_error=True,
                    details={"synthetic": True, "reason": "session_interruption"},
                    msg_type="synthetic",
                    timestamp=int(time.time() * 1000)
                ))
        pending_calls = []
        received_result_ids = set()

    for msg in phase1_messages:
        # 脏数据清理：如果 AI 话还没说完就报错/中断了，这条“残篇”不能喂给下一个模型
        if isinstance(msg, AssistantMessage):
            if msg.stop_reason in ["error", "aborted"]:
                continue # 丢弃坏掉的消息，触发模型从上个稳定状态重试

            # 在新回合开始前，先清理上一轮可能遗留的掉队调用
            if pending_calls:
                push_synthetic_results()

            # 登记本轮产出的所有工具调用
            new_calls = [b for b in msg.content if b.type == "toolCall"]
            if new_calls:
                pending_calls = new_calls
                received_result_ids = set()
            
            final_result.append(msg)

        elif isinstance(msg, ToolResultMessage):
            received_result_ids.add(msg.tool_call_id)
            final_result.append(msg)

        elif isinstance(msg, UserMessage):
            # 人类插嘴了，必须先结算完之前的工具流
            if pending_calls:
                push_synthetic_results()
            final_result.append(msg)
        
        else:
            final_result.append(msg)

    # 【核心修正】：终场扫除
    # 如果最后一条消息是 Assistant 但缺失了结果，在这里进行最后的补全
    if pending_calls:
        push_synthetic_results()

    return final_result
