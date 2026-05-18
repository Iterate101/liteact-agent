import json
import uuid
import os
from datetime import datetime
from typing import List, Optional, Dict, Union
from pydantic import BaseModel, Field
from src.models.messages import AgentMessage, AgentContext

# --- 第一部分：底层协议模型 (Protocol Models) ---

class SessionHeader(BaseModel):
    """
    【会话头部】存储整个文件的元数据
    """
    type: str = "session"
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    cwd: str = Field(default_factory=lambda: os.getcwd())

class SessionEntry(BaseModel):
    """
    【消息条目】包裹每一条 AgentMessage，并建立树形联系
    """
    type: str = "message"
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    message: AgentMessage

# --- 第二部分：会话管理器 (Session Manager) ---

class SessionManager:
    """
    【记忆中枢】管理 JSONL 文件的追加与加载。
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.header: Optional[SessionHeader] = None
        self.entries: Dict[str, SessionEntry] = {}  # 内存索引：ID -> 条目
        self.leaf_id: Optional[str] = None          # 当前“叶子”节点指针

    @classmethod
    def create_new(cls, directory: str) -> "SessionManager":
        """
        创建一个全新的会话文件。
        """
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        # 使用时间戳作为文件名，方便排序
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_id = str(uuid.uuid4())[:8]
        file_path = os.path.join(directory, f"{timestamp}_{new_id}.jsonl")
        
        manager = cls(file_path)
        manager.header = SessionHeader(id=new_id)
        
        # 立即写入头部行
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(manager.header.model_dump_json() + "\n")
            
        return manager

    @classmethod
    def load_from_file(cls, file_path: str) -> "SessionManager":
        """
        从现有的 .jsonl 文件恢复状态。这就是“断点续传”的核心。
        """
        manager = cls(file_path)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"找不到会话文件: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                
                data = json.loads(line)
                if data.get("type") == "session":
                    manager.header = SessionHeader.model_validate(data)
                elif data.get("type") == "message":
                    entry = SessionEntry.model_validate(data)
                    manager.entries[entry.id] = entry
                    # 不断更新叶子指针，最后一行就是最新的叶子
                    manager.leaf_id = entry.id
                    
        return manager

    def append_message(self, message: AgentMessage) -> str:
        """
        【对话追加】将新消息挂载到当前叶子节点之下，并持久化到硬盘。
        """
        entry = SessionEntry(
            parent_id=self.leaf_id,
            message=message
        )
        
        # 写入文件（追加模式，极速响应）
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")
            
        # 更新内存状态
        self.entries[entry.id] = entry
        self.leaf_id = entry.id
        return entry.id

    def get_context(self, system_prompt: str = "") -> AgentContext:
        """
        【上下文构建】从当前叶子出发，一路向上溯源至根部。
        """
        messages = []
        curr_id = self.leaf_id
        
        # 就像顺着绳索向上爬
        while curr_id:
            entry = self.entries.get(curr_id)
            if not entry:
                break
            # 因为是向上溯源，所以要把新找到的老消息插到列表最前面
            messages.insert(0, entry.message)
            curr_id = entry.parent_id
            
        return AgentContext(system_prompt=system_prompt, messages=messages)
