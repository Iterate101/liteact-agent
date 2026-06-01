import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Set, Dict, Any
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback
from src.models.messages import TextContent

class SafeLsTool(AgentTool):
    """
    【安全目录探测工具】
    仿照 ls.ts 实现。具备递归控制、自动过滤、树状展示与熔断截断功能。
    """
    
    name: str = "safe_ls"
    description: str = (
        "递归列出目录内容。支持深度控制、自动忽略无关项（如 .git）。"
        "输出包含文件大小和修改时间，并以树状结构呈现。最多返回 100 条。"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to list (default: /workspace/)"},
            "depth": {"type": "integer", "description": "Maximum recursion depth (default: 1)", "default": 1},
            "recursive": {"type": "boolean", "description": "Whether to list subdirectories (default: False)", "default": False}
        }
    }

    # 工业级排除名单：自动忽略那些“大且无用”的机器生成目录
    IGNORE_LIST: Set[str] = {
        ".git", "__pycache__", "node_modules", ".venv", "venv", ".DS_Store", "dist", "build", ".idea", ".vscode"
    }

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path

    def _resolve_path(self, path: str) -> str:
        if not self.base_path:
            return path

        base = Path(self.base_path).resolve()
        normalized = (path or "/workspace/").replace("\\", "/")
        if normalized.startswith("/workspace/"):
            rel_path = normalized[len("/workspace/"):].lstrip("/")
            target_path = (base / rel_path).resolve()
        else:
            raw_path = Path(path)
            target_path = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()

        try:
            target_path.relative_to(base)
        except ValueError:
            raise ValueError(f"路径越界：{path} 不在工作区 {base} 内。")

        return str(target_path)

    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        path = params.get("path", "/workspace/")
        depth = params.get("depth", 1)
        recursive = params.get("recursive", False)
        
        # 1. 路径沙箱化转译
        try:
            real_path = self._resolve_path(path)
        except Exception as e:
            return AgentToolResult(content=[TextContent(text=f"错误：{str(e)}")], is_error=True)

        if not os.path.exists(real_path):
            return AgentToolResult(content=[TextContent(text=f"错误：路径不存在 {path}")], is_error=True)

        if not os.path.isdir(real_path):
            return AgentToolResult(content=[TextContent(text=f"错误：该路径不是目录 {path}")], is_error=True)

        # 2. 发起深度探测
        try:
            results = []
            self._explore(real_path, "", 0, depth if recursive else 0, results)
            
            # 3. 熔断保护：防刷屏截断逻辑
            limit = 100
            truncated = len(results) > limit
            display_results = results[:limit]
            
            output = "\n".join(display_results)
            if truncated:
                output += f"\n\n⚠️ [已截断] 探测条目超过 {limit} 条，还有更多文件可用。请减小深度或指定子文件夹重试。"
            
            if not display_results:
                output = "(空目录)"

            return AgentToolResult(content=[TextContent(text=output)])

        except Exception as e:
            return AgentToolResult(content=[TextContent(text=f"执行失败: {str(e)}")], is_error=True)

    def _explore(self, current_dir: str, prefix: str, current_depth: int, max_depth: int, results: List[str]):
        """【深度递归扫描器】"""
        if len(results) > 120: # 提前停止探测，防止内存溢出
            return

        try:
            # 这里的扫描排序：文件夹优先，且字母序
            entries = sorted(list(os.scandir(current_dir)), key=lambda e: (not e.is_dir(), e.name.lower()))
            
            for i, entry in enumerate(entries):
                if entry.name in self.IGNORE_LIST:
                    continue
                
                # 计算树状分支符号
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                
                # 获取元数据
                info = ""
                if entry.is_file():
                    size = self._format_size(entry.stat().st_size)
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    info = f" ({size} | {mtime})"
                
                # 记录条目
                results.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}{info}")
                
                # 递归进入
                if entry.is_dir() and current_depth < max_depth:
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    self._explore(entry.path, new_prefix, current_depth + 1, max_depth, results)
                    
        except PermissionError:
            results.append(f"{prefix}└── [权限拒绝]")
        except Exception as e:
            results.append(f"{prefix}└── [扫描错误: {str(e)}]")

    def _format_size(self, size: int) -> str:
        """【人性化单位转换】"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class ListFilesTool(SafeLsTool):
    """Default CLI-facing alias for directory listing."""

    name: str = "list_files"
    description: str = (
        "List files under a workspace directory with depth control and safe ignores. "
        "Use this before reading files when you need to understand project structure."
    )
