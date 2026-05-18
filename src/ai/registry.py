import os
from typing import Dict, Any, Type, Optional
from src.ai.providers.openai import OpenAIProvider

class ProviderRegistry:
    """
    【分拣中心】根据 model.api 类型自动分发适配器。
    类似于 TypeScript 中的 api-registry.ts。
    """
    _instance = None
    _providers: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProviderRegistry, cls).__new__(cls)
            # 初始化默认内置的适配器
            # 我们将 'openai-responses' 映射到 OpenAIProvider
            cls._instance._register_defaults()
        return cls._instance

    def _register_defaults(self):
        """自动注册项目内置的适配器"""
        # 1. 官方 OpenAI 节点
        self.register("openai-responses", OpenAIProvider())
        
        # 2. 阿里云通义千问 (DashScope兼容模式)
        self.register("dashscope", OpenAIProvider(
            api_key=os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        ))
        
        # 3. (预留) DeepSeek / 智谱等兼容节点建议：
        # self.register("deepseek", OpenAIProvider(base_url="https://api.deepseek.com/v1"))

    def register(self, api_type: str, provider_instance: Any):
        """允许插件动态扩展适配器"""
        self._providers[api_type] = provider_instance

    def get_provider(self, api_type: str) -> Any:
        provider = self._providers.get(api_type)
        if not provider:
            raise ValueError(f"没有找到 API 类型 '{api_type}' 对应的 Provider。请检查注册表。")
        return provider

# 全局单例
registry = ProviderRegistry()
