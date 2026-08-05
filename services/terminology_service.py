import json
from datetime import datetime
from typing import List, Optional

from langchain_core.messages import HumanMessage
from sqlalchemy import desc, or_, text

from common.exception import MyException
from common.llm_util import get_llm
from constants.code_enum import SysCodeEnum
from model import Datasource
from model.db_connection_pool import get_db_pool
from model.db_models import TTerminology
from model.schemas import PaginatedResponse
from model.serializers import model_to_dict

pool = get_db_pool()


async def query_terminology_list(
    page: int,
    size: int,
    word: Optional[str] = None,
    dslist: Optional[List[int]] = None,
):
    with pool.get_session() as session:
        query = session.query(TTerminology)
        filters = [TTerminology.pid.is_(None)]

        if word:
            matched_ids_query = session.query(TTerminology.id).filter(
                TTerminology.word.ilike(f"%{word}%")
            )
            matched_ids = [row[0] for row in matched_ids_query.all()]
            if matched_ids:
                parent_ids_query = session.query(TTerminology.pid).filter(
                    TTerminology.id.in_(matched_ids),
                    TTerminology.pid.isnot(None),
                )
                parent_ids = [row[0] for row in parent_ids_query.all()]
                candidate_ids = set(matched_ids) | set(parent_ids)
                filters.append(TTerminology.id.in_(candidate_ids))
            else:
                return PaginatedResponse(
                    records=[],
                    current_page=page,
                    total_count=0,
                    total_pages=0,
                )

        if dslist:
            datasource_conditions = [TTerminology.specific_ds == False]
            datasource_values = ", ".join(
                [f"'{datasource_id}'" for datasource_id in dslist]
            )
            if datasource_values:
                datasource_conditions.append(
                    text(
                        f"""
                        specific_ds = true
                        AND datasource_ids IS NOT NULL
                        AND EXISTS (
                            SELECT 1
                            FROM json_array_elements_text(datasource_ids::json)
                            WHERE value IN ({datasource_values})
                        )
                        """
                    )
                )
            filters.append(or_(*datasource_conditions))

        query = query.filter(*filters)
        total_count = query.count()
        total_pages = (total_count + size - 1) // size
        records = (
            query.order_by(desc(TTerminology.create_time))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        result_list = []
        for record in records:
            item = model_to_dict(record)
            item.pop("embedding", None)
            children = session.query(TTerminology).filter(
                TTerminology.pid == record.id
            ).all()
            item["other_words"] = [child.word for child in children]
            item["datasource_names"] = []
            item["datasource_ids"] = []
            if record.specific_ds and record.datasource_ids:
                try:
                    datasource_ids = json.loads(record.datasource_ids)
                    item["datasource_ids"] = datasource_ids
                    if datasource_ids:
                        names = session.query(Datasource.name).filter(
                            Datasource.id.in_(datasource_ids)
                        ).all()
                        item["datasource_names"] = [row[0] for row in names]
                except Exception:
                    pass
            result_list.append(item)

        return PaginatedResponse(
            records=result_list,
            current_page=page,
            total_count=total_count,
            total_pages=total_pages,
        )


async def create_terminology(
    word: str,
    description: str,
    other_words: List[str],
    specific_ds: bool,
    datasource_ids: List[int],
    oid: int = 1,
):
    with pool.get_session() as session:
        all_words = [word] + other_words
        existing = session.query(TTerminology).filter(
            TTerminology.word.in_(all_words)
        ).first()
        if existing:
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                f"术语或同义词 '{existing.word}' 已存在",
            )

        parent = TTerminology(
            word=word,
            description=description,
            specific_ds=specific_ds,
            datasource_ids=(
                json.dumps(datasource_ids) if datasource_ids else "[]"
            ),
            oid=oid,
            enabled=True,
            create_time=datetime.now(),
            embedding=None,
        )
        session.add(parent)
        session.flush()

        for other_word in other_words:
            if not other_word.strip():
                continue
            session.add(
                TTerminology(
                    pid=parent.id,
                    word=other_word,
                    specific_ds=specific_ds,
                    datasource_ids=(
                        json.dumps(datasource_ids)
                        if datasource_ids
                        else "[]"
                    ),
                    oid=oid,
                    enabled=True,
                    create_time=datetime.now(),
                    embedding=None,
                )
            )
        session.commit()
        return True


