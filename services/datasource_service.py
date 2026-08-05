"""第 8 层数据源 CRUD 与授权服务。"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
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
    def _save_tables_and_fields(
        session: Session,
        datasource: Datasource,
        tables: List[Dict[str, Any]],
        is_select_all: bool = False,
    ) -> None:
        config = DatasourceConfigUtil.decrypt_config(
            datasource.configuration
        )
        keep_table_ids: List[int] = []

        try:
            all_db_tables = DatasourceConnectionUtil.get_tables(
                datasource.type,
                config,
            )
            total_count = len(all_db_tables)
        except Exception:
            total_count = len(tables)

        for table_info in tables:
            table_name = table_info.get("table_name") or table_info.get(
                "tableName"
            )
            table_comment = (
                table_info.get("table_comment")
                or table_info.get("tableComment")
                or ""
            )
            if not table_name:
                continue

            table = (
                session.query(DatasourceTable)
                .filter(
                    DatasourceTable.ds_id == datasource.id,
                    DatasourceTable.table_name == table_name,
                )
                .first()
            )
            if table is None:
                table = DatasourceTable(
                    ds_id=datasource.id,
                    checked=True,
                    table_name=table_name,
                    table_comment=table_comment,
                    custom_comment=table_comment,
                )
                session.add(table)
                session.flush()
                session.refresh(table)
            else:
                table.table_comment = table_comment
                table.custom_comment = table.custom_comment or table_comment
                table.checked = True

            keep_table_ids.append(table.id)

            try:
                fields = DatasourceConnectionUtil.get_fields(
                    datasource.type,
                    config,
                    table_name,
                )
            except Exception:
                fields = []

            keep_field_ids: List[int] = []
            for field_info in fields:
                field_name = field_info.get("fieldName")
                if not field_name:
                    continue
                field_comment = field_info.get("fieldComment") or ""
                field_type = field_info.get("fieldType") or ""
                field_index = field_info.get("fieldIndex") or 0

                field = (
                    session.query(DatasourceField)
                    .filter(
                        and_(
                            DatasourceField.table_id == table.id,
                            DatasourceField.field_name == field_name,
                        )
                    )
                    .first()
                )
                if field is None:
                    field = DatasourceField(
                        ds_id=datasource.id,
                        table_id=table.id,
                        checked=True,
                        field_name=field_name,
                        field_type=field_type,
                        field_comment=field_comment,
                        custom_comment=field_comment,
                        field_index=field_index,
                    )
                    session.add(field)
                    session.flush()
                    session.refresh(field)
                else:
                    field.field_comment = field_comment
                    field.field_type = field_type
                    field.field_index = field_index
                    if field.custom_comment is None:
                        field.custom_comment = field_comment

                keep_field_ids.append(field.id)

            if keep_field_ids:
                session.query(DatasourceField).filter(
                    and_(
                        DatasourceField.table_id == table.id,
                        DatasourceField.id.not_in(keep_field_ids),
                    )
                ).delete(synchronize_session=False)

        if keep_table_ids:
            session.query(DatasourceTable).filter(
                and_(
                    DatasourceTable.ds_id == datasource.id,
                    DatasourceTable.id.not_in(keep_table_ids),
                )
            ).delete(synchronize_session=False)
            session.query(DatasourceField).filter(
                and_(
                    DatasourceField.ds_id == datasource.id,
                    DatasourceField.table_id.not_in(keep_table_ids),
                )
            ).delete(synchronize_session=False)

        datasource.num = f"{len(keep_table_ids)}/{total_count}"
        session.add(datasource)

    @staticmethod
    def sync_tables(
        session: Session,
        ds_id: int,
        tables: List[Dict[str, Any]],
        is_select_all: bool = False,
    ) -> bool:
        datasource = session.get(Datasource, ds_id)
        if datasource is None:
            return False
        DatasourceService._save_tables_and_fields(
            session,
            datasource,
            tables,
            is_select_all,
        )
        session.commit()
        return True

    @staticmethod
    def get_tables_by_config(
        ds_type: str,
        configuration: Any,
    ) -> List[Dict[str, Any]]:
        config = DatasourceService._parse_configuration(configuration)
        return DatasourceConnectionUtil.get_tables(ds_type, config)

    @staticmethod
    def get_fields_by_config(
        ds_type: str,
        configuration: Any,
        table_name: str,
    ) -> List[Dict[str, Any]]:
        config = DatasourceService._parse_configuration(configuration)
        return DatasourceConnectionUtil.get_fields(
            ds_type,
            config,
            table_name,
        )

    @staticmethod
    def get_tables_by_ds_id(
        session: Session,
        ds_id: int,
    ) -> List[DatasourceTable]:
        return session.query(DatasourceTable).filter(
            DatasourceTable.ds_id == ds_id
        ).all()

    @staticmethod
    def get_fields_by_table_id(
        session: Session,
        table_id: int,
    ) -> List[DatasourceField]:
        return session.query(DatasourceField).filter(
            DatasourceField.table_id == table_id
        ).all()

    @staticmethod
    def save_table(session: Session, data: Dict[str, Any]) -> bool:
        table_id = data.get("id")
        if not table_id:
            return False
        table = session.get(DatasourceTable, table_id)
        if table is None:
            return False
        if "custom_comment" in data:
            table.custom_comment = data["custom_comment"]
        if "checked" in data:
            table.checked = data["checked"]
        session.commit()
        return True

    @staticmethod
    def save_field(session: Session, data: Dict[str, Any]) -> bool:
        field_id = data.get("id")
        if not field_id:
            return False
        field = session.get(DatasourceField, field_id)
        if field is None:
            return False
        if "custom_comment" in data:
            field.custom_comment = data["custom_comment"]
        if "checked" in data:
            field.checked = data["checked"]
        session.commit()
        return True

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
