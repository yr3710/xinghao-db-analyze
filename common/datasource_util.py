"""数据源工具类。"""

import json
import logging
import urllib.parse
from base64 import b64encode
from enum import Enum
from typing import Any, Dict, Tuple

import psycopg2
import pymysql
from elasticsearch import Elasticsearch
from sqlalchemy import create_engine, text

# 达梦数据库驱动（可选依赖）
try:
    import dmPython
except ImportError:
    dmPython = None

# AWS Redshift 驱动
try:
    import redshift_connector
except ImportError:
    redshift_connector = None

logger = logging.getLogger(__name__)


class ConnectType(Enum):
    """数据库连接类型。"""

    sqlalchemy = "sqlalchemy"
    py_driver = "py_driver"


class DB(Enum):
    """数据库类型枚举。"""

    mysql = ("mysql", "MySQL", "`", "`", ConnectType.sqlalchemy)
    pg = ("pg", "PostgreSQL", '"', '"', ConnectType.sqlalchemy)
    oracle = ("oracle", "Oracle", '"', '"', ConnectType.sqlalchemy)
    sqlServer = ("sqlServer", "SQL Server", "[", "]", ConnectType.sqlalchemy)
    ck = ("ck", "ClickHouse", '"', '"', ConnectType.sqlalchemy)
    dm = ("dm", "达梦", '"', '"', ConnectType.py_driver)
    doris = ("doris", "Apache Doris", "`", "`", ConnectType.py_driver)
    redshift = ("redshift", "AWS Redshift", '"', '"', ConnectType.py_driver)
    es = ("es", "Elasticsearch", '"', '"', ConnectType.py_driver)
    kingbase = ("kingbase", "Kingbase", '"', '"', ConnectType.py_driver)
    starrocks = ("starrocks", "StarRocks", "`", "`", ConnectType.py_driver)

    def __init__(
        self,
        type_code: str,
        db_name: str,
        prefix: str,
        suffix: str,
        connect_type: ConnectType,
    ):
        self.type_code = type_code
        self.db_name = db_name
        self.prefix = prefix
        self.suffix = suffix
        self.connect_type = connect_type

    @classmethod
    def get_db(cls, ds_type: str, default_if_none: bool = False):
        """根据类型代码获取数据库枚举。"""
        for db in cls:
            if db.type_code.lower() == ds_type.lower():
                return db
        if default_if_none:
            return DB.pg
        raise ValueError(f"不支持的数据库类型: {ds_type}")


