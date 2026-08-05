import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from common.exception import MyException
from model.datasource_models import Datasource
from model.db_connection_pool import Base
from model.db_models import TAiModel, TDataTraining
from services import data_training_service
import controllers.data_training_api as data_training_api


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(element, compiler, **kwargs):
    return "INTEGER"


@compiles(VECTOR, "sqlite")
def compile_vector_as_text(element, compiler, **kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def compile_jsonb_as_json(element, compiler, **kwargs):
    return "JSON"


class TrainingPool:
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


@pytest.fixture
def training_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Datasource.__table__,
            TAiModel.__table__,
            TDataTraining.__table__,
        ],
    )
    monkeypatch.setattr(
        data_training_service,
        "pool",
        TrainingPool(engine),
    )
    async def no_embedding(text):
        return None

    monkeypatch.setattr(
        data_training_service,
        "generate_embedding",
        no_embedding,
    )
    with Session(engine) as session:
        session.add(
            Datasource(
                id=10,
                name="Analytics",
                type="pg",
                configuration="{}",
            )
        )
        session.add(
            TAiModel(
                id=20,
                supplier=1,
                name="Advanced App",
                model_type=1,
                base_model="model",
                default_model=False,
                api_domain="http://example.test",
                protocol=1,
                status=1,
            )
        )
        session.commit()
    yield engine
    engine.dispose()


def test_create_and_page_training_without_embedding(training_database):
    created = asyncio.run(
        data_training_service.create_training(
            {
                "question": "Monthly revenue?",
                "description": "select sum(amount) from orders",
                "datasource": 10,
                "advanced_application": 20,
                "enabled": True,
            }
        )
    )

    page = asyncio.run(
        data_training_service.page_data_training(
            1,
            10,
            "Revenue",
        )
    )

    assert created is True
    assert page["total_count"] == 1
    assert page["current_page"] == 1
    assert page["total_pages"] == 1
    assert page["records"][0].question == "Monthly revenue?"
    assert page["records"][0].datasource_name == "Analytics"
    assert (
        page["records"][0].advanced_application_name
        == "Advanced App"
    )
    with Session(training_database) as session:
        record = session.scalar(select(TDataTraining))
        assert record.embedding is None


def test_create_training_persists_online_embedding(
    training_database,
    monkeypatch,
):
    async def fake_generate_embedding(text):
        assert text == "Monthly revenue?"
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(
        data_training_service,
        "generate_embedding",
        fake_generate_embedding,
    )

    assert asyncio.run(
        data_training_service.create_training(
            {
                "question": "Monthly revenue?",
                "description": "select sum(amount) from orders",
                "datasource": 10,
                "enabled": True,
            }
        )
    )

    with Session(training_database) as session:
        record = session.scalar(select(TDataTraining))
        assert list(record.embedding) == [0.1, 0.2, 0.3]


def test_update_training_only_recalculates_changed_question(
    training_database,
    monkeypatch,
):
    calls = []

    async def fake_generate_embedding(text):
        calls.append(text)
        return [0.4, 0.5]

    monkeypatch.setattr(
        data_training_service,
        "generate_embedding",
        fake_generate_embedding,
    )
    assert asyncio.run(
        data_training_service.create_training(
            {
                "question": "Old question",
                "description": "select 1",
                "datasource": 10,
            }
        )
    )
    with Session(training_database) as session:
        training_id = session.scalar(select(TDataTraining.id))

    calls.clear()
    assert asyncio.run(
        data_training_service.update_training(
            {
                "id": training_id,
                "question": "Old question",
                "description": "select 2",
            }
        )
    )
    assert calls == []

    assert asyncio.run(
        data_training_service.update_training(
            {
                "id": training_id,
                "question": "New question",
                "description": "select 3",
            }
        )
    )
    assert calls == ["New question"]
    with Session(training_database) as session:
        record = session.get(TDataTraining, training_id)
        assert list(record.embedding) == [0.4, 0.5]


