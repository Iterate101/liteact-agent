import asyncio

from src.agent.loop import ReActLoop
from src.tools.editor.manager import FileEditManager
from src.tools.registry import DEFAULT_TOOL_FACTORIES, build_default_tools
from src.tools.schemas import TOOLS_DEFINITIONS


def test_default_tool_registry_includes_edit_file():
    """验证默认工具注册表把 edit_file 作为正式内置工具暴露出来。"""
    tools = build_default_tools()

    assert set(DEFAULT_TOOL_FACTORIES) == {
        "read_file",
        "write_file",
        "edit_file",
        "execute_bash",
    }
    assert isinstance(tools["edit_file"], FileEditManager)


def test_react_loop_schema_exposes_edit_file():
    """验证 ReActLoop 发送给模型的 tools schema 包含 edit_file。"""
    loop = ReActLoop()
    schemas = {
        item["function"]["name"]: item["function"]
        for item in loop._get_openai_tools_schema()
    }

    assert "edit_file" in loop.tools
    assert "edit_file" in schemas
    assert schemas["edit_file"]["parameters"]["required"] == [
        "path",
        "target",
        "replacement",
    ]


def test_static_tool_schemas_match_default_registry():
    """验证静态 schemas.py 没有漏掉默认工具。"""
    schema_names = {
        item["function"]["name"]
        for item in TOOLS_DEFINITIONS
    }

    assert schema_names == set(DEFAULT_TOOL_FACTORIES)


def test_static_tool_schemas_use_tool_metadata():
    """验证 schemas.py 直接反映工具类自己的描述和参数。"""
    tools = build_default_tools()
    schemas = {
        item["function"]["name"]: item["function"]
        for item in TOOLS_DEFINITIONS
    }

    for name, tool in tools.items():
        assert schemas[name]["description"] == tool.description
        assert schemas[name]["parameters"] == tool.parameters


def test_react_loop_default_edit_file_can_modify_file(tmp_path):
    """验证从 ReActLoop 默认工具集中取出的 edit_file 可以完成真实局部替换。"""
    target_file = tmp_path / "sample.py"
    target_file.write_text("value = 1\n", encoding="utf-8")

    loop = ReActLoop()
    result = asyncio.run(
        loop.tools["edit_file"].execute(
            "call_edit",
            {
                "path": str(target_file),
                "target": "value = 1",
                "replacement": "value = 2",
            },
        )
    )

    assert not result.is_error
    assert target_file.read_text(encoding="utf-8") == "value = 2\n"
