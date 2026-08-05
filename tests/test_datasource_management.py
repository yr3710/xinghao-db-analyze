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
    ConnectType,
    DB,
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


def test_database_enum_matches_aix_db_source():
    expected = {
        "mysql": ("MySQL", "`", "`", ConnectType.sqlalchemy),
        "pg": ("PostgreSQL", '"', '"', ConnectType.sqlalchemy),
        "oracle": ("Oracle", '"', '"', ConnectType.sqlalchemy),
        "sqlServer": ("SQL Server", "[", "]", ConnectType.sqlalchemy),
        "ck": ("ClickHouse", '"', '"', ConnectType.sqlalchemy),
        "dm": ("达梦", '"', '"', ConnectType.py_driver),
        "doris": ("Apache Doris", "`", "`", ConnectType.py_driver),
        "redshift": ("AWS Redshift", '"', '"', ConnectType.py_driver),
        "es": ("Elasticsearch", '"', '"', ConnectType.py_driver),
        "kingbase": ("Kingbase", '"', '"', ConnectType.py_driver),
        "starrocks": ("StarRocks", "`", "`", ConnectType.py_driver),
    }

    assert {
        item.type_code: (
            item.db_name,
            item.prefix,
            item.suffix,
            item.connect_type,
        )
        for item in DB
    } == expected
    assert DB.get_db("SQLSERVER") is DB.sqlServer
    assert DB.get_db("unknown", default_if_none=True) is DB.pg
    with pytest.raises(ValueError, match="不支持的数据库类型"):
        DB.get_db("unknown")


@pytest.mark.parametrize(
    ("ds_type", "expected"),
    [
        (
            "mysql",
            "mysql+pymysql://report%20user:p%40ss/word@db.local:3306/analytics?charset=utf8mb4",
        ),
        (
            "pg",
            "postgresql+psycopg2://report%20user:p%40ss/word@db.local:5432/analytics?sslmode=disable",
        ),
        (
            "sqlServer",
            "mssql+pymssql://report%20user:p%40ss/word@db.local:1433/analytics?charset=utf8",
        ),
        (
            "ck",
            "clickhouse+http://report%20user:p%40ss/word@db.local:8123/analytics?protocol=http",
        ),
    ],
)
def test_sqlalchemy_connection_uris_match_source(ds_type, expected):
    default_ports = {
        "mysql": 3306,
        "pg": 5432,
        "sqlServer": 1433,
        "ck": 8123,
    }
    extra_jdbc = {
        "mysql": "charset=utf8mb4",
        "pg": "sslmode=disable",
        "sqlServer": "charset=utf8",
        "ck": "protocol=http",
    }
    config = {
        "host": "db.local",
        "port": default_ports[ds_type],
        "username": "report user",
        "password": "p@ss/word",
        "database": "analytics",
        "extraJdbc": extra_jdbc[ds_type],
    }

    assert DatasourceConnectionUtil.build_connection_uri(ds_type, config) == expected


def test_oracle_connection_uris_match_source_modes():
    config = {
        "host": "oracle.local",
        "port": 1521,
        "username": "system",
        "password": "p@ss",
        "database": "ORCL",
        "mode": "service_name",
        "extraJdbc": "expire_time=10",
    }
    assert DatasourceConnectionUtil.build_connection_uri("oracle", config) == (
        "oracle+oracledb://system:p%40ss@oracle.local:1521"
        "?service_name=ORCL&expire_time=10"
    )

    config["mode"] = "sid"
    assert DatasourceConnectionUtil.build_connection_uri("oracle", config) == (
        "oracle+oracledb://system:p%40ss@oracle.local:1521/ORCL"
        "?expire_time=10"
    )


@pytest.mark.parametrize(
    ("ds_type", "expected_sql", "expected_connect_args"),
    [
        ("mysql", "SELECT 1", {"connect_timeout": 12}),
        ("pg", "SELECT 1", {"connect_timeout": 12}),
        ("oracle", "SELECT 1 FROM DUAL", None),
        (
            "sqlServer",
            "SELECT 1",
            {"timeout": 12, "login_timeout": 12, "encryption": "off"},
        ),
        ("ck", "SELECT 1", {"connect_timeout": 12}),
    ],
)
def test_sqlalchemy_connection_tests_match_source(
    monkeypatch,
    ds_type,
    expected_sql,
    expected_connect_args,
):
    state = {}

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

    def fake_create_engine(uri, **kwargs):
        state["uri"] = uri
        state["kwargs"] = kwargs
        return FakeEngine()

    monkeypatch.setattr(datasource_util, "create_engine", fake_create_engine)
    config = {
        "host": "db.local",
        "port": 1521 if ds_type == "oracle" else 5432,
        "username": "user",
        "password": "password",
        "database": "analytics",
        "timeout": 12,
    }

    connected, message = DatasourceConnectionUtil.test_connection(ds_type, config)

    assert connected
    assert message == ""
    assert state["sql"] == expected_sql
    assert state["kwargs"]["pool_pre_ping"] is True
    assert state["kwargs"].get("connect_args") == expected_connect_args


