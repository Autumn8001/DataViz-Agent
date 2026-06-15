import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# 加载根目录下的 .env 环境变量
load_dotenv()


class LLMFactory:
    """大模型分层实例化工厂，实现冷热模型解耦与成本控制"""

    @staticmethod
    def get_flash_model() -> ChatOpenAI:
        """获取轻量级模型：用于意图规划 (Planner) 和简单路由判断，极其便宜且速度快"""
        return ChatOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("BASE_URL"),
            model=os.getenv("FLASH_MODEL", "glm-4-flash"),
            temperature=0.0,  # 路由不需要创造力，设为 0 保证绝对的严谨稳定
            streaming=True,  # 开启流式输出底层支持
        )

    @staticmethod
    def get_core_model() -> ChatOpenAI:
        """获取旗舰级核心模型：用于高难度的代码生成 (Coder) 与错误自我反思 (Analyzer)"""
        return ChatOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("BASE_URL"),
            model=os.getenv("CORE_MODEL", "glm-4"),
            temperature=0.2,  # 较低的随机度，确保生成的 Python 代码逻辑严密
            streaming=True,  # 开启流式输出底层支持
        )
