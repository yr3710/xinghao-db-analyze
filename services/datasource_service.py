"""第 8 层数据源 CRUD 与授权服务。"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.datasource_util import (
    DatasourceConfigUtil,
    DatasourceConnectionUtil,
)
from common.permission_util import is_admin
from model.datasource_models import (
    Datasource,
    DatasourceAuth,
    DatasourceField,
    DatasourceTable,
)


class DatasourceService:
    """数据源管理的事务内服务。"""

    @staticmethod
    def _parse_configuration(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("数据源配置不能为空")
        try:
            result = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("数据源配置必须是 JSON 对象") from exc
        if not isinstance(result, dict):
            raise ValueError("数据源配置必须是 JSON 对象")
        return result

    @staticmethod
    def get_datasource_list(
        session: Session,
        user_id: int,
    ) -> List[Datasource]:
        query = session.query(Datasource)
        if not is_admin(user_id):
            authorized_ids = (
                select(DatasourceAuth.datasource_id)
                .where(
                    DatasourceAuth.user_id == user_id,
                    DatasourceAuth.enable.is_(True),
                )
                .distinct()
            )
            query = query.filter(Datasource.id.in_(authorized_ids))
        return query.order_by(Datasource.create_time.desc()).all()

    @staticmethod
    def get_datasource_by_id(
        session: Session,
        ds_id: int,
    ) -> Optional[Datasource]:
        return session.get(Datasource, ds_id)

    @staticmethod
    def create_datasource(
        session: Session,
        data: Dict[str, Any],
        user_id: int,
    ) -> Datasource:
        config = DatasourceService._parse_configuration(
            data.get("configuration")
        )

        datasource = Datasource(
            name=data.get("name"),
            description=data.get("description", ""),
            type=data.get("type"),
            type_name=data.get("type_name", ""),
            configuration=DatasourceConfigUtil.encrypt_config(config),
            create_time=datetime.now(),
            create_by=user_id,
            status="Success",
            num="0/0",
        )
        session.add(datasource)
        session.flush()
        return datasource

    @staticmethod
    def update_datasource(
        session: Session,
        ds_id: int,
        data: Dict[str, Any],
    ) -> Optional[Datasource]:
        datasource = session.get(Datasource, ds_id)
        if datasource is None:
            return None

        if data.get("name") is not None:
            datasource.name = data["name"]

        if data.get("description") is not None:
            datasource.description = data["description"]

        if data.get("type") is not None:
            datasource.type = data["type"]
        if data.get("type_name") is not None:
            datasource.type_name = data["type_name"]

        if data.get("configuration") is not None:
            new_config = DatasourceService._parse_configuration(
                data["configuration"]
            )
            datasource.configuration = (
                DatasourceConfigUtil.encrypt_config(new_config)
            )

        session.flush()
        return datasource

    @staticmethod
    def delete_datasource(session: Session, ds_id: int) -> bool:
        datasource = session.get(Datasource, ds_id)
        if datasource is None:
            return False

        session.query(DatasourceField).filter(
            DatasourceField.ds_id == ds_id
        ).delete(synchronize_session=False)
        session.query(DatasourceTable).filter(
            DatasourceTable.ds_id == ds_id
        ).delete(synchronize_session=False)
        session.delete(datasource)
        session.flush()
        return True

    @staticmethod
    def check_connection(
        datasource: Datasource,
    ) -> tuple[bool, str]:
        config = DatasourceConfigUtil.decrypt_config(
            datasource.configuration
        )
        return DatasourceConnectionUtil.test_connection(
            datasource.type,
            config,
        )

    @staticmethod
    def check_connection_by_config(
        ds_type: str,
        configuration: Any,
    ) -> tuple[bool, str]:
        config = DatasourceService._parse_configuration(configuration)
        return DatasourceConnectionUtil.test_connection(ds_type, config)

    @staticmethod
    def get_authorized_users(
        session: Session,
        datasource_id: int,
    ) -> List[int]:
        rows = (
            session.query(DatasourceAuth.user_id)
            .filter(
                DatasourceAuth.datasource_id == datasource_id,
                DatasourceAuth.enable.is_(True),
            )
            .order_by(DatasourceAuth.user_id.asc())
            .all()
        )
        return [row[0] for row in rows]

    @staticmethod
    def authorize_datasource(
        session: Session,
        datasource_id: int,
        user_ids: List[int],
    ) -> bool:
        if session.get(Datasource, datasource_id) is None:
            return False

        session.query(DatasourceAuth).filter(
            DatasourceAuth.datasource_id == datasource_id
        ).delete(synchronize_session=False)
        for user_id in user_ids:
            session.add(
                DatasourceAuth(
                    datasource_id=datasource_id,
                    user_id=user_id,
                    enable=True,
                    create_time=datetime.now(),
                )
            )
        session.flush()
        return True