def test_extra_jdbc_parser_matches_source():
    assert DatasourceConnectionUtil._get_extra_config(
        {"extraJdbc": "ssl=true&charset=utf8mb4&invalid&empty="}
    ) == {"ssl": "true", "charset": "utf8mb4"}


def test_optional_native_drivers_report_source_errors(monkeypatch):
    monkeypatch.setattr(datasource_util, "dmPython", None)
    monkeypatch.setattr(datasource_util, "redshift_connector", None)

    dm_connected, dm_message = DatasourceConnectionUtil.test_connection(
        "dm", {"host": "dm.local"}
    )
    redshift_connected, redshift_message = (
        DatasourceConnectionUtil.test_connection(
            "redshift", {"host": "redshift.local"}
        )
    )

    assert not dm_connected
    assert dm_message == "未安装达梦数据库驱动 dmPython"
    assert not redshift_connected
    assert redshift_message == "未安装 redshift_connector 驱动"


@pytest.mark.parametrize(
    ("ds_type", "driver_name"),
    [("dm", "dmPython"), ("redshift", "redshift_connector")],
)
def test_optional_native_driver_connections_match_source(
    monkeypatch,
    ds_type,
    driver_name,
):
    state = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, **kwargs):
            state["sql"] = sql
            state["execute_kwargs"] = kwargs

        def fetchall(self):
            state["fetched"] = True

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return FakeCursor()

    fake_driver = SimpleNamespace(
        connect=lambda **kwargs: state.update(kwargs=kwargs) or FakeConnection()
    )
    monkeypatch.setattr(datasource_util, driver_name, fake_driver)

    connected, message = DatasourceConnectionUtil.test_connection(
        ds_type,
        {
            "host": "database.local",
            "port": 5236 if ds_type == "dm" else 5439,
            "username": "system",
            "password": "secret",
            "database": "analytics",
            "timeout": 18,
        },
    )

    assert connected
    assert message == ""
    assert state["sql"] == "SELECT 1"
    if ds_type == "dm":
        assert state["execute_kwargs"] == {"timeout": 18}
        assert state["fetched"] is True
        assert state["kwargs"]["server"] == "database.local"
    else:
        assert state["kwargs"]["timeout"] == 18
        assert state["kwargs"]["database"] == "analytics"


@pytest.mark.parametrize("ds_type", ["doris", "starrocks"])
def test_mysql_protocol_native_connections_match_source(monkeypatch, ds_type):
    state = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql):
            state["sql"] = sql

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return FakeCursor()

    def fake_connect(**kwargs):
        state["kwargs"] = kwargs
        return FakeConnection()

    monkeypatch.setattr(datasource_util.pymysql, "connect", fake_connect)
    connected, message = DatasourceConnectionUtil.test_connection(
        ds_type,
        {
            "host": "cluster.local",
            "port": 9030,
            "username": "root",
            "password": "secret",
            "database": "analytics",
            "timeout": 20,
        },
    )

    assert connected
    assert message == ""
    assert state["sql"] == "SELECT 1"
    assert state["kwargs"]["connect_timeout"] == 60
    assert state["kwargs"]["read_timeout"] == 20
    assert state["kwargs"]["write_timeout"] == 20


def test_kingbase_native_connection_matches_source(monkeypatch):
    state = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql):
            state["sql"] = sql

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(
        datasource_util.psycopg2,
        "connect",
        lambda **kwargs: state.update(kwargs=kwargs) or FakeConnection(),
    )
    connected, message = DatasourceConnectionUtil.test_connection(
        "kingbase",
        {
            "host": "kingbase.local",
            "port": 54321,
            "username": "system",
            "password": "secret",
            "database": "analytics",
            "timeout": 8,
        },
    )

    assert connected
    assert message == ""
    assert state["sql"] == "SELECT 1"
    assert state["kwargs"]["connect_timeout"] == 8


def test_elasticsearch_connection_uses_source_ping(monkeypatch):
    class FakeElasticsearch:
        def ping(self):
            return True

    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "_get_es_connect",
        lambda config: FakeElasticsearch(),
    )

    connected, message = DatasourceConnectionUtil.test_connection(
        "es",
        {"host": "http://es.local:9200"},
    )

    assert connected
    assert message == ""


def test_elasticsearch_failed_ping_matches_source(monkeypatch):
    class FakeElasticsearch:
        def ping(self):
            return False

    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "_get_es_connect",
        lambda config: FakeElasticsearch(),
    )

    connected, message = DatasourceConnectionUtil.test_connection(
        "es",
        {"host": "http://es.local:9200"},
    )

    assert not connected
    assert message == "Elasticsearch 连接失败"


def test_unknown_database_type_matches_source_error():
    connected, message = DatasourceConnectionUtil.test_connection(
        "unknown",
        {},
    )

    assert not connected
    assert message == "不支持的数据库类型: unknown"


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
