import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from model.db_connection_pool import Base
from model.db_models import TAiModel


class EmbeddingPool:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def get_session(self):
        with Session(self.engine) as session:
            yield session


def test_default_embedding_model_prefers_default_model(monkeypatch):
    import services.embedding_service as embedding_service

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TAiModel.__table__])
    with Session(engine) as session:
        session.add_all(
            [
                TAiModel(
                    id=1,
                    supplier=1,
                    name="Fallback embedding",
                    model_type=2,
                    base_model="fallback-model",
                    default_model=False,
                    api_key="fallback-key",
                    api_domain="https://fallback.example/v1",
                    protocol=1,
                    status=1,
                ),
                TAiModel(
                    id=2,
                    supplier=1,
                    name="Default embedding",
                    model_type=2,
                    base_model="default-model",
                    default_model=True,
                    api_key="default-key",
                    api_domain="https://default.example/v1",
                    protocol=1,
                    status=1,
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(embedding_service, "pool", EmbeddingPool(engine))

    result = asyncio.run(embedding_service.get_default_embedding_model())

    assert result == {
        "supplier": 1,
        "api_key": "default-key",
        "api_domain": "https://default.example/v1",
        "base_model": "default-model",
    }


def test_generate_embedding_uses_online_openai_client(monkeypatch):
    import services.embedding_service as embedding_service

    captured = {}

    async def fake_model():
        return {
            "supplier": 1,
            "api_key": "key",
            "api_domain": "embedding.example/v1",
            "base_model": "text-embedding-model",
        }

    class FakeEmbeddings:
        async def create(self, *, model, input):
            captured["request"] = {"model": model, "input": input}
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
            )

    class FakeClient:
        def __init__(self, *, api_key, base_url):
            captured["client"] = {
                "api_key": api_key,
                "base_url": base_url,
            }
            self.embeddings = FakeEmbeddings()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(embedding_service, "get_default_embedding_model", fake_model)
    monkeypatch.setattr(embedding_service, "AsyncOpenAI", FakeClient)

    result = asyncio.run(embedding_service.generate_embedding("sales trend"))

    assert result == [0.1, 0.2, 0.3]
    assert captured == {
        "client": {
            "api_key": "key",
            "base_url": "https://embedding.example/v1",
        },
        "request": {
            "model": "text-embedding-model",
            "input": "sales trend",
        },
    }


def test_generate_embedding_appends_openai_path_for_ollama(monkeypatch):
    import services.embedding_service as embedding_service

    captured = {}

    async def fake_model():
        return {
            "supplier": 3,
            "api_key": None,
            "api_domain": "localhost:11434",
            "base_model": "nomic-embed-text",
        }

    class FakeEmbeddings:
        async def create(self, *, model, input):
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0])])

    class FakeClient:
        def __init__(self, *, api_key, base_url):
            captured.update(api_key=api_key, base_url=base_url)
            self.embeddings = FakeEmbeddings()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(embedding_service, "get_default_embedding_model", fake_model)
    monkeypatch.setattr(embedding_service, "AsyncOpenAI", FakeClient)

    result = asyncio.run(embedding_service.generate_embedding("question"))

    assert result == [1.0]
    assert captured == {
        "api_key": "empty",
        "base_url": "http://localhost:11434/v1",
    }


def test_generate_embedding_returns_none_without_online_model(monkeypatch):
    import services.embedding_service as embedding_service

    async def no_model():
        return None

    monkeypatch.setattr(embedding_service, "get_default_embedding_model", no_model)

    assert asyncio.run(embedding_service.generate_embedding("question")) is None
