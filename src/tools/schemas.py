# 【核心中枢】LiteAct 工具集 JSON Schema 定义
# 这里定义了 Agent 能够理解的所有工具描述，就像是给 AI 读的“说明书”。

READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "从指定路径读取文件内容。支持图片识别、文本分页读取及安全截断（50KB/800行限制）。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件的完整或相对路径。"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始读取行号 (1-indexed)。",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "本次读取的最大行数。",
                    "default": 800
                }
            },
            "required": ["path"]
        }
    }
}

WRITE_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "将内容原子化地写入指定路径。支持自动创建父目录，并具备并发锁定保护。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目标文件路径。"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的完整文本内容。"
                }
            },
            "required": ["path", "content"]
        }
    }
}

EXECUTE_BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_bash",
        "description": "在本地终端执行安全受限的 Bash 指令，并捕获标准输出和标准错误。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "需要运行的命令行字符串。"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数。",
                    "default": 30
                }
            },
            "required": ["command"]
        }
    }
}

LIST_FILES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "列出工作区目录内容，支持深度控制、常见构建产物过滤和最多 100 条截断。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要查看的目录路径，默认 /workspace/。",
                    "default": "/workspace/"
                },
                "depth": {
                    "type": "integer",
                    "description": "递归深度。",
                    "default": 1
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归列出子目录。",
                    "default": False
                }
            }
        }
    }
}

SEARCH_TEXT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_text",
        "description": "在工作区文件内容中搜索正则表达式，返回 文件名:行号:匹配行。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "要搜索的正则表达式。"
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录，默认 /workspace/。",
                    "default": "/workspace/"
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "是否忽略大小写。",
                    "default": True
                }
            },
            "required": ["pattern"]
        }
    }
}

SEARCH_FILES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_files",
        "description": "按文件名或 glob 模式在工作区内查找文件，适合快速定位入口文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "文件名或 glob 模式，例如 *.py 或 **/main.py。"
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录，默认 /workspace/。",
                    "default": "/workspace/"
                }
            },
            "required": ["pattern"]
        }
    }
}

EDIT_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "通过唯一文本片段替换来局部修改文件，返回 unified diff，并在写入前自动生成 checkpoint。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要修改的文件路径。"
                },
                "target": {
                    "type": "string",
                    "description": "要替换的原始文本片段，必须在文件中全局唯一。"
                },
                "replacement": {
                    "type": "string",
                    "description": "替换后的文本片段。"
                },
                "preview_only": {
                    "type": "boolean",
                    "description": "是否只预览 diff，不实际写入文件。",
                    "default": False
                }
            },
            "required": ["path", "target", "replacement"]
        }
    }
}

RUN_TESTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_tests",
        "description": "在当前工作区运行 Python unittest 测试，用于代码修改后的执行验证。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "测试目录，默认 tests。",
                    "default": "tests"
                },
                "pattern": {
                    "type": "string",
                    "description": "unittest discover 文件匹配模式。",
                    "default": "test*.py"
                },
                "timeout": {
                    "type": "integer",
                    "description": "测试超时秒数。",
                    "default": 60
                }
            }
        }
    }
}

ROLLBACK_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "rollback_file",
        "description": "从 LiteAct checkpoint 恢复文件。优先传入 edit_file/write_file 返回的 checkpoint_id；也可以按 path 恢复该文件最近一次 checkpoint。",
        "parameters": {
            "type": "object",
            "properties": {
                "checkpoint_id": {
                    "type": "string",
                    "description": "edit_file/write_file 返回的 checkpoint_id。也可传 latest 并配合 path 使用。"
                },
                "path": {
                    "type": "string",
                    "description": "未提供 checkpoint_id 时，按文件路径恢复最近一次 checkpoint。"
                }
            }
        }
    }
}

# 统一导出工具定义列表，方便 Agent 核心层直接加载
TOOLS_DEFINITIONS = [
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    EDIT_FILE_SCHEMA,
    EXECUTE_BASH_SCHEMA,
    LIST_FILES_SCHEMA,
    SEARCH_TEXT_SCHEMA,
    SEARCH_FILES_SCHEMA,
    RUN_TESTS_SCHEMA,
    ROLLBACK_FILE_SCHEMA,
]
