import asyncio
import sys
import os
import shutil

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent.session import SessionManager
from src.models.messages import UserMessage, AssistantMessage, TextContent

def test_session_persistence():
    print("\n--- [持久化可靠性测试] SessionManager ---")
    
    # 准备测试目录
    test_dir = "test_sessions"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    # --- 第一幕：创建并写入消息 ---
    print("1. [第一幕] 正在建立新会话并持久化消息...")
    manager1 = SessionManager.create_new(test_dir)
    file_path = manager1.file_path
    
    # 添加用户消息
    manager1.append_message(UserMessage(content="你好，我是测试员。"))
    # 添加 AI 回复 (包含思考片段)
    manager1.append_message(AssistantMessage(content=[TextContent(text="你好！我是 LiteAct。")]))
    
    print(f"   已写入 2 条消息到: {file_path}")
    print("   当前叶子 ID:", manager1.leaf_id)
    
    # --- 第二幕：模拟程序退出并重新加载 ---
    print("\n2. [第二幕] 模拟程序重启，正在加载历史记录...")
    manager2 = SessionManager.load_from_file(file_path)
    
    print("   加载后的叶子 ID:", manager2.leaf_id)
    assert manager1.leaf_id == manager2.leaf_id, "❌ 错误：叶子指针丢失！"
    
    # --- 第三幕：验证上下文完整性 ---
    print("\n3. [第三幕] 正在溯源对话完整性...")
    ctx = manager2.get_context(system_prompt="你是测试专家。")
    
    print(f"   上下文消息数量: {len(ctx.messages)}")
    assert len(ctx.messages) == 2, "❌ 错误：消息记录缺失！"
    
    print(f"   [0] {ctx.messages[0].role}: {ctx.messages[0].content}")
    print(f"   [1] {ctx.messages[1].role}: {ctx.messages[1].content[0].text}")
    
    # --- 第四幕：在旧会话基础上继续聊天 ---
    print("\n4. [第四幕] 尝试在恢复的会话中继续对话...")
    manager2.append_message(UserMessage(content="你能记住刚才的话吗？"))
    
    # 再次加载看看是否变成了 3 条
    final_manager = SessionManager.load_from_file(file_path)
    final_ctx = final_manager.get_context()
    print(f"   最终会话长度: {len(final_ctx.messages)}")
    assert len(final_ctx.messages) == 3, "❌ 错误：追加消息失败！"

    # 彻底清理
    if os.path.exists("test_sessions"):
        shutil.rmtree("test_sessions")
    print("\n[SUCCESS] 所有持久化测试通过！SessionManager 表现完美。")

if __name__ == "__main__":
    test_session_persistence()
