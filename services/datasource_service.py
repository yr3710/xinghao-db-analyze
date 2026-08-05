"""第 8 层数据源 CRUD 与授权服务。"""

import json
import logging
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
from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel

logger = logging.getLogger(__name__)


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
        embedding_items: List[Dict[str, Any]] = []

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

            field_docs = [
                {
                    "fieldName": field.get("fieldName"),
                    "fieldComment": field.get("fieldComment") or "",
                }
                for field in fields
                if field.get("fieldName")
            ]
            embedding_items.append({"table": table, "fields": field_docs})

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
        # 批量计算并保存表的 embedding（表名 + 注释 + 字段名 + 字段注释）
        try:
            DatasourceService._compute_and_save_table_embeddings_batch(
                session,
                embedding_items,
            )
        except Exception as exc:
            logger.warning("批量计算表 embedding 失败: %s", exc, exc_info=True)

    @staticmethod
    def _get_embedding_client():
        """
        获取 embedding 客户端和模型名称
        当前层表结构 embedding 只使用在线模型，未配置时不回退本地模型
        """
        try:
            db_pool = get_db_pool()
            with db_pool.get_session() as session:
                # model_type: 2 -> Embedding
                model = session.query(TAiModel).filter(TAiModel.model_type == 2, TAiModel.default_model == True).first()

                if not model:
                    # 尝试查找任何 embedding 模型
                    model = session.query(TAiModel).filter(TAiModel.model_type == 2).first()

                if not model:
                    logger.info("未配置在线嵌入模型（model_type=2），跳过表 embedding")
                    return None, None

                # 处理 base_url，确保包含协议前缀
                base_url = (model.api_domain or "").strip()
                if not base_url:
                    logger.warning("表结构 embedding 在线模型的 API Domain 为空")
                    return None, None

                if not base_url.startswith(("http://", "https://")):
                    # 本地地址默认 http，其它默认 https
                    if base_url.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
                        base_url = f"http://{base_url}"
                    else:
                        base_url = f"https://{base_url}"

                # 延迟导入，避免在模块加载时触发 OpenTelemetry 初始化问题
                from langfuse.openai import OpenAI
                embedding_client = OpenAI(
                    api_key=model.api_key or "empty",
                    base_url=base_url
                )
                logger.info(f"✅ 使用在线模型计算表 embedding: {model.base_model} ({base_url})")
                return embedding_client, model.base_model
        except Exception as e:
            logger.warning(f"获取在线 embedding 客户端失败: {e}")
            return None, None

    @staticmethod
    def _build_table_document(table: DatasourceTable, fields: List[Dict[str, Any]]) -> str:
        """
        构建用于检索的文档文本（表名 + 注释 + 字段名 + 字段注释）。

        Args:
            table: 表对象
            fields: 字段列表

        Returns:
            文档文本
        """
        parts = [table.table_name]

        # 添加表注释（优先使用 custom_comment，否则使用 table_comment）
        table_comment = table.custom_comment or table.table_comment or ""
        if table_comment:
            parts.append(table_comment)

        # 添加字段名和字段注释
        for field in fields:
            field_name = field.get("fieldName") or field.get("field_name")
            if field_name:
                parts.append(field_name)
                field_comment = field.get("fieldComment") or field.get("field_comment") or ""
                if field_comment:
                    parts.append(field_comment)

        return " ".join(parts)

    @staticmethod
    def _compute_and_save_table_embedding(session: Session, table: DatasourceTable, fields: List[Dict[str, Any]]):
        """
        计算并保存表的 embedding。

        Args:
            session: 数据库会话
            table: 表对象
            fields: 字段列表
        """
        # 检查是否有 embedding 字段
        if not hasattr(table, 'embedding'):
            logger.debug(f"表 {table.table_name} 没有 embedding 字段，跳过计算")
            return

        # 构建文档文本
        document = DatasourceService._build_table_document(table, fields)

        if not document or not document.strip():
            logger.warning(f"表 {table.table_name} 的文档文本为空，跳过 embedding 计算")
            return

        # 获取在线 embedding 客户端
        embedding_client, model_name = DatasourceService._get_embedding_client()

        try:
            if embedding_client and model_name:
                # 使用在线模型
                logger.info(f"计算表 {table.table_name} 的 embedding（在线模型: {model_name}）...")
                response = embedding_client.embeddings.create(model=model_name, input=document)
                embedding_vec = response.data[0].embedding
            else:
                # 当前层不使用离线模型
                logger.warning(f"未配置在线模型，跳过表 {table.table_name} 的 embedding 计算")
                return
            # 将 embedding 转换为 JSON 字符串并保存
            embedding_json = json.dumps(embedding_vec)
            table.embedding = embedding_json

            logger.info(f"✅ 表 {table.table_name} 的 embedding 计算并保存成功（维度: {len(embedding_vec)}）")

        except Exception as e:
            logger.error(f"计算表 {table.table_name} 的 embedding 失败: {e}", exc_info=True)
            # 不抛出异常，避免影响表同步流程

    @staticmethod
    def _compute_and_save_table_embeddings_batch(session: Session, items: List[Dict[str, Any]]):
        """
        批量计算并保存多个表的 embedding，减少 API 调用次数。

        Args:
            session: 数据库会话
            items: 列表，每项包含 {"table": DatasourceTable, "fields": List[Dict]}
        """
        if not items:
            return

        # 统一检查是否支持 embedding 字段
        tables_for_embedding: List[DatasourceTable] = []
        docs: List[str] = []

        for item in items:
            table: DatasourceTable = item.get("table")
            fields: List[Dict[str, Any]] = item.get("fields") or []

            if not table or not hasattr(table, "embedding"):
                continue

            doc = DatasourceService._build_table_document(table, fields)
            if not doc or not doc.strip():
                continue

            tables_for_embedding.append(table)
            docs.append(doc)

        if not docs:
            return

        # 获取在线 embedding 客户端
        embedding_client, model_name = DatasourceService._get_embedding_client()

        try:
            if embedding_client and model_name:
                # 使用在线模型批量计算
                logger.info(f"批量计算 {len(docs)} 个表的 embedding（在线模型: {model_name}）...")
                response = embedding_client.embeddings.create(model=model_name, input=docs)
                data = response.data or []

                if len(data) != len(tables_for_embedding):
                    logger.warning(
                        f"批量 embedding 返回数量与请求数量不一致: 请求 {len(tables_for_embedding)}, 返回 {len(data)}"
                    )

                for idx, table in enumerate(tables_for_embedding):
                    if idx >= len(data):
                        break
                    embedding_vec = data[idx].embedding
                    embedding_json = json.dumps(embedding_vec)
                    table.embedding = embedding_json

                logger.info(f"✅ 批量表 embedding 计算并保存成功（维度: {len(data[0].embedding) if data else 'unknown'}）")
            else:
                # 当前层不使用离线模型
                logger.warning("未配置在线模型，跳过批量表 embedding 计算")
                return

        except Exception as e:
            logger.error(f"批量计算表 embedding 失败: {e}", exc_info=True)

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
        # 如果表注释或字段信息发生变化，重新计算 embedding
        fields = session.query(DatasourceField).filter(
            DatasourceField.table_id == table_id
        ).all()
        fields_data = [
            {
                "fieldName": field.field_name,
                "fieldComment": (
                    field.custom_comment or field.field_comment or ""
                ),
            }
            for field in fields
        ]
        try:
            DatasourceService._compute_and_save_table_embedding(
                session,
                table,
                fields_data,
            )
        except Exception as exc:
            logger.warning(
                "更新表 %s 的 embedding 失败: %s",
                table.table_name,
                exc,
                exc_info=True,
            )
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
        # 如果字段信息发生变化，重新计算所属表的 embedding
        table = session.get(DatasourceTable, field.table_id)
        if table:
            fields = session.query(DatasourceField).filter(
                DatasourceField.table_id == field.table_id
            ).all()
            fields_data = [
                {
                    "fieldName": item.field_name,
                    "fieldComment": (
                        item.custom_comment or item.field_comment or ""
                    ),
                }
                for item in fields
            ]
            try:
                DatasourceService._compute_and_save_table_embedding(
                    session,
                    table,
                    fields_data,
                )
            except Exception as exc:
                logger.warning(
                    "更新表 %s 的 embedding 失败: %s",
                    table.table_name,
                    exc,
                    exc_info=True,
                )
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
