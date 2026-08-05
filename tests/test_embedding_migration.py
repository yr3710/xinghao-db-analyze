import asyncio
import inspect
import json
from contextlib import contextmanager

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from model.datasource_models import Datasource, DatasourceField, DatasourceTable
from model.db_connection_pool import Base
from model.db_models import TDataTraining, TTerminology


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(element, compiler, **kwargs):
    return "INTEGER"


@compiles(VECTOR, "sqlite")
def compile_vector_as_text(element, compiler, **kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def compile_jsonb_as_json(element, compiler, **kwargs):
    return "JSON"


class MigrationPool:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def get_session(self):
        with Session(self.engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


def build_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Datasource.__table__,
            DatasourceTable.__table__,
            DatasourceField.__table__,
            TTerminology.__table__,
            TDataTraining.__table__,
        ],
    )
    with Session(engine) as session:
        session.add(
            Datasource(
                id=1,
                name="Analytics",
                type="pg",
                configuration="{}",
            )
        )
        session.add_all(
            [
                TTerminology(id=1, word="Sales", oid=1, enabled=True),
                TTerminology(
                    id=2,
                    pid=1,
                    word="Revenue",
                    oid=1,
                    enabled=True,
                ),
                TDataTraining(
                    id=1,
                    question="Monthly sales?",
                    oid=1,
                    enabled=True,
                ),
            ]
        )
        table = DatasourceTable(
            id=1,
            ds_id=1,
            table_name="orders",
            table_comment="Orders",
        )
        session.add(table)
        session.add(
            DatasourceField(
                id=1,
                ds_id=1,
                table_id=1,
                field_name="amount",
                field_comment="Order amount",
            )
        )
        session.commit()
    return engine


def test_current_embedding_model_info_uses_online_model(monkeypatch):
    import services.embedding_migration_service as migration

    async def fake_model():
        return {"base_model": "text-embedding-3-small"}

    async def fake_embedding(text):
        assert text == "test"
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(migration, "get_default_embedding_model", fake_model)
    monkeypatch.setattr(migration, "generate_embedding", fake_embedding)

    assert asyncio.run(migration.get_current_embedding_model_info()) == {
        "model_type": "online",
        "model_name": "text-embedding-3-small",
        "dimension": 3,
    }


def test_recalculate_all_embeddings_updates_all_modules(monkeypatch):
    import services.embedding_migration_service as migration

    engine = build_database()
    monkeypatch.setattr(migration, "pool", MigrationPool(engine))

    vectors = {
        "Sales": [0.1, 0.2],
        "Revenue": [0.3, 0.4],
        "Monthly sales?": [0.5, 0.6],
    }

    async def fake_embedding(text):
        return vectors[text]

    async def fake_info():
        return {
            "model_type": "online",
            "model_name": "embedding-model",
            "dimension": 2,
        }

    def fake_table_embeddings(session, items):
        assert len(items) == 1
        items[0]["table"].embedding = "[0.7, 0.8]"

    monkeypatch.setattr(migration, "generate_embedding", fake_embedding)
    monkeypatch.setattr(
        migration,
        "get_current_embedding_model_info",
        fake_info,
    )
    monkeypatch.setattr(
        migration.DatasourceService,
        "_compute_and_save_table_embeddings_batch",
        staticmethod(fake_table_embeddings),
    )

    progress = []

    async def progress_callback(module, current, total, message):
        progress.append((module, current, total, message))

    result = asyncio.run(
        migration.recalculate_all_embeddings(
            ["terminology", "training", "table"],
            progress_callback,
        )
    )

    assert result["success"] is True
    assert set(result["results"]) == {"terminology", "training", "table"}
    assert progress[0][0] == "info"
    with Session(engine) as session:
        terms = session.scalars(
            select(TTerminology).order_by(TTerminology.id)
        ).all()
        training = session.get(TDataTraining, 1)
        table = session.get(DatasourceTable, 1)
        assert [list(term.embedding) for term in terms] == [
            [0.1, 0.2],
            [0.3, 0.4],
        ]
        assert list(training.embedding) == [0.5, 0.6]
        assert table.embedding == "[0.7, 0.8]"
    engine.dispose()


def test_failed_embedding_still_reports_final_progress(monkeypatch):
    import services.embedding_migration_service as migration

    engine = build_database()
    monkeypatch.setattr(migration, "pool", MigrationPool(engine))

    async def no_embedding(_text):
        return None

    progress = []

    async def callback(current, total, message):
        progress.append((current, total))

    monkeypatch.setattr(migration, "generate_embedding", no_embedding)
    result = asyncio.run(migration.recalculate_training_embeddings(callback))

    assert result["failed_count"] == 1
    assert progress[-1] == (1, 1)
    engine.dispose()


def test_embedding_migration_routes_match_source_contract():
    import controllers.embedding_migration_api as api

    routes = {
        (route.uri, tuple(sorted(route.methods)))
        for route in api.bp._future_routes
    }

    assert routes == {
        ("/model-info", ("GET",)),
        ("/recalculate", ("POST",)),
        ("/recalculate-sync", ("POST",)),
    }


def test_embedding_migration_sse_event_contract(monkeypatch):
    import controllers.embedding_migration_api as api

    async def fake_recalculate(modules, callback):
        assert modules == ["training"]
        await callback("training", 1, 2, "working")
        await asyncio.sleep(0.55)
        return {"success": True, "results": {}}

    monkeypatch.setattr(api, "recalculate_all_embeddings", fake_recalculate)
    response_stream = asyncio.run(
        inspect.unwrap(api.recalculate_embeddings)(
            type("Request", (), {"json": {"modules": ["training"]}})()
        )
    )
    writer = StreamWriter()
    asyncio.run(response_stream.streaming_fn(writer))
    events = parse_sse(writer.chunks)

    assert [event["type"] for event in events] == [
        "start", "progress", "heartbeat", "complete",
    ]


def test_embedding_migration_sse_error_event(monkeypatch):
    import controllers.embedding_migration_api as api

    async def fail_recalculate(modules, callback):
        raise RuntimeError("boom")

    monkeypatch.setattr(api, "recalculate_all_embeddings", fail_recalculate)
    response_stream = asyncio.run(
        inspect.unwrap(api.recalculate_embeddings)(
            type("Request", (), {"json": {}})()
        )
    )
    writer = StreamWriter()
    asyncio.run(response_stream.streaming_fn(writer))
    events = parse_sse(writer.chunks)

    assert events[-1]["type"] == "error"
    assert "boom" in events[-1]["message"]


class StreamWriter:
    def __init__(self):
        self.chunks = []

    async def write(self, value):
        self.chunks.append(value)


def parse_sse(chunks):
    return [
        json.loads(block[6:])
        for block in "".join(chunks).split("\n\n")
        if block.startswith("data: ")
    ]
