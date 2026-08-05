import asyncio

import pytest
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from agent.text2sql.rag import terminology_retriever, training_retriever
from model.db_connection_pool import Base
from model.db_models import TDataTraining


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(element, compiler, **kwargs):
    return "INTEGER"


@compiles(VECTOR, "sqlite")
def compile_vector_as_text(element, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[TDataTraining.__table__])
    with Session(engine) as value:
        yield value


def test_training_keyword_retrieval_filters_scope(session, monkeypatch):
    session.add_all([
        TDataTraining(id=1, oid=1, datasource=10, question="本月销售额", description="SELECT 1", enabled=True),
        TDataTraining(id=2, oid=2, datasource=10, question="本月销售额", description="SELECT 2", enabled=True),
        TDataTraining(id=3, oid=1, datasource=11, question="本月销售额", description="SELECT 3", enabled=True),
        TDataTraining(id=4, oid=1, datasource=10, question="本月销售额", description="SELECT 4", enabled=False),
    ])
    session.commit()
    monkeypatch.setattr(training_retriever, "generate_embedding", _no_embedding)

    result = asyncio.run(training_retriever._select_training_by_question(
        session, "销售额", oid=1, datasource_id=10, top_k=5
    ))

    assert result == [{"question": "本月销售额", "suggestion-answer": "SELECT 1"}]


def test_training_xml_matches_original_format():
    assert training_retriever._format_training_examples_to_xml([
        {"question": "销售额", "suggestion-answer": "SELECT sum(amount)"}
    ]) == (
        "<sql-examples>\n"
        "  <sql-example>\n"
        "    <question><![CDATA[销售额]]></question>\n"
        "    <suggestion-answer><![CDATA[SELECT sum(amount)]]></suggestion-answer>\n"
        "  </sql-example>\n"
        "</sql-examples>"
    )


def test_terminology_xml_matches_original_format():
    assert terminology_retriever._format_terminologies_to_xml([
        {"words": ["GMV", "成交总额"], "description": "订单成交金额总和"}
    ]) == (
        "<terminologies>\n"
        "  <terminology>\n"
        "    <words>\n"
        "      <word><![CDATA[GMV]]></word>\n"
        "      <word><![CDATA[成交总额]]></word>\n"
        "    </words>\n"
        "    <description><![CDATA[订单成交金额总和]]></description>\n"
        "  </terminology>\n"
        "</terminologies>"
    )


async def _no_embedding(_text):
    return None
