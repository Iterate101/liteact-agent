import json
import os
from typing import List, Optional, Callable, Dict, Any
from pathlib import Path
from src.models.ai import AgentMessage, UserMessage, AssistantMessage, ToolResultMessage, TextContent

class MemoryManager:
    """
    【智慧记忆管家】
    支持消息链回溯（Parent-Child Chain）和基于 LLM 的历史压缩。
    """
    
    def __init__(self, storage_path: str, bootstrap_path: Optional[str] = None):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.bootstrap_path = Path(bootstrap_path) if bootstrap_path else None
        self._latest_uuid: Optional[str] = None

    def load_bootstrap(self) -> List[AgentMessage]:
        """【引导记忆】从外部 Markdown 加载静态规则"""
        if not self.bootstrap_path or not self.bootstrap_path.exists():
            return []
        
        content = self.bootstrap_path.read_text(encoding="utf-8")
        # 将引导内容作为最高优先级的系统消息包装类
        return [UserMessage(
            role="user", 
            content=f"### BOOTSTRAP MEMORY ###\n{content}",
            msg_type="bootstrap"
        )]

    def append(self, message: AgentMessage):
        """【记录追加】建立链路并存入磁盘"""
        # 如果消息没有显式指定父亲，则自动挂载到当前会话的末尾
        if not message.parent_uuid and self._latest_uuid:
            message.parent_uuid = self._latest_uuid
            
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(message.model_dump_json() + "\n")
            
        self._latest_uuid = message.uuid

    def get_context_chain(self, start_uuid: Optional[str] = None) -> List[AgentMessage]:
        """【链式回溯】从指定或最新的节点向上寻找，直到遇到 Compaction 或根节点"""
        target_uuid = start_uuid or self._latest_uuid
        if not target_uuid:
            return []

        # 1. 一次性加载所有消息索引（内存索引化，适合中型对话）
        all_msgs: Dict[str, AgentMessage] = {}
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        # 这里我们需要一点技巧来从 role 恢复 Pydantic 模型
                        role = data.get("role")
                        if role == "user": msg = UserMessage(**data)
                        elif role == "assistant": msg = AssistantMessage(**data)
                        elif role == "toolResult": msg = ToolResultMessage(**data)
                        else: continue
                        all_msgs[msg.uuid] = msg
                    except Exception:
                        continue

        # 2. 爬岩逻辑
        chain = []
        curr_uuid = target_uuid
        while curr_uuid and curr_uuid in all_msgs:
            msg = all_msgs[curr_uuid]
            chain.append(msg)
            
            # 如果撞到“摘要节点”，停止回溯，它就是历史的终极防火墙
            if msg.msg_type == "compaction":
                break
                
            curr_uuid = msg.parent_uuid
            
        # 3. 翻转顺序（从旧到新）
        return list(reversed(chain))

    async def compact_history(
        self, 
        summarizer_fn: Callable[[List[AgentMessage]], Any], 
        threshold: int = 20
    ):
        """
        【自动压缩逻辑】
        当消息链超过阈值时，调用 LLM 对前半部分生成摘要，并创建一个 Compaction 节点。
        """
        full_chain = self.get_context_chain()
        if len(full_chain) <= threshold:
            return

        # 提取需要压缩的段落（例如前 15 条）
        to_compress = full_chain[:-5] # 保留最后 5 条作为新鲜上下文
        keep_recent = full_chain[-5:]
        
        print(f"DEBUG: [记忆压缩] 正在合并 {len(to_compress)} 条历史记录...")
        
        # 调用 LLM 生成摘要（由外部注入)
        summary_text = await summarizer_fn(to_compress)
        
        # 创建一个特殊的 Compaction 节点
        # 它没有父节点（或者它作为当前新链路的起点），但它包含摘要。
        compaction_node = AssistantMessage(
            role="assistant",
            content=[TextContent(text=f"### HISTORY SUMMARY ###\n{summary_text}")],
            msg_type="compaction",
            # 它链接到这些被压缩消息最开始的那个 parent，或者是 None
            parent_uuid=to_compress[0].parent_uuid 
        )
        
        # 写入 Compaction 节点
        self.append(compaction_node)
        
        # 关键操作：将保留的最近消息的第一个节点的 parent 指向这个 Compaction 节点
        # 从而在逻辑上切断旧链条，接入新节点。
        # 注意：由于 append 逻辑会自动挂载到最新节点，所以我们只需要顺着 append 最近的几条即可
        for msg in keep_recent:
            self.append(msg)
            
        print("✅ 记忆压缩完成。")
