import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import BigInteger, create_engine, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from model.datasource_models import Datasource
from common.exception import MyException
from model.db_connection_pool import Base
from model.db_models import TTerminology
from services import terminology_service


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(element, compiler, **kwargs):
    return "INTEGER"


@compiles(VECTOR, "sqlite")
def compile_vector_as_text(element, compiler, **kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def compile_jsonb_as_json(element, compiler, **kwargs):
    return "JSON"


class TerminologyPool:
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
def terminology_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Datasource.__table__, TTerminology.__table__],
    )
    monkeypatch.setattr(
        terminology_service,
        "pool",
        TerminologyPool(engine),
    )
    async def no_embedding(ids):
        return None

    monkeypatch.setattr(
        terminology_service,
        "save_terminology_embeddings",
        no_embedding,
    )
    yield engine
    engine.dispose()


def test_create_and_list_terminology_parent_with_synonyms(
    terminology_database,
):
    created = asyncio.run(
        terminology_service.create_terminology(
            "销售额",
            "订单实际成交金额汇总",
            ["营业额", "销售收入", "  "],
            False,
            [],
        )
    )

    page = asyncio.run(
        terminology_service.query_terminology_list(1, 10)
    )

    assert created is True
    assert page.total_count == 1
    assert page.total_pages == 1
    assert page.records[0]["word"] == "销售额"
    assert page.records[0]["other_words"] == ["营业额", "销售收入"]
    assert page.records[0]["datasource_ids"] == []
    assert "embedding" not in page.records[0]

    with Session(terminology_database) as session:
        records = session.scalars(
            select(TTerminology).order_by(TTerminology.id)
        ).all()
        assert len(records) == 3
        assert records[0].pid is None
        assert [record.pid for record in records[1:]] == [records[0].id] * 2
        assert all(record.embedding is None for record in records)


def test_create_terminology_persists_parent_and_synonym_embeddings(
    terminology_database,
    monkeypatch,
):
    vectors = {
        "Sales": [0.1, 0.2],
        "Revenue": [0.3, 0.4],
    }

    async def fake_save_embeddings(ids):
        with terminology_service.pool.get_session() as session:
            records = session.query(TTerminology).filter(
                or_(
                    TTerminology.id.in_(ids),
                    TTerminology.pid.in_(ids),
                )
            ).all()
            for record in records:
                record.embedding = vectors[record.word]

    monkeypatch.setattr(
        terminology_service,
        "save_terminology_embeddings",
        fake_save_embeddings,
    )

    assert asyncio.run(
        terminology_service.create_terminology(
            "Sales",
            "Order revenue",
            ["Revenue"],
            False,
            [],
        )
    )

    with Session(terminology_database) as session:
        records = session.scalars(
            select(TTerminology).order_by(TTerminology.id)
        ).all()
        assert [list(record.embedding) for record in records] == [
            [0.1, 0.2],
            [0.3, 0.4],
        ]


def test_online_embedding_worker_matches_source_flow(
    terminology_database,
    monkeypatch,
):
    with Session(terminology_database) as session:
        parent = TTerminology(word="Sales", oid=1, enabled=True)
        session.add(parent)
        session.flush()
        session.add(TTerminology(pid=parent.id, word="Revenue", oid=1, enabled=True))
        session.commit()
        parent_id = parent.id

    async def fake_model():
        return {
            "supplier": 3,
            "api_key": "key",
            "api_domain": "http://localhost:11434",
            "base_model": "embedding-model",
        }

    class Embeddings:
        def create(self, model, input):
            assert model == "embedding-model"
            vectors = {"Sales": [0.1, 0.2], "Revenue": [0.3, 0.4]}
            return SimpleNamespace(data=[SimpleNamespace(embedding=vectors[input])])

    class Client:
        def __init__(self, api_key, base_url):
            assert api_key == "key"
            assert base_url == "http://localhost:11434/v1"
            self.embeddings = Embeddings()

    import openai

    monkeypatch.setattr(terminology_service, "get_default_embedding_model", fake_model)
    monkeypatch.setattr(openai, "OpenAI", Client)

    terminology_service._save_terminology_embeddings_sync([parent_id])

    with Session(terminology_database) as session:
        records = session.scalars(select(TTerminology).order_by(TTerminology.id)).all()
        assert [list(record.embedding) for record in records] == [
            [0.1, 0.2],
            [0.3, 0.4],
        ]