async def update_terminology(
    terminology_id: int,
    word: str,
    description: str,
    other_words: List[str],
    specific_ds: bool,
    datasource_ids: List[int],
    oid: int = 1,
):
    with pool.get_session() as session:
        parent = session.query(TTerminology).filter(
            TTerminology.id == terminology_id
        ).first()
        if not parent:
            raise MyException(SysCodeEnum.PARAM_ERROR, "术语不存在")

        all_words = [word] + other_words
        existing = session.query(TTerminology).filter(
            TTerminology.word.in_(all_words),
            TTerminology.id != terminology_id,
            or_(
                TTerminology.pid != terminology_id,
                TTerminology.pid.is_(None),
            ),
        ).first()
        if existing:
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                f"术语或同义词 '{existing.word}' 已存在",
            )

        parent.word = word
        parent.description = description
        parent.specific_ds = specific_ds
        parent.datasource_ids = (
            json.dumps(datasource_ids) if datasource_ids else "[]"
        )

        session.query(TTerminology).filter(
            TTerminology.pid == terminology_id
        ).delete()
        for other_word in other_words:
            if not other_word.strip():
                continue
            session.add(
                TTerminology(
                    pid=parent.id,
                    word=other_word,
                    specific_ds=specific_ds,
                    datasource_ids=(
                        json.dumps(datasource_ids)
                        if datasource_ids
                        else "[]"
                    ),
                    oid=oid,
                    enabled=parent.enabled,
                    create_time=datetime.now(),
                    embedding=None,
                )
            )
        session.commit()
        return True


async def delete_terminology(ids: List[int]):
    with pool.get_session() as session:
        session.query(TTerminology).filter(
            or_(
                TTerminology.id.in_(ids),
                TTerminology.pid.in_(ids),
            )
        ).delete(synchronize_session=False)
        session.commit()
        return True


async def enable_terminology(
    terminology_id: int,
    enabled: bool,
):
    with pool.get_session() as session:
        session.query(TTerminology).filter(
            or_(
                TTerminology.id == terminology_id,
                TTerminology.pid == terminology_id,
            )
        ).update(
            {TTerminology.enabled: enabled},
            synchronize_session=False,
        )
        session.commit()
        return True


async def get_terminology_detail(terminology_id: int):
    with pool.get_session() as session:
        record = session.query(TTerminology).filter(
            TTerminology.id == terminology_id
        ).first()
        if not record:
            return None

        item = model_to_dict(record)
        item.pop("embedding", None)
        children = session.query(TTerminology).filter(
            TTerminology.pid == record.id
        ).all()
        item["other_words"] = [child.word for child in children]
        item["datasource_ids"] = []
        item["datasource_names"] = []
        if record.datasource_ids:
            try:
                datasource_ids = json.loads(record.datasource_ids)
                item["datasource_ids"] = datasource_ids
                if datasource_ids:
                    names = session.query(Datasource.name).filter(
                        Datasource.id.in_(datasource_ids)
                    ).all()
                    item["datasource_names"] = [row[0] for row in names]
            except Exception:
                pass
        return item


async def generate_synonyms_by_llm(word: str) -> List[str]:
    try:
        llm = get_llm()
        prompt = f"""
        请为术语 "{word}" 生成5个同义词，用于数据分析和商业智能场景。
        请直接返回JSON数组格式的字符串，例如 ["词1", "词2"]。
        不要包含Markdown标记或其他文本。
        """
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            result = json.loads(content)
            if isinstance(result, list):
                return [str(item) for item in result]
            return []
        except json.JSONDecodeError:
            return [
                item.strip()
                for item in content.split(",")
                if item.strip()
            ]
    except Exception as exc:
        if "No default AI model" in str(exc):
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                "未配置默认AI模型，请先在模型管理中配置",
            )
        raise MyException(
            SysCodeEnum.c_9999,
            f"AI生成失败: {str(exc)}",
        )
