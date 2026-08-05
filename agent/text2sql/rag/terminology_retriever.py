"""
术语检索器
基于关键词匹配和 embedding 向量检索术语，格式化为模板所需的 XML 格式
支持混合检索：关键词匹配 + 向量相似度搜索
"""

import json
import logging
import os
from typing import List, Optional, Dict, Any
from sqlalchemy import or_, and_, text
from sqlalchemy.orm import Session

from model.db_connection_pool import get_db_pool
from model.db_models import TTerminology
from model.datasource_models import Datasource
from services.embedding_service import generate_embedding

logger = logging.getLogger(__name__)
pool = get_db_pool()

# 配置参数
EMBEDDING_TERMINOLOGY_SIMILARITY = float(os.getenv("EMBEDDING_TERMINOLOGY_SIMILARITY", "0.5"))  # 相似度阈值，默认 0.5
EMBEDDING_TERMINOLOGY_TOP_COUNT = int(os.getenv("EMBEDDING_TERMINOLOGY_TOP_COUNT", "10"))  # 向量检索返回的最大数量
USE_EMBEDDING = os.getenv("USE_TERMINOLOGY_EMBEDDING", "true").lower() == "true"  # 是否启用 embedding 检索


def retrieve_terminologies(
    question: str,
    datasource_id: Optional[int] = None,
    oid: int = 1,
    top_k: int = 10,
    use_embedding: bool = True,
) -> str:
    """
    检索术语并格式化为模板所需的 XML 格式
    
    Args:
        question: 用户问题
        datasource_id: 数据源ID（可选）
        oid: 组织ID（默认：1）
        top_k: 返回的最大术语数量（默认：10）
        use_embedding: 是否使用 embedding 向量检索（默认：True）
    
    Returns:
        格式化的术语 XML 字符串，如果没有找到则返回空字符串
    """
    if not question or not question.strip():
        return ""
    
    try:
        with pool.get_session() as session:
            # 查询匹配的术语（混合检索：关键词匹配 + embedding 向量检索）
            # 注意：_select_terminology_by_word 是异步函数，需要在异步环境中调用
            # 在线程池中运行时，需要创建新的事件循环
            import asyncio
            
            # 尝试获取当前线程的事件循环
            loop = None
            should_close_loop = False
            
            try:
                loop = asyncio.get_event_loop()
                # 检查事件循环是否已关闭
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except (RuntimeError, AttributeError):
                # 没有事件循环或事件循环已关闭，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                should_close_loop = True
            
            try:
                results = loop.run_until_complete(_select_terminology_by_word(
                    session=session,
                    word=question,
                    oid=oid,
                    datasource_id=datasource_id,
                    top_k=top_k,
                    use_embedding=use_embedding and USE_EMBEDDING,
                ))
            finally:
                # 如果是我们创建的事件循环，确保关闭它
                if should_close_loop and loop and not loop.is_closed():
                    try:
                        # 取消所有待处理的任务
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            if not task.done():
                                task.cancel()
                        
                        # 等待所有任务取消完成，捕获所有异常
                        if pending:
                            try:
                                # 给任务一些时间来完成清理
                                loop.run_until_complete(
                                    asyncio.wait_for(
                                        asyncio.gather(*pending, return_exceptions=True),
                                        timeout=2.0
                                    )
                                )
                            except (asyncio.TimeoutError, Exception):
                                # 超时或异常时，继续关闭循环
                                pass
                        
                        # 再次检查并处理剩余任务
                        remaining = [t for t in asyncio.all_tasks(loop) if not t.done()]
                        if remaining:
                            # 强制取消剩余任务
                            for task in remaining:
                                if not task.done():
                                    task.cancel()
                            # 快速等待，不阻塞太久
                            try:
                                loop.run_until_complete(
                                    asyncio.wait_for(
                                        asyncio.gather(*remaining, return_exceptions=True),
                                        timeout=0.5
                                    )
                                )
                            except (asyncio.TimeoutError, Exception):
                                pass
                    except Exception as e:
                        logger.debug(f"关闭事件循环时出现异常（可忽略）: {e}")
                    finally:
                        try:
                            # 确保事件循环被关闭
                            if not loop.is_closed():
                                loop.close()
                        except Exception as e:
                            logger.debug(f"关闭事件循环时出现异常（可忽略）: {e}")
            
            if not results or len(results) == 0:
                return ""
            
            # 格式化为 XML
            xml_str = _format_terminologies_to_xml(results)
            
            # Text2SQL Prompt 在后续层接入；当前层直接返回原项目 XML
            return xml_str
            
    except Exception as e:
        logger.error(f"检索术语失败: {e}", exc_info=True)
        return ""


