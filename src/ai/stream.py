import asyncio
import os
from typing import AsyncGenerator, Optional, List, Dict, Any
from tenacity import (
    AsyncRetrying, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type
)
import openai

from src.ai.registry import registry
from src.models.ai import StreamEvent, AgentMessage

async def stream_chat(
    model_id: str,
    api_type: str,
    messages: List[AgentMessage],
    system_prompt: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    reasoning_effort: Optional[str] = None
) -> AsyncGenerator[StreamEvent, None]:
    """
    【AI 统一流式入口】
    1. 自动根据 api_type 路由到对应 Provider。
    2. 支持基于 tenacity 的自动重试逻辑。
    3. 支持 asyncio.wait_for 超时控制。
    """
    # 从注册表获取适配器实例
    provider = registry.get_provider(api_type)
    
    # 定义重试策略
    retryer = AsyncRetrying(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            openai.RateLimitError, 
            openai.APIConnectionError, 
            asyncio.TimeoutError
        )),
        reraise=True
    )

    async def _run_stream():
        # 这里我们通过 asyncio.wait_for 包装整个流的启动和每一帧
        generator = provider.stream(
            model=model_id,
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            reasoning_effort=reasoning_effort
        )
        
        # 这是一个小巧思：如何在异步生成器中实现超时
        while True:
            try:
                # 每一帧的获取都不能超过 timeout 秒
                event = await asyncio.wait_for(generator.__anext__(), timeout=timeout)
                yield event
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                # 记录超时并抛出，触发外层重试
                print(f"[Timeout] Model {model_id} 响应超时 (>{timeout}s)")
                raise

    # 执行带重试逻辑的流
    # 注意：tenacity 的 AsyncRetrying 对于异步生成器需要特殊处理
    # 简单起见，我们对整个生成过程进行尝试
    attempt_count = 0
    async for attempt in retryer:
        with attempt:
            attempt_count += 1
            if attempt_count > 1:
                print(f"[Retry] 正在进行第 {attempt_count} 次尝试...")
            
            async for event in _run_stream():
                yield event