class DatasourceConnectionUtil:
    """数据源连接工具类。"""

    NEED_SCHEMA_TYPES = [
        "sqlServer",
        "pg",
        "oracle",
        "dm",
        "redshift",
        "kingbase",
    ]

    @staticmethod
    def build_connection_uri(ds_type: str, config: Dict[str, Any]) -> str:
        host = config.get("host", "")
        port = config.get("port", 3306)
        username = config.get("username", "")
        password = config.get("password", "")
        database = config.get("database", "")
        extra_jdbc = config.get("extraJdbc", "")
        mode = config.get("mode", "service_name")

        username_encoded = urllib.parse.quote(username)
        password_encoded = urllib.parse.quote(password)

        if ds_type == "mysql":
            if extra_jdbc:
                return (
                    f"mysql+pymysql://{username_encoded}:{password_encoded}"
                    f"@{host}:{port}/{database}?{extra_jdbc}"
                )
            return (
                f"mysql+pymysql://{username_encoded}:{password_encoded}"
                f"@{host}:{port}/{database}"
            )

        elif ds_type == "pg":
            if extra_jdbc:
                return (
                    f"postgresql+psycopg2://{username_encoded}:{password_encoded}"
                    f"@{host}:{port}/{database}?{extra_jdbc}"
                )
            return (
                f"postgresql+psycopg2://{username_encoded}:{password_encoded}"
                f"@{host}:{port}/{database}"
            )

        elif ds_type == "oracle":
            if mode == "service_name":
                if extra_jdbc:
                    return (
                        f"oracle+oracledb://{username_encoded}:{password_encoded}"
                        f"@{host}:{port}?service_name={database}&{extra_jdbc}"
                    )
                return (
                    f"oracle+oracledb://{username_encoded}:{password_encoded}"
                    f"@{host}:{port}?service_name={database}"
                )
            if extra_jdbc:
                return (
                    f"oracle+oracledb://{username_encoded}:{password_encoded}"
                    f"@{host}:{port}/{database}?{extra_jdbc}"
                )
            return (
                f"oracle+oracledb://{username_encoded}:{password_encoded}"
                f"@{host}:{port}/{database}"
            )

        elif ds_type == "sqlServer":
            if extra_jdbc:
                return (
                    f"mssql+pymssql://{username_encoded}:{password_encoded}"
                    f"@{host}:{port}/{database}?{extra_jdbc}"
                )
            return (
                f"mssql+pymssql://{username_encoded}:{password_encoded}"
                f"@{host}:{port}/{database}"
            )

        elif ds_type == "ck":
            if extra_jdbc:
                return (
                    f"clickhouse+http://{username_encoded}:{password_encoded}"
                    f"@{host}:{port}/{database}?{extra_jdbc}"
                )
            return (
                f"clickhouse+http://{username_encoded}:{password_encoded}"
                f"@{host}:{port}/{database}"
            )

        raise ValueError(
            f"不支持使用 SQLAlchemy 连接的数据源类型: {ds_type}"
        )

    @staticmethod
    def _get_extra_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """解析额外的 JDBC 参数。"""
        config_dict = {}
        extra_jdbc = config.get("extraJdbc", "")
        if extra_jdbc:
            config_arr = extra_jdbc.split("&")
            for item in config_arr:
                kv = item.split("=")
                if len(kv) == 2 and kv[0] and kv[1]:
                    config_dict[kv[0]] = kv[1]
        return config_dict

    @staticmethod
    def _get_es_auth(config: Dict[str, Any]) -> Dict[str, str]:
        """获取 Elasticsearch 认证头。"""
        username = config.get("username", "")
        password = config.get("password", "")
        credentials = f"{username}:{password}"
        encoded_credentials = b64encode(credentials.encode()).decode()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
        }

    @staticmethod
    def _get_es_connect(config: Dict[str, Any]) -> Elasticsearch:
        """获取 Elasticsearch 连接。"""
        host = config.get("host", "")
        username = config.get("username", "")
        password = config.get("password", "")

        return Elasticsearch(
            [host],
            basic_auth=(username, password),
            verify_certs=False,
            compatibility_mode=True,
            headers=DatasourceConnectionUtil._get_es_auth(config),
        )

    @staticmethod
    def test_connection(
        ds_type: str,
        config: Dict[str, Any],
    ) -> Tuple[bool, str]:
        try:
            db = DB.get_db(ds_type)
            timeout = config.get("timeout", 30)
            extra_config = DatasourceConnectionUtil._get_extra_config(config)

            if db.connect_type == ConnectType.sqlalchemy:
                uri = DatasourceConnectionUtil.build_connection_uri(
                    ds_type,
                    config,
                )
                if ds_type == "oracle":
                    engine = create_engine(uri, pool_pre_ping=True)
                elif ds_type == "sqlServer":
                    engine = create_engine(
                        uri,
                        pool_pre_ping=True,
                        connect_args={
                            "timeout": timeout,
                            "login_timeout": timeout,
                            "encryption": "off",
                        },
                    )
                else:
                    engine = create_engine(
                        uri,
                        pool_pre_ping=True,
                        connect_args={"connect_timeout": timeout},
                    )
                with engine.connect() as connection:
                    test_sql = (
                        "SELECT 1 FROM DUAL"
                        if ds_type == "oracle"
                        else "SELECT 1"
                    )
                    connection.execute(text(test_sql))
                return True, ""

            host = config.get("host", "")
            port = config.get("port", 3306)
            username = config.get("username", "")
            password = config.get("password", "")
            database = config.get("database", "")

            if ds_type == "dm":
                if dmPython is None:
                    return False, "未安装达梦数据库驱动 dmPython"
                with dmPython.connect(
                    user=username,
                    password=password,
                    server=host,
                    port=port,
                    **extra_config,
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1", timeout=timeout)
                        cursor.fetchall()
                return True, ""

            elif ds_type in ("doris", "starrocks"):
                connect_timeout = max(timeout, 60)
                with pymysql.connect(
                    user=username,
                    passwd=password,
                    host=host,
                    port=port,
                    db=database,
                    connect_timeout=connect_timeout,
                    read_timeout=timeout,
                    write_timeout=timeout,
                    charset="utf8mb4",
                    autocommit=True,
                    **extra_config,
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                return True, ""

            elif ds_type == "redshift":
                if redshift_connector is None:
                    return False, "未安装 redshift_connector 驱动"
                with redshift_connector.connect(
                    host=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password,
                    timeout=timeout,
                    **extra_config,
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                return True, ""

            elif ds_type == "kingbase":
                with psycopg2.connect(
                    host=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password,
                    connect_timeout=timeout,
                    **extra_config,
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                return True, ""

            elif ds_type == "es":
                es_client = DatasourceConnectionUtil._get_es_connect(config)
                if es_client.ping():
                    return True, ""
                return False, "Elasticsearch 连接失败"

            return False, f"不支持的数据源类型: {ds_type}"
        except Exception as exc:
            logger.error("连接测试失败: %s", exc)
            return False, str(exc)


class DatasourceConfigUtil:
    """Aix-DB 源码中的 AES-ECB 配置加解密实现。"""

    KEY = b"AixDB12345678901"

    @staticmethod
    def encrypt_config(config: Dict[str, Any]) -> str:
        try:
            import base64

            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad

            config_str = json.dumps(config)
            cipher = AES.new(DatasourceConfigUtil.KEY, AES.MODE_ECB)
            padded_data = pad(
                config_str.encode("utf-8"),
                AES.block_size,
            )
            encrypted = cipher.encrypt(padded_data)
            return base64.b64encode(encrypted).decode("utf-8")
        except ImportError:
            import base64

            logger.warning(
                "pycryptodome未安装，使用base64编码（不安全）"
            )
            config_str = json.dumps(config)
            return base64.b64encode(
                config_str.encode("utf-8")
            ).decode("utf-8")

    @staticmethod
    def decrypt_config(encrypted_config: str) -> Dict[str, Any]:
        try:
            import base64

            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad

            encrypted_data = base64.b64decode(encrypted_config)
            cipher = AES.new(DatasourceConfigUtil.KEY, AES.MODE_ECB)
            decrypted = cipher.decrypt(encrypted_data)
            unpadded = unpad(decrypted, AES.block_size)
            return json.loads(unpadded.decode("utf-8"))
        except ImportError:
            import base64

            logger.warning(
                "pycryptodome未安装，使用base64解码"
            )
            config_str = base64.b64decode(
                encrypted_config
            ).decode("utf-8")
            return json.loads(config_str)