async def _select_terminology_by_word(
    session: Session,
    word: str,
    oid: int,
    datasource_id: Optional[int] = None,
    top_k: int = 10,
    use_embedding: bool = True,
) -> List[Dict[str, Any]]:
    """
    通过关键词匹配和 embedding 向量检索术语（混合检索）
    
    Args:
        session: 数据库会话
        word: 搜索关键词
        oid: 组织ID
        datasource_id: 数据源ID（可选）
        top_k: 返回的最大数量
        use_embedding: 是否使用 embedding 向量检索
    
    Returns:
        术语列表，格式为 [{"words": [...], "description": "..."}, ...]
    """
    terminology_ids = set()
    
    # 1. 关键词匹配
    stmt = session.query(TTerminology).filter(
        and_(
            text(":sentence ILIKE '%' || word || '%'"),
            TTerminology.oid == oid,
            TTerminology.enabled == True,
        )
    )
    
    if datasource_id is not None:
        # 数据源筛选：通用术语或指定数据源的术语
        stmt = stmt.filter(
            or_(
                or_(TTerminology.specific_ds == False, TTerminology.specific_ds.is_(None)),
                and_(
                    TTerminology.specific_ds == True,
                    TTerminology.datasource_ids.isnot(None),
                    text(f"datasource_ids::jsonb @> jsonb_build_array({datasource_id})")
                )
            )
        )
    else:
        stmt = stmt.filter(
            or_(TTerminology.specific_ds == False, TTerminology.specific_ds.is_(None))
        )
    
    # 执行查询
    keyword_results = stmt.params(sentence=word).limit(top_k * 2).all()  # 多查一些，因为要去重
    
    # 收集关键词匹配的术语ID（包含父节点和子节点）
    for term in keyword_results:
        if term.pid is not None:
            terminology_ids.add(term.pid)
        else:
            terminology_ids.add(term.id)
    
    # 2. Embedding 向量检索（如果启用）
    # 当前层只使用用户配置的在线 embedding 模型
    if use_embedding:
        try:
            # 生成查询的在线 embedding；失败时仅保留关键词结果
            embedding = await generate_embedding(word)
            
            if embedding:
                # 使用 pgvector 的 <=> 操作符计算余弦距离
                # 相似度 = 1 - 余弦距离
                # 将 embedding 列表转换为字符串格式（PostgreSQL vector 格式）
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                
                # 构建 SQL 查询（根据是否有数据源筛选使用不同的 SQL）
                if datasource_id is not None:
                    embedding_sql = text(f"""
                        SELECT id, pid, word, similarity
                        FROM (
                            SELECT id, pid, word, oid, specific_ds, datasource_ids, enabled,
                                   (1 - (embedding <=> CAST(:embedding_array AS vector))) AS similarity
                            FROM t_terminology
                        ) TEMP
                        WHERE similarity > {EMBEDDING_TERMINOLOGY_SIMILARITY} 
                          AND oid = :oid 
                          AND enabled = true
                          AND (
                              (specific_ds = false OR specific_ds IS NULL)
                              OR
                              (specific_ds = true AND datasource_ids IS NOT NULL 
                               AND datasource_ids::jsonb @> jsonb_build_array(:datasource))
                          )
                        ORDER BY similarity DESC
                        LIMIT {EMBEDDING_TERMINOLOGY_TOP_COUNT}
                    """)
                    params = {
                        "embedding_array": embedding_str,
                        "oid": oid,
                        "datasource": datasource_id,
                    }
                else:
                    embedding_sql = text(f"""
                        SELECT id, pid, word, similarity
                        FROM (
                            SELECT id, pid, word, oid, specific_ds, datasource_ids, enabled,
                                   (1 - (embedding <=> CAST(:embedding_array AS vector))) AS similarity
                            FROM t_terminology
                        ) TEMP
                        WHERE similarity > {EMBEDDING_TERMINOLOGY_SIMILARITY} 
                          AND oid = :oid 
                          AND enabled = true
                          AND (specific_ds = false OR specific_ds IS NULL)
                        ORDER BY similarity DESC
                        LIMIT {EMBEDDING_TERMINOLOGY_TOP_COUNT}
                    """)
                    params = {
                        "embedding_array": embedding_str,
                        "oid": oid,
                    }
                
                embedding_results = session.execute(embedding_sql, params).fetchall()
                
                # 收集向量检索的术语ID（包含父节点和子节点）
                for row in embedding_results:
                    if row.pid is not None:
                        terminology_ids.add(row.pid)
                    else:
                        terminology_ids.add(row.id)
                        
        except Exception as e:
            logger.warning(f"Embedding 检索失败，仅使用关键词匹配: {e}")
    
    if len(terminology_ids) == 0:
        return []
    
    # 查询完整的术语信息（包含父节点和子节点）
    all_terms = session.query(TTerminology).filter(
        or_(TTerminology.id.in_(list(terminology_ids)), TTerminology.pid.in_(list(terminology_ids)))
    ).all()
    
    # 组织为字典格式
    term_dict = {}
    for term in all_terms:
        pid = term.pid if term.pid is not None else term.id
        if pid not in term_dict:
            term_dict[pid] = {
                "words": [],
                "description": term.description or "",
            }
        term_dict[pid]["words"].append(term.word or "")
    
    # 转换为列表，限制数量
    result_list = []
    for pid, term_data in list(term_dict.items())[:top_k]:
        result_list.append(term_data)
    
    return result_list


def _format_terminologies_to_xml(terminologies: List[Dict[str, Any]]) -> str:
    """
    将术语列表格式化为 XML 字符串
    
    Args:
        terminologies: 术语列表，格式为 [{"words": [...], "description": "..."}, ...]
    
    Returns:
        XML 字符串
    """
    if not terminologies:
        return ""
    
    # 构建 XML
    xml_parts = ["<terminologies>"]
    
    for term in terminologies:
        words = term.get("words", [])
        description = term.get("description", "")
        
        xml_parts.append("  <terminology>")
        xml_parts.append("    <words>")
        for word in words:
            if word:
                xml_parts.append(f'      <word><![CDATA[{word}]]></word>')
        xml_parts.append("    </words>")
        if description:
            xml_parts.append(f'    <description><![CDATA[{description}]]></description>')
        xml_parts.append("  </terminology>")
    
    xml_parts.append("</terminologies>")
    
    return "\n".join(xml_parts)
