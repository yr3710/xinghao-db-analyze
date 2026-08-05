"""数据源连接与配置工具（第 8 层仅保留 PostgreSQL 分支）。"""

import json
import logging
import urllib.parse
from typing import Any, Dict, Tuple

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class DatasourceConnectionUtil:
    """按 Aix-DB 源码方式构造并测试 PostgreSQL 连接。"""

    @staticmethod
    def build_connection_uri(ds_type: str, config: Dict[str, Any]) -> str:
        if ds_type != "pg":
            raise ValueError(f"第 8 层暂不支持数据源类型: {ds_type}")

        host = config.get("host", "")
        port = config.get("port", 5432)
        username = urllib.parse.quote(config.get("username", ""))
        password = urllib.parse.quote(config.get("password", ""))
        database = config.get("database", "")
        extra_jdbc = config.get("extraJdbc", "")

        uri = (
            f"postgresql+psycopg2://{username}:{password}"
            f"@{host}:{port}/{database}"
        )
        if extra_jdbc:
            uri = f"{uri}?{extra_jdbc}"
        return uri

    @staticmethod
    def test_connection(
        ds_type: str,
        config: Dict[str, Any],
    ) -> Tuple[bool, str]:
        try:
            timeout = config.get("timeout", 30)
            uri = DatasourceConnectionUtil.build_connection_uri(
                ds_type,
                config,
            )
            engine = create_engine(
                uri,
                pool_pre_ping=True,
                connect_args={"connect_timeout": timeout},
            )
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True, ""
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
