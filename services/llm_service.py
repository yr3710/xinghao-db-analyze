import json
import logging

from langchain_core.messages import HumanMessage

from common.llm_util import get_llm
from constants.code_enum import DataTypeEnum
from services.user_service import decode_jwt_token

logger = logging.getLogger(__name__)


class LLMRequest:
    def __init__(self):
        self.running_tasks = {}

    @staticmethod
    def _create_sse(data) -> str:
        return (
            "data:"
            + json.dumps(data, ensure_ascii=False)
            + "\n\n"
        )

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            texts = []

            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))

            return "".join(texts)

        return ""

    async def _send_text(
        self,
        response,
        content: str,
        message_type: str = "continue",
    ):
        message = {
            "data": {
                "messageType": message_type,
                "content": content,
            },
            "dataType": DataTypeEnum.ANSWER.value[0],
        }

        await response.write(self._create_sse(message))

    async def _send_stream_end(self, response):
        message = {
            "data": "DONE",
            "dataType": DataTypeEnum.STREAM_END.value[0],
        }

        await response.write(self._create_sse(message))

    async def exec_query(
        self,
        response,
        req_obj: dict,
        token: str,
    ):
        user = await decode_jwt_token(token)
        user_id = user["id"]

        task_context = {"cancelled": False}
        self.running_tasks[user_id] = task_context

        try:
            query = req_obj["query"]

            await self._send_text(
                response,
                "",
                message_type="begin",
            )

            llm = get_llm(temperature=0.75)

            async for chunk in llm.astream(
                [HumanMessage(content=query)]
            ):
                if task_context["cancelled"]:
                    await self._send_text(
                        response,
                        "\n\n> 本次生成已停止",
                    )
                    break

                text = self._extract_text(chunk.content)

                if text:
                    await self._send_text(response, text)

            await self._send_text(
                response,
                "",
                message_type="end",
            )

        except Exception as exc:
            logger.exception("LLM streaming failed")

            await self._send_text(
                response,
                f"模型调用失败：{exc}",
                message_type="error",
            )

        finally:
            await self._send_stream_end(response)
            self.running_tasks.pop(user_id, None)

    async def cancel_task(self, user_id: int) -> bool:
        task_context = self.running_tasks.get(user_id)

        if not task_context:
            return False

        task_context["cancelled"] = True
        return True


llm_request = LLMRequest()

async def stop_dify_chat(
    request,
    task_id,
    qa_type,
) -> dict:
    token = request.headers.get("Authorization")

    if not token:
        return {
            "success": False,
            "message": "未登录",
        }

    if token.startswith("Bearer "):
        token = token.removeprefix("Bearer ")

    if qa_type != "COMMON_QA":
        return {
            "success": False,
            "message": f"暂不支持停止 {qa_type}",
        }

    user = await decode_jwt_token(token)
    user_id = user["id"]

    success = await llm_request.cancel_task(user_id)

    return {
        "success": success,
        "message": (
            "任务已停止"
            if success
            else "未找到正在执行的任务"
        ),
    }