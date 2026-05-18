import asyncio
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import openai

# 加入根目录到搜索路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ai.stream import stream_chat
from src.ai.registry import registry
from src.models.ai import TextDelta

# 强制设置环境编码
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

class TestAIStreaming(unittest.IsolatedAsyncioTestCase):
    
    async def test_automatic_provider_routing(self):
        """验证 stream_chat 能够正确根据 API 类型选择对应的 Provider。"""
        print("\n--- [测试 1: 自动路由分发] ---")
        
        # 我们可以检查 registry 是否已经注册了默认值
        provider = registry.get_provider("openai-responses")
        self.assertIsNotNone(provider)
        print("[SUCCESS] 路由分发中心已正确加载默认适配器。")

    @patch("src.ai.providers.openai.OpenAIProvider.stream")
    async def test_retry_on_rate_limit(self, mock_stream):
        """验证面对速率限制时，系统是否会自动开启 retry 逻辑。"""
        print("\n--- [测试 2: 速率限制重试验证] ---")
        
        # 准备一个“苦尽甘来”的模拟器：
        # 前两次抛出 RateLimitError，第三次成功返回数据
        async def mock_generator(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                print(f"  (模拟失败 第 {attempt_count} 次: 速率限制已满)")
                raise openai.RateLimitError("Rate limit exceeded", response=MagicMock(), body={})
            yield TextDelta(delta="成功了！")

        attempt_count = 0
        mock_stream.side_effect = mock_generator
        
        events = []
        async for event in stream_chat(
            model_id="gpt-mock", 
            api_type="openai-responses", 
            messages=[],
            max_retries=3 # 刚好三次
        ):
            events.append(event)

        self.assertEqual(attempt_count, 3)
        self.assertEqual(events[0].delta, "成功了！")
        print(f"[SUCCESS] 完成了 {attempt_count} 次重试，且最终拿到了数据。")

    @patch("src.ai.providers.openai.OpenAIProvider.stream")
    async def test_timeout_interruption(self, mock_stream):
        """验证当模型响应超过设置的 timeout 时，系统是否能正确切断。"""
        print("\n--- [测试 3: 响应超时熔断验证] ---")
        
        async def slow_generator(*args, **kwargs):
            # 模拟模型在那边“思考”太久
            await asyncio.sleep(5)
            yield TextDelta(delta="我来晚了")

        mock_stream.side_effect = slow_generator
        
        with self.assertRaises(asyncio.TimeoutError):
            # 设置极端的 1 秒超时
            async for _ in stream_chat(
                model_id="gpt-mock", 
                api_type="openai-responses", 
                messages=[],
                timeout=1.0, # 强制一秒超时
                max_retries=1 # 不重试，直接抛出
            ):
                pass
        
        print("[SUCCESS] 超时限制生效，成功在 [1s] 内中断了阻塞连接。")

if __name__ == "__main__":
    unittest.main()