def test_search_by_synonym_returns_parent_and_datasource_names(
    terminology_database,
):
    with Session(terminology_database) as session:
        session.add_all(
            [
                Datasource(
                    id=10,
                    name="业务库",
                    type="pg",
                    configuration="{}",
                ),
                Datasource(
                    id=11,
                    name="数据仓库",
                    type="pg",
                    configuration="{}",
                ),
            ]
        )
        session.commit()

    asyncio.run(
        terminology_service.create_terminology(
            "销售额",
            "订单实际成交金额汇总",
            ["营业额", "销售收入"],
            True,
            [10, 11],
        )
    )

    page = asyncio.run(
        terminology_service.query_terminology_list(
            1,
            10,
            "营业额",
        )
    )

    assert page.total_count == 1
    assert page.records[0]["word"] == "销售额"
    assert page.records[0]["datasource_ids"] == [10, 11]
    assert page.records[0]["datasource_names"] == ["业务库", "数据仓库"]

    empty = asyncio.run(
        terminology_service.query_terminology_list(1, 10, "不存在")
    )
    assert empty.records == []
    assert empty.total_count == 0


def test_create_rejects_existing_parent_or_synonym(
    terminology_database,
):
    asyncio.run(
        terminology_service.create_terminology(
            "销售额",
            "描述",
            ["营业额"],
            False,
            [],
        )
    )

    with pytest.raises(MyException, match="销售额.*已存在"):
        asyncio.run(
            terminology_service.create_terminology(
                "销售额",
                "重复",
                [],
                False,
                [],
            )
        )

    with pytest.raises(MyException, match="营业额.*已存在"):
        asyncio.run(
            terminology_service.create_terminology(
                "新术语",
                "重复同义词",
                ["营业额"],
                False,
                [],
            )
        )


def test_parent_search_paginates_by_create_time_descending(
    terminology_database,
):
    now = datetime.now()
    with Session(terminology_database) as session:
        session.add_all(
            [
                TTerminology(
                    word="销售额旧口径",
                    description="旧",
                    enabled=True,
                    create_time=now - timedelta(minutes=1),
                ),
                TTerminology(
                    word="销售额新口径",
                    description="新",
                    enabled=True,
                    create_time=now,
                ),
            ]
        )
        session.commit()

    first_page = asyncio.run(
        terminology_service.query_terminology_list(
            1,
            1,
            "销售额",
        )
    )
    second_page = asyncio.run(
        terminology_service.query_terminology_list(
            2,
            1,
            "销售额",
        )
    )

    assert first_page.total_count == 2
    assert first_page.total_pages == 2
    assert first_page.records[0]["word"] == "销售额新口径"
    assert second_page.records[0]["word"] == "销售额旧口径"


def test_update_detail_enable_and_delete_parent_with_children(
    terminology_database,
):
    asyncio.run(
        terminology_service.create_terminology(
            "旧术语",
            "旧描述",
            ["旧同义词"],
            False,
            [],
        )
    )
    with Session(terminology_database) as session:
        parent_id = session.scalar(
            select(TTerminology.id).where(TTerminology.pid.is_(None))
        )

    updated = asyncio.run(
        terminology_service.update_terminology(
            parent_id,
            "新术语",
            "新描述",
            ["新同义词一", "新同义词二"],
            True,
            [10],
        )
    )
    detail = asyncio.run(
        terminology_service.get_terminology_detail(parent_id)
    )

    assert updated is True
    assert detail["word"] == "新术语"
    assert detail["description"] == "新描述"
    assert detail["other_words"] == ["新同义词一", "新同义词二"]
    assert detail["datasource_ids"] == [10]
    assert "embedding" not in detail

    assert asyncio.run(
        terminology_service.enable_terminology(parent_id, False)
    )
    with Session(terminology_database) as session:
        records = session.scalars(select(TTerminology)).all()
        assert len(records) == 3
        assert all(record.enabled is False for record in records)
        assert all(record.embedding is None for record in records)

    assert asyncio.run(
        terminology_service.delete_terminology([parent_id])
    )
    with Session(terminology_database) as session:
        assert session.scalars(select(TTerminology)).all() == []


def test_update_missing_terminology_and_missing_detail(
    terminology_database,
):
    with pytest.raises(MyException, match="术语不存在"):
        asyncio.run(
            terminology_service.update_terminology(
                99999,
                "不存在",
                "描述",
                [],
                False,
                [],
            )
        )

    assert asyncio.run(
        terminology_service.get_terminology_detail(99999)
    ) is None


