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
import controllers.datasource_api as datasource_api
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
def session(monkeypatch):
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
    monkeypatch.setattr(
        DatasourceService,
        "_get_embedding_client",
        staticmethod(lambda: (None, None)),
        raising=False,
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


def test_postgresql_schema_browse_normalizes_tables_and_fields(monkeypatch):
    executed = []

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params):
            executed.append((str(statement), params))
            if "pg_attribute" in str(statement):
                return FakeResult([(b"id", b"bigint", b"primary key")])
            return FakeResult([(b"users", b"user table")])

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(
        datasource_util,
        "create_engine",
        lambda *args, **kwargs: FakeEngine(),
    )

    tables = DatasourceConnectionUtil.get_tables("pg", pg_config())
    fields = DatasourceConnectionUtil.get_fields(
        "pg",
        pg_config(),
        "users",
    )

    assert tables == [
        {"tableName": "users", "tableComment": "user table"}
    ]
    assert fields == [
        {
            "fieldName": "id",
            "fieldType": "bigint",
            "fieldComment": "primary key",
            "fieldIndex": 0,
        }
    ]
    assert executed[0][1] == {"param": "public"}
    assert executed[1][1] == {"param1": "public", "param2": "users"}


def test_elasticsearch_schema_browse_uses_indices_and_mapping(monkeypatch):
    class FakeIndices:
        def get_mapping(self, index):
            assert index == "orders"
            return {
                "orders": {
                    "mappings": {
                        "_meta": {"description": "order index"},
                        "properties": {
                            "id": {
                                "type": "long",
                                "_meta": {"description": "order id"},
                            }
                        },
                    }
                }
            }

    class FakeCat:
        def indices(self, format):
            assert format == "json"
            return [{"index": "orders"}]

    fake_client = SimpleNamespace(cat=FakeCat(), indices=FakeIndices())
    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "_get_es_connect",
        lambda config: fake_client,
    )

    assert DatasourceConnectionUtil.get_tables("es", {}) == [
        {"tableName": "orders", "tableComment": "order index"}
    ]
    assert DatasourceConnectionUtil.get_fields("es", {}, "orders") == [
        {
            "fieldName": "id",
            "fieldType": "long",
            "fieldComment": "order id",
            "fieldIndex": 0,
        }
    ]


def test_schema_sync_persists_and_refreshes_selected_metadata(
    session,
    monkeypatch,
):
    datasource = create_datasource(session)
    session.flush()
    source_tables = [
        {"tableName": "users", "tableComment": "Users"},
        {"tableName": "orders", "tableComment": "Orders"},
    ]
    source_fields = {
        "users": [
            {
                "fieldName": "id",
                "fieldType": "bigint",
                "fieldComment": "User ID",
                "fieldIndex": 0,
            }
        ],
        "orders": [
            {
                "fieldName": "id",
                "fieldType": "bigint",
                "fieldComment": "Order ID",
                "fieldIndex": 0,
            }
        ],
    }
    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "get_tables",
        lambda ds_type, config: source_tables,
    )
    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "get_fields",
        lambda ds_type, config, table_name: source_fields[table_name],
    )

    assert DatasourceService.sync_tables(
        session,
        datasource.id,
        source_tables,
        True,
    )
    assert datasource.num == "2/2"
    assert [row.table_name for row in DatasourceService.get_tables_by_ds_id(
        session,
        datasource.id,
    )] == ["users", "orders"]

    users = session.query(DatasourceTable).filter_by(
        ds_id=datasource.id,
        table_name="users",
    ).one()
    user_id = session.query(DatasourceField).filter_by(
        table_id=users.id,
        field_name="id",
    ).one()
    users.custom_comment = "Business users"
    user_id.custom_comment = "Business user ID"
    source_tables[0]["tableComment"] = "Updated users"
    source_fields["users"] = [
        {
            "fieldName": "email",
            "fieldType": "varchar",
            "fieldComment": "Email",
            "fieldIndex": 0,
        }
    ]

    assert DatasourceService.sync_tables(
        session,
        datasource.id,
        [source_tables[0]],
        False,
    )

    remaining_tables = DatasourceService.get_tables_by_ds_id(
        session,
        datasource.id,
    )
    assert [row.table_name for row in remaining_tables] == ["users"]
    assert remaining_tables[0].table_comment == "Updated users"
    assert remaining_tables[0].custom_comment == "Business users"
    remaining_fields = DatasourceService.get_fields_by_table_id(
        session,
        users.id,
    )
    assert [row.field_name for row in remaining_fields] == ["email"]
    assert datasource.num == "1/2"


