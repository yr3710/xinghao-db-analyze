import asyncio
import base64
import json
from types import SimpleNamespace

import pytest
from Crypto.Cipher import AES
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import common.datasource_util as datasource_util
import services.datasource_service as datasource_service_module
import services.user_service as user_service
from common.datasource_util import (
    DatasourceConfigUtil,
    DatasourceConnectionUtil,
)
from common.exception import MyException
from model.datasource_models import (
    Datasource,
    DatasourceAuth,
    DatasourceField,
    DatasourceTable,
)
from model.db_connection_pool import Base
from model.db_models import TUser
from services.datasource_service import DatasourceService


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(element, compiler, **kwargs):
    return "INTEGER"


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            TUser.__table__,
            Datasource.__table__,
            DatasourceTable.__table__,
            DatasourceField.__table__,
            DatasourceAuth.__table__,
        ],
    )
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def pg_config(password="p@ssword"):
    return {
        "host": "127.0.0.1",
        "port": 5432,
        "username": "report user",
        "password": password,
        "database": "analytics",
        "dbSchema": "public",
        "extraJdbc": "sslmode=disable",
        "timeout": 10,
    }


def create_datasource(session, name="Reporting"):
    return DatasourceService.create_datasource(
        session,
        {
            "name": name,
            "type": "pg",
            "type_name": "PostgreSQL",
            "configuration": json.dumps(pg_config()),
        },
        user_id=1,
    )


def test_aix_db_aes_ecb_configuration_round_trip():
    config = pg_config()
    encrypted = DatasourceConfigUtil.encrypt_config(config)

    assert not encrypted.startswith("v1:")
    assert base64.b64decode(encrypted)
    assert len(base64.b64decode(encrypted)) % AES.block_size == 0
    assert DatasourceConfigUtil.encrypt_config(config) == encrypted
    assert DatasourceConfigUtil.decrypt_config(encrypted) == config


def test_postgresql_uri_matches_source_encoding():
    uri = DatasourceConnectionUtil.build_connection_uri(
        "pg",
        pg_config("p@ss/word"),
    )

    assert "report%20user" in uri
    assert "p%40ss/word" in uri
    assert uri.startswith("postgresql+psycopg2://")
    assert "sslmode=disable" in uri


def test_connection_executes_select_one(monkeypatch):
    state = {"sql": ""}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement):
            state["sql"] = str(statement)

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(
        datasource_util,
        "create_engine",
        lambda *args, **kwargs: FakeEngine(),
    )

    connected, message = DatasourceConnectionUtil.test_connection(
        "pg",
        pg_config(),
    )

    assert connected
    assert message == ""
    assert state["sql"] == "SELECT 1"


def test_connection_returns_driver_error_like_source(monkeypatch):
    monkeypatch.setattr(
        datasource_util,
        "create_engine",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("driver connection failed")
        ),
    )

    connected, message = DatasourceConnectionUtil.test_connection(
        "pg",
        pg_config(),
    )

    assert not connected
    assert message == "driver connection failed"


def test_create_encrypts_configuration_with_source_format(session):
    datasource = create_datasource(session)

    assert datasource.name == "Reporting"
    assert not datasource.configuration.startswith("v1:")
    assert DatasourceConfigUtil.decrypt_config(
        datasource.configuration
    ) == pg_config()


def test_source_allows_duplicate_names(session):
    create_datasource(session, "Reporting")
    create_datasource(session, "reporting")

    assert session.query(Datasource).count() == 2


def test_update_uses_password_returned_by_source_detail(session):
    datasource = create_datasource(session)
    changed = pg_config("new-password")
    changed["host"] = "db.internal"

    DatasourceService.update_datasource(
        session,
        datasource.id,
        {"configuration": json.dumps(changed)},
    )

    assert DatasourceConfigUtil.decrypt_config(
        datasource.configuration
    ) == changed


def test_regular_user_only_sees_authorized_datasource(
    session,
    monkeypatch,
):
    first = create_datasource(session, "First")
    create_datasource(session, "Second")
    session.add(
        DatasourceAuth(
            datasource_id=first.id,
            user_id=2,
            enable=True,
        )
    )
    session.flush()
    monkeypatch.setattr(
        datasource_service_module,
        "is_admin",
        lambda user_id: False,
    )

    records = DatasourceService.get_datasource_list(session, 2)

    assert [record.name for record in records] == ["First"]


def test_authorization_replaces_old_rows_exactly_like_source(session):
    datasource = create_datasource(session)

    DatasourceService.authorize_datasource(
        session,
        datasource.id,
        [1, 2, 999],
    )
    assert DatasourceService.get_authorized_users(
        session,
        datasource.id,
    ) == [1, 2, 999]

    DatasourceService.authorize_datasource(
        session,
        datasource.id,
        [],
    )
    assert DatasourceService.get_authorized_users(
        session,
        datasource.id,
    ) == []


def test_delete_matches_source_association_scope(session):
    datasource = create_datasource(session)
    table = DatasourceTable(
        ds_id=datasource.id,
        table_name="orders",
    )
    session.add(table)
    session.flush()
    session.add_all(
        [
            DatasourceField(
                ds_id=datasource.id,
                table_id=table.id,
                field_name="id",
            ),
            DatasourceAuth(
                datasource_id=datasource.id,
                user_id=2,
                enable=True,
            ),
        ]
    )
    session.flush()

    assert DatasourceService.delete_datasource(
        session,
        datasource.id,
    )
    assert session.scalars(select(DatasourceTable)).all() == []
    assert session.scalars(select(DatasourceField)).all() == []
    assert len(session.scalars(select(DatasourceAuth)).all()) == 1


def test_admin_guard_uses_source_user_info(monkeypatch):
    async def regular_user(request):
        return {"id": 2, "role": "user"}

    monkeypatch.setattr(user_service, "get_user_info", regular_user)
    request = SimpleNamespace(ctx=SimpleNamespace())

    with pytest.raises(MyException, match="只有管理员"):
        asyncio.run(
            __import__(
                "common.permission_util",
                fromlist=["check_admin_permission"],
            ).check_admin_permission(request)
        )