def test_update_allows_own_synonym_but_rejects_other_terms(
    terminology_database,
):
    asyncio.run(
        terminology_service.create_terminology(
            "销售额",
            "描述",
            ["营业额"],
            False,
            [],
        )
    )
    asyncio.run(
        terminology_service.create_terminology(
            "订单量",
            "描述",
            ["订单数"],
            False,
            [],
        )
    )
    with Session(terminology_database) as session:
        sales_id = session.scalar(
            select(TTerminology.id).where(
                TTerminology.word == "销售额"
            )
        )

    assert asyncio.run(
        terminology_service.update_terminology(
            sales_id,
            "销售额",
            "新描述",
            ["营业额"],
            False,
            [],
        )
    )

    with pytest.raises(MyException, match="订单数.*已存在"):
        asyncio.run(
            terminology_service.update_terminology(
                sales_id,
                "销售额",
                "冲突",
                ["订单数"],
                False,
                [],
            )
        )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('["营业额", "销售收入"]', ["营业额", "销售收入"]),
        ('```json\n["营业额"]\n```', ["营业额"]),
        ("营业额, 销售收入", ["营业额", "销售收入"]),
    ],
)
def test_generate_synonyms_parses_source_response_formats(
    monkeypatch,
    content,
    expected,
):
    class FakeLlm:
        async def ainvoke(self, messages):
            assert "销售额" in messages[0].content
            return SimpleNamespace(content=content)

    monkeypatch.setattr(
        terminology_service,
        "get_llm",
        lambda: FakeLlm(),
        raising=False,
    )

    result = asyncio.run(
        terminology_service.generate_synonyms_by_llm("销售额")
    )

    assert result == expected


def test_generate_synonyms_reports_missing_default_model(monkeypatch):
    def missing_model():
        raise ValueError("No default AI model configured in database.")

    monkeypatch.setattr(
        terminology_service,
        "get_llm",
        missing_model,
        raising=False,
    )

    with pytest.raises(
        MyException,
        match="未配置默认AI模型",
    ):
        asyncio.run(
            terminology_service.generate_synonyms_by_llm("销售额")
        )


def test_datasource_filter_uses_source_postgresql_json_expression(
    monkeypatch,
):
    class FakeQuery:
        def __init__(self):
            self.filters = []

        def filter(self, *expressions):
            self.filters.extend(expressions)
            return self

        def count(self):
            return 0

        def order_by(self, *args):
            return self

        def offset(self, value):
            return self

        def limit(self, value):
            return self

        def all(self):
            return []

    class FakePool:
        def __init__(self):
            self.query = FakeQuery()

        @contextmanager
        def get_session(self):
            class FakeSession:
                def __init__(self, query):
                    self.query_result = query

                def query(self, *args):
                    return self.query_result

            yield FakeSession(self.query)

    fake_pool = FakePool()
    monkeypatch.setattr(terminology_service, "pool", fake_pool)

    page = asyncio.run(
        terminology_service.query_terminology_list(
            1,
            10,
            dslist=[10, 11],
        )
    )
    compiled_filters = " ".join(
        str(expression) for expression in fake_pool.query.filters
    )

    assert page.total_count == 0
    assert "json_array_elements_text(datasource_ids::json)" in compiled_filters
    assert "'10', '11'" in compiled_filters


def test_terminology_http_routes_match_source_contract():
    import controllers.terminology_api as terminology_api

    routes = {
        (route.uri, tuple(sorted(route.methods)))
        for route in terminology_api.bp._future_routes
    }

    assert routes == {
        ("/list", ("POST",)),
        ("/save", ("POST",)),
        ("/delete", ("POST",)),
        ("/<id:int>/enable/<enabled:int>", ("GET",)),
        ("/<id:int>", ("GET",)),
        ("/generate_synonyms", ("POST",)),
    }


def _find_wrapper(handler, filename):
    current = handler
    while True:
        if current.__code__.co_filename.endswith(filename):
            return current
        if not hasattr(current, "__wrapped__"):
            raise AssertionError(f"wrapper not found: {filename}")
        current = current.__wrapped__


def test_all_terminology_handlers_reject_missing_token():
    import controllers.terminology_api as terminology_api

    request = SimpleNamespace(headers={})
    handlers = [
        terminology_api.list_terminology,
        terminology_api.save_term,
        terminology_api.delete_term,
        terminology_api.enable_term,
        terminology_api.get_term,
        terminology_api.gen_synonyms,
    ]

    for handler in handlers:
        token_wrapper = _find_wrapper(
            handler,
            "token_decorator.py",
        )
        response = asyncio.run(token_wrapper(request))
        assert response.status == 401


def test_save_api_wraps_request_validation_errors():
    import json
    import controllers.terminology_api as terminology_api

    request = SimpleNamespace(
        method="POST",
        path="/terminology/save",
        args={},
        content_type="application/json",
        json={},
        form={},
        match_info={},
    )
    response_wrapper = _find_wrapper(
        terminology_api.save_term,
        "res_decorator.py",
    )

    response = asyncio.run(response_wrapper(request))
    body = json.loads(response.body)

    assert body["code"] == 400
    assert "参数验证失败" in body["msg"]