def test_empty_schema_sync_keeps_source_cleanup_boundary(session, monkeypatch):
    datasource = create_datasource(session)
    table = DatasourceTable(
        ds_id=datasource.id,
        table_name="users",
        checked=True,
    )
    session.add(table)
    session.flush()
    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "get_tables",
        lambda ds_type, config: [{"tableName": "users"}],
    )

    assert DatasourceService.sync_tables(session, datasource.id, [], False)
    assert session.get(DatasourceTable, table.id) is table
    assert datasource.num == "0/1"


def test_schema_metadata_edits_only_supported_fields(session):
    datasource = create_datasource(session)
    table = DatasourceTable(
        ds_id=datasource.id,
        table_name="users",
        table_comment="Users",
        custom_comment="Users",
        checked=True,
    )
    session.add(table)
    session.flush()
    field = DatasourceField(
        ds_id=datasource.id,
        table_id=table.id,
        field_name="id",
        field_type="bigint",
        custom_comment="ID",
        checked=True,
    )
    session.add(field)
    session.flush()

    assert DatasourceService.save_table(
        session,
        {"id": table.id, "table_name": "renamed", "custom_comment": "Business users", "checked": False},
    )
    assert table.table_name == "users"
    assert table.custom_comment == "Business users"
    assert table.checked is False

    assert DatasourceService.save_field(
        session,
        {"id": field.id, "field_type": "text", "custom_comment": "User ID", "checked": False},
    )
    assert field.field_type == "bigint"
    assert field.custom_comment == "User ID"
    assert field.checked is False


def test_schema_sync_persists_table_document_embedding(session, monkeypatch):
    datasource = create_datasource(session)
    source_tables = [
        {"tableName": "orders", "tableComment": "Orders"},
    ]
    source_fields = [
        {
            "fieldName": "amount",
            "fieldType": "numeric",
            "fieldComment": "Order amount",
            "fieldIndex": 0,
        }
    ]
    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "get_tables",
        lambda ds_type, config: source_tables,
    )
    monkeypatch.setattr(
        DatasourceConnectionUtil,
        "get_fields",
        lambda ds_type, config, table_name: source_fields,
    )

    captured = {}

    class FakeEmbeddings:
        def create(self, *, model, input):
            captured.update(model=model, input=input)
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2])]
            )

    fake_client = SimpleNamespace(embeddings=FakeEmbeddings())
    monkeypatch.setattr(
        DatasourceService,
        "_get_embedding_client",
        staticmethod(lambda: (fake_client, "embedding-model")),
    )

    assert DatasourceService.sync_tables(
        session,
        datasource.id,
        source_tables,
        True,
    )

    table = session.scalar(select(DatasourceTable))
    assert captured == {
        "model": "embedding-model",
        "input": ["orders Orders amount Order amount"],
    }
    assert json.loads(table.embedding) == [0.1, 0.2]


def test_schema_browse_http_routes_match_source_contract():
    routes = {
        (route.uri, tuple(sorted(route.methods)))
        for route in datasource_api.bp._future_routes
    }

    assert {
        ("/getTablesByConf", ("POST",)),
        ("/getFieldsByConf", ("POST",)),
        ("/syncTables/<ds_id:int>", ("POST",)),
        ("/tableList/<ds_id:int>", ("POST",)),
        ("/fieldList/<table_id:int>", ("POST",)),
        ("/saveTable", ("POST",)),
        ("/saveField", ("POST",)),
    }.issubset(routes)


