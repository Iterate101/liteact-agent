import os
import re
import fnmatch
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback
from src.models.messages import TextContent

class SearchTextTool(AgentTool):
    """
    【全文内容检索工具】
    仿照 grep.ts 实现。支持正则搜索、上下文展示与 50 条强制熔断。
    """
    
    name: str = "search_text"
    description: str = (
        "在指定目录的文件内容中搜索正则模式。返回格式为 '文件名:行号:匹配行'。"
        "默认递归搜索。结果上限 50 条。"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for."},
            "path": {"type": "string", "description": "Search root directory (default: /workspace/)"},
            "ignore_case": {"type": "boolean", "description": "Case-insensitive search (default: True)", "default": True}
        },
        "required": ["pattern"]
    }

    # 排除名单：避免搜索二进制或庞大的无关文件
    IGNORE_EXTS = {".exe", ".bin", ".pyc", ".png", ".jpg", ".zip", ".git", "node_modules", ".venv"}

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path

    async def execute(self, tool_call_id: str, params: dict, **kwargs) -> AgentToolResult:
        pattern_str = params.get("pattern", "")
        path_str = params.get("path", "/workspace/")
        ignore_case = params.get("ignore_case", True)

        # 1. 沙箱转译
        real_path = path_str
        if self.base_path and path_str.startswith("/workspace/"):
            rel_path = path_str[len("/workspace/"):].lstrip("/").lstrip("\\")
            real_path = os.path.join(self.base_path, rel_path)

        if not os.path.exists(real_path):
            return AgentToolResult(content=[TextContent(text=f"错误：路径不存在 {path_str}")], is_error=True)

        # 2. 编译正则
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern_str, flags)
        except Exception as e:
            return AgentToolResult(content=[TextContent(text=f"错误：正则语法错误 {str(e)}")], is_error=True)

        matches = []
        limit = 50
        
        # 3. 递归扫描
        for root, dirs, files in os.walk(real_path):
            # 过滤目录
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv"}]
            
            for file in files:
                if any(file.endswith(ext) for ext in self.IGNORE_EXTS):
                    continue
                
                full_path = os.path.join(root, file)
                rel_file_path = os.path.relpath(full_path, real_path).replace("\\", "/")
                
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                matches.append(f"{rel_file_path}:{line_num}: {line.strip()}")
                                if len(matches) >= limit:
                                    break
                except Exception:
                    continue # 忽略无法读取的文件
                
                if len(matches) >= limit:
                    break
            if len(matches) >= limit:
                break

        # 4. 熔断反馈
        output = "\n".join(matches)
        if len(matches) >= limit:
            output += f"\n\n⚠️ [已熔断] 已达到 {limit} 条上限。请细化您的搜索模式以节省 token。"
        
        if not matches:
            output = "未找到匹配项。"

        return AgentToolResult(content=[TextContent(text=output)])

class SearchFilesTool(AgentTool):
    """
    【文件名定位工具】
    仿照 find.ts 实现。支持 Glob 通配符查找与 50 条熔断。
    """
    
    name: str = "search_files"
    description: str = "按文件名通配符查找文件。例如: '**/main.py' 或 '*.txt'。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/base.py')"},
            "path": {"type": "string", "description": "Search root (default: /workspace/)"}
        },
        "required": ["pattern"]
    }

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path

    async def execute(self, tool_call_id: str, params: dict, **kwargs) -> AgentToolResult:
        pattern = params.get("pattern", "")
        path_str = params.get("path", "/workspace/")

        # 1. 沙箱转译
        real_path = path_str
        if self.base_path and path_str.startswith("/workspace/"):
            rel_path = path_str[len("/workspace/"):].lstrip("/").lstrip("\\")
            real_path = os.path.join(self.base_path, rel_path)

        matches = []
        limit = 50

        # 2. 递归查找
        try:
            # 使用 Path.glob 进行高效通配符搜索
            p = Path(real_path)
            # 如果 pattern 包含 **/ 则启用递归，否则按照 pattern 本身逻辑
            for match_path in p.glob(pattern):
                if match_path.is_file():
                    rel_match = match_path.relative_to(p).as_posix()
                    matches.append(rel_match)
                    if len(matches) >= limit:
                        break
        except Exception as e:
            return AgentToolResult(content=[TextContent(text=f"查找异常: {str(e)}")], is_error=True)

        # 3. 反馈
        output = "\n".join(matches)
        if len(matches) >= limit:
            output += f"\n\n⚠️ [已熔断] 匹配文件过多，仅显示前 {limit} 个。"
        
        if not matches:
            output = "未找到符合条件的文件。"

        return AgentToolResult(content=[TextContent(text=output)])
