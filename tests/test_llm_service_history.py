import asyncio
import json
from types import SimpleNamespace

import services.llm_service as llm_service


class FakeResponse:
    def __init__(self):
        self.writes = []

    async def write(self, value):
        self.writes.append(value)


class FakeLlm:
    async def astream(self, messages):
        yield SimpleNamespace(content="Hello ")
        yield SimpleNamespace(
            content=[{"type": "text", "text": "history"}],
        )


class CancellingLlm:
    def __init__(self, request):
        self.request = request

    async def astream(self, messages):
        yield SimpleNamespace(content="partial")
        self.request.running_tasks[7]["cancelled"] = True
        yield SimpleNamespace(content="ignored")


def test_completed_answer_is_saved_and_stream_is_closed(monkeypatch):
    saved = {}

    async def fake_decode_jwt_token(token):
        return {"id": 7}

    async def fake_add_user_record(**kwargs):
        saved.update(kwargs)
        return 42

    monkeypatch.setattr(
        llm_service,
        "decode_jwt_token",
        fake_decode_jwt_token,
    )
    monkeypatch.setattr(
        llm_service,
        "add_user_record",
        fake_add_user_record,
    )
    monkeypatch.setattr(
        llm_service,
        "get_llm",
        lambda **kwargs: FakeLlm(),
    )

    response = FakeResponse()
    request = llm_service.LLMRequest()

    asyncio.run(
        request.exec_query(
            response,
            req_obj={
                "query": "Remember this",
                "uuid": "message-1",
                "chat_id": "chat-1",
                "qa_type": "COMMON_QA",
                "file_list": [],
                "datasource_id": None,
            },
            token="token-1",
        )
    )

    assert saved["uuid_str"] == "message-1"
    assert saved["chat_id"] == "chat-1"
    assert saved["question"] == "Remember this"
    assert saved["to2_answer"] == ["Hello ", "history"]
    assert saved["qa_type"] == "COMMON_QA"
    assert saved["user_token"] == "token-1"

    messages = [
        json.loads(value.removeprefix("data:").strip())
        for value in response.writes
    ]

    assert messages[-1]["dataType"] == "t99"
    assert 7 not in request.running_tasks


def test_save_failure_does_not_break_completed_stream(monkeypatch):
    async def fake_decode_jwt_token(token):
        return {"id": 7}

    async def failing_add_user_record(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        llm_service,
        "decode_jwt_token",
        fake_decode_jwt_token,
    )
    monkeypatch.setattr(
        llm_service,
        "add_user_record",
        failing_add_user_record,
    )
    monkeypatch.setattr(
        llm_service,
        "get_llm",
        lambda **kwargs: FakeLlm(),
    )

    response = FakeResponse()

    asyncio.run(
        llm_service.LLMRequest().exec_query(
            response,
            req_obj={
                "query": "Still answer",
                "uuid": "message-2",
                "chat_id": "chat-2",
                "qa_type": "COMMON_QA",
            },
            token="token-1",
        )
    )

    messages = [
        json.loads(value.removeprefix("data:").strip())
        for value in response.writes
    ]

    assert messages[-2]["data"]["messageType"] == "end"
    assert messages[-1]["dataType"] == "t99"


def test_cancelled_answer_is_not_saved(monkeypatch):
    saved = False

    async def fake_decode_jwt_token(token):
        return {"id": 7}

    async def fake_add_user_record(**kwargs):
        nonlocal saved
        saved = True

    request = llm_service.LLMRequest()

    monkeypatch.setattr(
        llm_service,
        "decode_jwt_token",
        fake_decode_jwt_token,
    )
    monkeypatch.setattr(
        llm_service,
        "add_user_record",
        fake_add_user_record,
    )
    monkeypatch.setattr(
        llm_service,
        "get_llm",
        lambda **kwargs: CancellingLlm(request),
    )

    response = FakeResponse()

    asyncio.run(
        request.exec_query(
            response,
            req_obj={
                "query": "Cancel this",
                "uuid": "message-3",
                "chat_id": "chat-3",
                "qa_type": "COMMON_QA",
            },
            token="token-1",
        )
    )

    assert saved is False
    assert 7 not in request.running_tasks