@pytest.mark.parametrize(
    ("ds_type", "table_token", "field_token"),
    [
        ("mysql", "information_schema.TABLES", "INFORMATION_SCHEMA.COLUMNS"),
        ("pg", "pg_class", "pg_catalog.pg_attribute"),
        ("oracle", "ALL_TABLES", "ALL_TAB_COLUMNS"),
        ("sqlServer", "INFORMATION_SCHEMA.TABLES", "INFORMATION_SCHEMA.COLUMNS"),
        ("ck", "system.tables", "system.columns"),
        ("dm", "all_tab_comments", "ALL_TAB_COLS"),
        ("doris", "information_schema.TABLES", "INFORMATION_SCHEMA.COLUMNS"),
        ("starrocks", "information_schema.TABLES", "INFORMATION_SCHEMA.COLUMNS"),
        ("redshift", "pg_class", "pg_catalog.pg_attribute"),
        ("kingbase", "pg_class", "pg_catalog.pg_attribute"),
        ("es", "", ""),
    ],
)
def test_all_layer_nine_database_types_have_schema_branches(
    ds_type,
    table_token,
    field_token,
):
    config = pg_config()
    table_sql, _ = DatasourceConnectionUtil._get_table_sql(ds_type, config)
    field_sql, _, _ = DatasourceConnectionUtil._get_field_sql(
        ds_type,
        config,
        "users",
    )

    assert table_token in table_sql
    assert field_token in field_sql


def test_schema_services_parse_configuration_and_missing_source(
    session,
    monkeypatch,
):
    captured = {}

    def get_tables(ds_type, config):
        captured.update(config)
        return [{"tableName": "users", "tableComment": "Users"}]

    monkeypatch.setattr(DatasourceConnectionUtil, "get_tables", get_tables)

    assert DatasourceService.get_tables_by_config(
        "pg",
        json.dumps(pg_config()),
    )[0]["tableName"] == "users"
    assert captured == pg_config()
    assert not DatasourceService.sync_tables(session, 99999, [], False)


@pytest.mark.parametrize(
    "ds_type",
    ["mysql", "pg", "oracle", "sqlServer", "ck"],
)
def test_sqlalchemy_schema_public_interface_for_every_source_type(
    monkeypatch,
    ds_type,
):
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params):
            sql = str(statement).lower()
            is_field = any(token in sql for token in (
                "columns",
                "pg_attribute",
                "all_tab_columns",
            ))
            if is_field:
                return FakeResult([("id", "bigint", "Identifier")])
            return FakeResult([("users", "Users")])

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(
        datasource_util,
        "create_engine",
        lambda *args, **kwargs: FakeEngine(),
    )
    config = pg_config()

    assert DatasourceConnectionUtil.get_tables(ds_type, config) == [
        {"tableName": "users", "tableComment": "Users"}
    ]
    assert DatasourceConnectionUtil.get_fields(
        ds_type,
        config,
        "users",
    ) == [
        {
            "fieldName": "id",
            "fieldType": "bigint",
            "fieldComment": "Identifier",
            "fieldIndex": 0,
        }
    ]


@pytest.mark.parametrize(
    ("ds_type", "driver_name"),
    [
        ("dm", "dmPython"),
        ("doris", "pymysql"),
        ("starrocks", "pymysql"),
        ("redshift", "redshift_connector"),
        ("kingbase", "psycopg2"),
    ],
)
def test_native_schema_public_interface_for_every_source_type(
    monkeypatch,
    ds_type,
    driver_name,
):
    class FakeCursor:
        def __init__(self):
            self.rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, *args, **kwargs):
            normalized = sql.lower()
            is_field = any(token in normalized for token in (
                "columns",
                "pg_attribute",
                "all_tab_cols",
            ))
            self.rows = (
                [("id", "bigint", "Identifier")]
                if is_field
                else [("users", "Users")]
            )

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    fake_driver = SimpleNamespace(connect=lambda **kwargs: FakeConnection())
    monkeypatch.setattr(datasource_util, driver_name, fake_driver)
    config = pg_config()

    assert DatasourceConnectionUtil.get_tables(ds_type, config) == [
        {"tableName": "users", "tableComment": "Users"}
    ]
    assert DatasourceConnectionUtil.get_fields(
        ds_type,
        config,
        "users",
    ) == [
        {
            "fieldName": "id",
            "fieldType": "bigint",
            "fieldComment": "Identifier",
            "fieldIndex": 0,
        }
    ]
