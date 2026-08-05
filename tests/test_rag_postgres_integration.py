import asyncio
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agent.text2sql.rag import terminology_retriever, training_retriever
from config.load_env import load_env
from model.db_models import TDataTraining, TTerminology


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RAG_INTEGRATION") != "1",
    reason="set RUN_RAG_INTEGRATION=1 for real PostgreSQL + pgvector tests",
)


def test_pgvector_hybrid_retrievers_apply_scope_and_top_k(monkeypatch):
    load_env()
    engine = create_engine(os.environ["SQLALCHEMY_DATABASE_URI"])
    session = Session(engine)
    transaction = session.begin()
    try:
        session.add_all([
            TDataTraining(id=-13001, oid=13, datasource=77, question="月度销售额", description="SELECT 1", enabled=True, embedding=[1.0, 0.0]),
            TDataTraining(id=-13002, oid=13, datasource=78, question="月度销售额", description="SELECT 2", enabled=True, embedding=[1.0, 0.0]),
            TDataTraining(id=-13003, oid=13, datasource=77, question="停用销售额", description="SELECT 3", enabled=False, embedding=[1.0, 0.0]),
            TTerminology(id=-13101, oid=13, word="GMV", description="成交总额", specific_ds=False, datasource_ids="[]", enabled=True, embedding=[1.0, 0.0]),
            TTerminology(id=-13102, oid=13, word="收入", description="收入", specific_ds=True, datasource_ids="[77]", enabled=True, embedding=[1.0, 0.0]),
            TTerminology(id=-13103, oid=13, word="其他库术语", description="不可见", specific_ds=True, datasource_ids="[78]", enabled=True, embedding=[1.0, 0.0]),
        ])
        session.flush()

        async def fake_embedding(_text):
            return [1.0, 0.0]

        monkeypatch.setattr(training_retriever, "generate_embedding", fake_embedding)
        monkeypatch.setattr(terminology_retriever, "generate_embedding", fake_embedding)

        training = asyncio.run(training_retriever._select_training_by_question(
            session, "销售额", oid=13, datasource_id=77, top_k=1,
        ))
        terms = asyncio.run(terminology_retriever._select_terminology_by_word(
            session, "GMV", oid=13, datasource_id=77, top_k=10,
        ))

        assert training == [{"question": "月度销售额", "suggestion-answer": "SELECT 1"}]
        assert {tuple(term["words"]) for term in terms} == {("GMV",), ("收入",)}
    finally:
        transaction.rollback()
        session.close()
        engine.dispose()
