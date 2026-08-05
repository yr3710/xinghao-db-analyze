import os

import pytest
from sqlalchemy.engine import make_url

from common.datasource_util import DatasourceConnectionUtil
from config.load_env import load_env


@pytest.mark.skipif(
    os.getenv("RUN_DATASOURCE_INTEGRATION") != "1",
    reason="set RUN_DATASOURCE_INTEGRATION=1 for real PostgreSQL tests",
)
def test_real_postgresql_accepts_correct_and_rejects_wrong_password():
    load_env()
    url = make_url(os.environ["SQLALCHEMY_DATABASE_URI"])
    config = {
        "host": url.host,
        "port": url.port or 5432,
        "username": url.username,
        "password": url.password,
        "database": url.database,
        "dbSchema": "public",
        "extraJdbc": "",
        "timeout": 5,
    }

    connected, _ = DatasourceConnectionUtil.test_connection("pg", config)
    wrong_config = dict(
        config,
        password="definitely-wrong-layer8-password",
    )
    wrong_connected, _ = (
        DatasourceConnectionUtil.test_connection("pg", wrong_config)
    )

    assert connected
    assert not wrong_connected
