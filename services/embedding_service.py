import logging
import traceback
from typing import List, Optional

from openai import AsyncOpenAI

from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel

logger = logging.getLogger(__name__)
pool = get_db_pool()


async def get_default_embedding_model():
    """
    获取默认的 embedding 模型配置
    只查找 Embedding 类型的模型（model_type=2），不回退到 LLM
    """
    with pool.get_session() as session:
        # 优先查找默认的 embedding 模型 (model_type=2)
        model = session.query(TAiModel).filter(
            TAiModel.model_type == 2,
            TAiModel.default_model == True
        ).first()

        # 如果没有默认的，查找任何可用的 embedding 模型
        if not model:
            model = session.query(TAiModel).filter(TAiModel.model_type == 2).first()

        # 如果找到了 embedding 模型，返回配置
        if model:
            return {
                "supplier": model.supplier,
                "api_key": model.api_key,
                "api_domain": model.api_domain,
                "base_model": model.base_model
            }
        
        # 当前层只验收在线模型；未配置时返回 None，不回退本地模型
        return None


async def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for the given text"""
    if not text:
        return None

    model = await get_default_embedding_model()
    
    # 当前层不实现本地模型回退
    if not model:
        logger.warning("No online embedding model configured")
        return None

    try:
        api_key = model["api_key"] or "empty"
        base_url = model.get("api_domain") or ""

        # 验证 base_url 是否有效
        if not base_url or not base_url.strip():
            logger.warning("Embedding API domain is empty")
            return None

        # 确保 base_url 包含协议前缀
        base_url = base_url.strip()
        if not base_url.startswith(("http://", "https://")):
            # 默认使用 https，如果是本地地址则使用 http
            if base_url.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
                base_url = f"http://{base_url}"
            else:
                base_url = f"https://{base_url}"

        # Special handling for Ollama to ensure OpenAI compatibility
        if model["supplier"] == 3:  # Ollama
            if not base_url.endswith("/v1"):
                base_url = f"{base_url.rstrip('/')}/v1"

        # 使用 async with 确保客户端被正确关闭
        async with AsyncOpenAI(api_key=api_key, base_url=base_url) as client:
            response = await client.embeddings.create(model=model["base_model"], input=text)

            if response.data:
                return response.data[0].embedding

    except Exception as e:
        traceback.print_exc()
        logger.warning(f"Failed to generate embedding with online model: {e}")
        # 当前层在线模型失败时返回 None，不回退到本地模型
        return None

    return None