def test_create_training_keeps_source_validation_and_duplicate_scope(
    training_database,
):
    with pytest.raises(MyException, match="Question cannot be empty"):
        asyncio.run(
            data_training_service.create_training(
                {"question": "", "description": "select 1"}
            )
        )

    data = {
        "question": "Order count?",
        "description": "select count(*) from orders",
        "datasource": 10,
        "advanced_application": None,
        "enabled": True,
    }
    assert asyncio.run(data_training_service.create_training(data))
    with pytest.raises(
        MyException,
        match="Training data already exists",
    ):
        asyncio.run(data_training_service.create_training(data))

    generic = dict(data)
    generic["datasource"] = None
    with pytest.raises(
        MyException,
        match="Training data already exists",
    ):
        asyncio.run(data_training_service.create_training(generic))

    generic["question"] = "Generic question"
    assert asyncio.run(data_training_service.create_training(generic))
    scoped = dict(generic)
    scoped["datasource"] = 10
    assert asyncio.run(data_training_service.create_training(scoped))


def test_page_training_paginates_and_orders_by_create_time(
    training_database,
):
    now = datetime.now()
    with Session(training_database) as session:
        session.add_all(
            [
                TDataTraining(
                    oid=1,
                    question="Older question",
                    description="select 1",
                    enabled=True,
                    create_time=now - timedelta(minutes=1),
                ),
                TDataTraining(
                    oid=1,
                    question="Newer question",
                    description="select 2",
                    enabled=True,
                    create_time=now,
                ),
                TDataTraining(
                    oid=2,
                    question="Other organization",
                    description="select 3",
                    enabled=True,
                    create_time=now + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    first_page = asyncio.run(
        data_training_service.page_data_training(1, 1)
    )
    second_page = asyncio.run(
        data_training_service.page_data_training(2, 1)
    )

    assert first_page["total_count"] == 2
    assert first_page["total_pages"] == 2
    assert first_page["records"][0].question == "Newer question"
    assert second_page["records"][0].question == "Older question"


def test_update_delete_and_enable_training(training_database):
    assert asyncio.run(
        data_training_service.create_training(
            {
                "question": "Old question",
                "description": "select 1",
                "datasource": 10,
                "enabled": True,
            }
        )
    )
    with Session(training_database) as session:
        training_id = session.scalar(select(TDataTraining.id))

    assert asyncio.run(
        data_training_service.update_training(
            {
                "id": training_id,
                "question": "New question",
                "description": "select 2",
                "datasource": None,
                "advanced_application": None,
                "enabled": False,
            }
        )
    )
    with Session(training_database) as session:
        record = session.get(TDataTraining, training_id)
        assert record.question == "New question"
        assert record.description == "select 2"
        assert record.datasource is None
        assert record.enabled is False
        assert record.embedding is None

    assert asyncio.run(
        data_training_service.enable_training(training_id, True)
    )
    with Session(training_database) as session:
        assert session.get(TDataTraining, training_id).enabled is True

    assert asyncio.run(
        data_training_service.delete_training([training_id, 99999])
    )
    with Session(training_database) as session:
        assert session.get(TDataTraining, training_id) is None


def test_missing_training_update_and_enable_match_source_errors(
    training_database,
):
    with pytest.raises(MyException, match="Training data not found"):
        asyncio.run(
            data_training_service.update_training(
                {
                    "id": 99999,
                    "question": "Missing",
                    "description": "select 1",
                }
            )
        )
    with pytest.raises(MyException, match="Training data not found"):
        asyncio.run(
            data_training_service.enable_training(99999, True)
        )


def test_data_training_http_routes_match_source_contract():
    routes = {
        (route.uri, tuple(sorted(route.methods)))
        for route in data_training_api.bp._future_routes
    }

    assert routes == {
        ("/page/<page:int>/<size:int>", ("GET",)),
        ("/", ("PUT",)),
        ("/", ("DELETE",)),
        ("/<id:int>/enable/<enabled:str>", ("GET",)),
    }
