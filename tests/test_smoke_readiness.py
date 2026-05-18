import os
from pathlib import Path


def test_project_readiness_files_exist():
    """检查公开仓库所需的项目说明文件是否存在。"""
    root = Path(__file__).resolve().parents[1]

    required_files = [
        "README.md",
        "requirements.txt",
        ".env.example",
        ".gitignore",
    ]

    missing = [name for name in required_files if not (root / name).exists()]
    assert not missing, f"缺少公开仓库说明文件: {missing}"


def test_env_example_documents_runtime_keys():
    """检查环境变量示例是否覆盖 CLI 和平台入口的关键配置。"""
    root = Path(__file__).resolve().parents[1]
    content = (root / ".env.example").read_text(encoding="utf-8")

    for key in [
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "MODEL_ID",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "SLACK_APP_TOKEN",
        "SLACK_BOT_TOKEN",
    ]:
        assert key in content


def test_gitignore_protects_private_runtime_files():
    """检查公开仓库中不应提交的运行记录和密钥文件是否已被忽略。"""
    root = Path(__file__).resolve().parents[1]
    content = (root / ".gitignore").read_text(encoding="utf-8")

    expected_patterns = [
        ".env",
        "sessions/*.jsonl",
        "tests/sessions/*.jsonl",
        "__pycache__/",
        "Notebook/",
    ]

    for pattern in expected_patterns:
        assert pattern in content
