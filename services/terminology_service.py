import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from langchain_core.messages import HumanMessage
from sqlalchemy import desc, or_, text, update

from common.exception import MyException
from common.llm_util import get_llm
from constants.code_enum import SysCodeEnum
from model import Datasource
from model.db_connection_pool import get_db_pool
from model.db_models import TTerminology
from model.schemas import PaginatedResponse
from model.serializers import model_to_dict
from services.embedding_service import get_default_embedding_model

logger = logging.getLogger(__name__)
pool = get_db_pool()

# 是否启用 embedding 功能
EMBEDDING_ENABLED = os.getenv("EMBEDDING_ENABLED", "true").lower() == "true"


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

        # 计算并保存 embedding（异步处理，不阻塞）
        if EMBEDDING_ENABLED:
            try:
                await save_terminology_embeddings([parent.id])
            except Exception as e:
                logger.warning(f"保存术语 embedding 失败: {e}", exc_info=True)
                # 不抛出异常，避免影响创建流程
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

        # 计算并保存 embedding（异步处理，不阻塞）
        if EMBEDDING_ENABLED:
            try:
                await save_terminology_embeddings([terminology_id])
            except Exception as e:
                logger.warning(f"保存术语 embedding 失败: {e}", exc_info=True)
                # 不抛出异常，避免影响更新流程
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


def _save_terminology_embeddings_sync(ids: List[int]):
    """
    同步版本：计算并保存术语的 embedding（在后台线程中执行）
    
    Args:
        ids: 术语ID列表（父节点ID），会自动处理子节点
    """
    if not EMBEDDING_ENABLED:
        return
    
    if not ids or len(ids) == 0:
        return
    
    try:
        with pool.get_session() as session:
            # 查询术语及其子节点（所有需要计算 embedding 的术语）
            # 使用 or_(id.in_(ids), pid.in_(ids)) 查询父节点和所有子节点
            terminology_list = session.query(TTerminology).filter(
                or_(TTerminology.id.in_(ids), TTerminology.pid.in_(ids))
            ).all()
            
            if not terminology_list:
                return
            
            # 收集所有术语的 word（用于批量生成 embedding）
            words_list = [term.word for term in terminology_list if term.word]
            
            if not words_list:
                return
            
            logger.info(f"开始计算 {len(words_list)} 个术语的 embedding（父节点和子节点）...")
            
            # 批量生成 embedding（当前层只使用用户配置的在线模型）
            # 术语 embedding 存储在 pgvector 中
            embeddings = []
            try:
                # 尝试获取在线模型配置（同步方式）
                model_config = None
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    model_config = loop.run_until_complete(get_default_embedding_model())
                    loop.close()
                except Exception as e:
                    logger.debug(f"获取在线模型配置失败: {e}")
                
                if model_config:
                    # 使用在线模型逐个生成（在线模型通常不支持批量）
                    from openai import OpenAI
                    
                    # 处理 Ollama 特殊格式
                    base_url = model_config["api_domain"]
                    if model_config["supplier"] == 3:  # Ollama
                        if not base_url.endswith("/v1"):
                            base_url = f"{base_url.rstrip('/')}/v1"
                    
                    client = OpenAI(
                        api_key=model_config["api_key"] or "empty",
                        base_url=base_url
                    )
                    
                    embeddings = []
                    for word in words_list:
                        try:
                            response = client.embeddings.create(model=model_config["base_model"], input=word)
                            if response.data:
                                embeddings.append(response.data[0].embedding)
                            else:
                                embeddings.append(None)
                        except Exception as e:
                            logger.warning(f"在线模型生成术语 '{word}' 的 embedding 失败: {e}，跳过")
                            embeddings.append(None)
                    
                    success_count = sum(1 for e in embeddings if e is not None)
                    logger.info(f"✅ 使用在线模型生成 {success_count}/{len(words_list)} 个术语 embedding")
                else:
                    # 当前层不实现离线模型回退
                    logger.error("❌ 未配置在线 embedding 模型，无法计算术语 embedding")
                    return
                        
            except Exception as e:
                logger.error(f"批量生成术语 embedding 失败: {e}", exc_info=True)
                return
            
            # 逐个更新到数据库（每个更新单独 commit，避免一个失败影响其他）
            success_count = 0
            for index in range(len(terminology_list)):
                if index < len(embeddings) and embeddings[index] is not None:
                    term = terminology_list[index]
                    try:
                        stmt = update(TTerminology).where(
                            TTerminology.id == term.id
                        ).values(embedding=embeddings[index])
                        session.execute(stmt)
                        session.commit()  # 每个更新单独 commit
                        success_count += 1
                        logger.debug(f"✅ 成功更新术语 {term.id} ({term.word}) 的 embedding")
                    except Exception as e:
                        error_msg = str(e)
                        # 检查是否是维度不匹配错误
                        if "expected" in error_msg and "dimensions" in error_msg:
                            logger.error(
                                f"❌ 术语 {term.id} ({term.word}) 的 embedding 维度不匹配: {e}。"
                            )
                        else:
                            logger.error(f"更新术语 {term.id} ({term.word}) 的 embedding 失败: {e}")
                        # 回滚当前事务，继续处理下一个
                        try:
                            session.rollback()
                        except:
                            pass
                        # 继续处理下一个，不中断
            
            logger.info(f"✅ 成功保存 {success_count}/{len(terminology_list)} 个术语的 embedding")
            
    except Exception as e:
        logger.error(f"保存术语 embedding 失败: {e}", exc_info=True)
        # 不抛出异常，避免影响主流程


async def save_terminology_embeddings(ids: List[int]):
    """
    异步包装：在后台线程中执行 embedding 计算和保存
    
    Args:
        ids: 术语ID列表（父节点ID），会自动处理子节点
    """
    if not EMBEDDING_ENABLED:
        return
    
    if not ids or len(ids) == 0:
        return
    
    # 在后台线程中执行，不阻塞主流程
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save_terminology_embeddings_sync, ids)

