import json
import os

from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel

pool = get_db_pool()

# 默认超时时间:30分钟
# 与 deep_research_agent.py 的 DEFAULT_LLM_TIMEOUT 保持一致
# 超时链路：LLM(15min) < TASK(30min) < Sanic RESPONSE(35min) < 前端 fetch(36min)
DEFAULT_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", 30 * 60))


def get_llm(temperature=0.75, timeout=None, max_tokens=None, thinking=False):
    """
    获取LLM模型
    :param temperature: 温度参数
    :param timeout: 超时时间（秒），默认使用环境变量 LLM_TIMEOUT 或 30分钟
    :param max_tokens: 单次输出 token 上限，默认 None（使用模型默认值）
    :param thinking: 是否开启思考模式（仅 OpenAI 协议支持，如 DeepSeek-R1），默认 False
    :return: LLM模型实例
    """
    with pool.get_session() as session:
        # Fetch default model
        model = (
            session.query(TAiModel)
            .filter(TAiModel.default_model == True, TAiModel.model_type == 1)
            .first()
        )
        if not model:
            raise ValueError("No default AI model configured in database.")

        # Map supplier to model type string used in map
        # 1:OpenAI, 2:Azure, 3:Ollama, 4:vLLM, 5:DeepSeek, 6:Qwen, 7:Moonshot, 8:ZhipuAI, 9:Other
        supplier = model.supplier

        # 目前统一将 Qwen 也视为通过 OpenAI 协议接入，避免 ChatTongyi 及其 LangSmith/OpenTelemetry 依赖
        if supplier == 3:
            model_type = "ollama"
        else:
            # Default to openai for others (OpenAI, Qwen, DeepSeek, Moonshot, Zhipu, vLLM, etc.)
            model_type = "openai"

        model_name = model.base_model
        model_api_key = model.api_key
        model_base_url = model.api_domain

        try:
            temperature = float(temperature)
        except ValueError:
            temperature = 0.75

        # 确定超时时间：优先使用参数，其次环境变量，最后使用默认值
        if timeout is None:
            timeout = DEFAULT_LLM_TIMEOUT
        else:
            try:
                timeout = int(timeout)
            except (ValueError, TypeError):
                timeout = DEFAULT_LLM_TIMEOUT

        # 为了避免在模块加载时就触发第三方依赖（如 OpenTelemetry/LangSmith）的副作用，
        # 对各类模型做统一的延迟导入和降级处理
        def _get_openai():
            """
            延迟导入 ChatOpenAI，避免在应用启动阶段因 langsmith/opentelemetry 初始化失败导致进程退出。
            如果导入失败，直接抛异常，由上层决定如何处理（通常是显式配置问题）。
            """
            try:
                from langchain_openai import ChatOpenAI
            except Exception as e:
                print(
                    f"[ERROR] Failed to import ChatOpenAI, please check langchain-openai/langsmith/opentelemetry installation: {e}"
                )
                raise

            kwargs = dict(
                model=model_name,
                temperature=temperature,
                base_url=model_base_url,
                api_key=model_api_key or "empty",  # Ensure not None
                timeout=timeout,
            )
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if thinking:
                kwargs["model_kwargs"] = {"extra_body": {"thinking": {"type": "enabled"}}}

            # LangChain silently drops reasoning_content at two points:
            # 1. _convert_chunk_to_generation_chunk never reads delta.reasoning_content
            # 2. _get_request_payload/_convert_message_to_dict never writes it back
            # This subclass fixes both ends so DeepSeek multi-turn conversations work.
            class _DeepSeekCompatChatOpenAI(ChatOpenAI):
                def _convert_chunk_to_generation_chunk(
                    self, chunk, default_chunk_class, base_generation_info
                ):
                    from langchain_core.messages import AIMessageChunk as _AIMessageChunk

                    gen = super()._convert_chunk_to_generation_chunk(
                        chunk, default_chunk_class, base_generation_info
                    )
                    if gen is None:
                        return None
                    choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
                    if choices:
                        delta = choices[0].get("delta") or {}
                        reasoning = delta.get("reasoning_content")
                        if reasoning and isinstance(gen.message, _AIMessageChunk):
                            gen.message.additional_kwargs["reasoning_content"] = (
                                gen.message.additional_kwargs.get("reasoning_content", "")
                                + reasoning
                            )
                    return gen

                def _create_chat_result(self, response, generation_info=None):
                    result = super()._create_chat_result(response, generation_info)
                    resp = response if isinstance(response, dict) else response.model_dump()
                    choices = resp.get("choices") or []
                    if choices and result.generations:
                        reasoning = (choices[0].get("message") or {}).get("reasoning_content")
                        if reasoning:
                            result.generations[0].message.additional_kwargs[
                                "reasoning_content"
                            ] = reasoning
                    return result

                def _get_request_payload(self, input_, *, stop=None, **kwargs):
                    from langchain_core.messages import AIMessage as _AIMessage

                    payload = super()._get_request_payload(input_, stop=stop, **kwargs)
                    messages = self._convert_input(input_).to_messages()
                    for msg, msg_dict in zip(messages, payload.get("messages", [])):
                        if isinstance(msg, _AIMessage) and msg_dict.get("role") == "assistant":
                            reasoning = (msg.additional_kwargs or {}).get("reasoning_content")
                            if reasoning:
                                msg_dict["reasoning_content"] = reasoning
                    return payload

            return _DeepSeekCompatChatOpenAI(**kwargs)

        def _get_ollama():
            """
            延迟导入 ChatOllama，避免在模块加载阶段触发不必要的依赖。
            """
            try:
                from langchain_ollama import ChatOllama
            except Exception as e:
                print(
                    f"[WARN] Failed to import ChatOllama, fallback to ChatOpenAI: {e}"
                )
                return _get_openai()

            return ChatOllama(
                model=model_name,
                temperature=temperature,
                base_url=model_base_url,
                timeout=timeout,  # 设置超时时间（秒）
            )

        # Qwen 也统一走 OpenAI 协议客户端，避免引入 ChatTongyi 及其 LangSmith/OpenTelemetry 依赖
        model_map = {
            "openai": _get_openai,
            "ollama": _get_ollama,
        }

        if model_type in model_map:
            return model_map[model_type]()
        else:
            # Should not happen given logic above, but fallback to openai
            return model_map["openai"]()
