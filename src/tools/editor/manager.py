import asyncio
import os
from pathlib import Path
from typing import Optional
from src.tools.base import AgentTool, AgentToolResult, AgentToolUpdateCallback, TextContent
from src.utils.lock_manager import global_path_lock

class FileEditManager(AgentTool):
    """
    【局部手术专家】实现基于精确匹配的文件编辑。
    特性：唯一性校验、原子化存储、极致的报错反馈。
    """
    
    name: str = "edit_file"
    description: str = "通过『搜索-替换』模式精确修改源代码中的局部片段。要求查找内容在文件中必须全局唯一。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file to edit."},
            "target": {"type": "string", "description": "The exact text fragment to replace. It must appear exactly once."},
            "replacement": {"type": "string", "description": "The new text fragment that will replace target."}
        },
        "required": ["path", "target", "replacement"]
    }

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path

    def _resolve_target_path(self, path: str) -> Path:
        """
        将工具收到的路径转换为真实路径。
        如果 Runner 注入了 base_path，就把 /workspace/ 或相对路径限制在该目录下。
        """
        if not self.base_path:
            return Path(path).resolve()

        base = Path(self.base_path).resolve()
        normalized = path.replace("\\", "/")

        if normalized.startswith("/workspace/"):
            rel_path = normalized[len("/workspace/"):].lstrip("/")
            target_path = (base / rel_path).resolve()
        else:
            raw_path = Path(path)
            if raw_path.is_absolute():
                target_path = raw_path.resolve()
            else:
                target_path = (base / raw_path).resolve()

        try:
            target_path.relative_to(base)
        except ValueError:
            raise ValueError(f"路径越界：{path} 不在工作区 {base} 内。")

        return target_path

    async def execute(
        self, 
        tool_call_id: str, 
        params: dict, 
        abort_signal: Optional[asyncio.Event] = None,
        on_partial_result: Optional[AgentToolUpdateCallback] = None
    ) -> AgentToolResult:
        """
        核心编辑逻辑入口。
        """
        path = params.get("path")
        target = params.get("target")
        replacement = params.get("replacement")

        if not path or target is None or replacement is None:
            return self._error_res("参数缺失。需要 'path', 'target', 'replacement'。")

        try:
            target_path = self._resolve_target_path(path)
            if not target_path.exists():
                return self._error_res(f"找不到文件: {path}")

            async with global_path_lock.lock_path(str(target_path)):
                # 1. 加载文件内容
                # 在执行大文件 I/O 前预读并检测
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 2. 精准匹配校验 (TS 逻辑移植)
                count = content.count(target)
                
                if count == 0:
                    # 给模型最友好的报错：告诉它为什么搜不到
                    return self._error_res(
                        f"匹配失败！在文件 {path} 中找不到指定的 target 字符串。\n"
                        "请检查拼写、缩进（空格 vs Tab）以及空行是否与原文件完全一致。"
                    )
                
                if count > 1:
                    # 歧义校验：防止误伤
                    return self._error_res(
                        f"匹配歧义！在文件中找到了 {count} 处相同的 target 字符串。\n"
                        "请提供更完整的上下文（增加前后行）以确保唯一性。"
                    )

                # 3. 执行替换并原子化写入
                new_content = content.replace(target, replacement, 1)
                
                # 使用临时文件方案
                tmp_path = target_path.with_suffix(".edit.tmp")
                try:
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                        f.flush()
                        os.fsync(f.fileno())
                    
                    os.replace(tmp_path, target_path)
                    return AgentToolResult(
                        content=[TextContent(text=f"成功修改文件 {path}。替换了 {len(target)} 字符为 {len(replacement)} 字符。")]
                    )
                except Exception as e:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    raise e

        except Exception as e:
            return self._error_res(f"编辑过程中发生异常: {str(e)}")

    def _error_res(self, message: str) -> AgentToolResult:
        """快速生成错误反馈"""
        return AgentToolResult(
            content=[TextContent(text=f"Error: {message}")],
            details={"status": "error"},
            is_error=True
        )
