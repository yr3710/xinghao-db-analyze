"""
训练示例检索器
基于关键词匹配和 embedding 向量检索训练示例，格式化为模板所需的 XML 格式
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import or_, and_, text, bindparam
from sqlalchemy.orm import Session

from model.db_connection_pool import get_db_pool
from model.db_models import TDataTraining
from services.embedding_service import generate_embedding

logger = logging.getLogger(__name__)
pool = get_db_pool()


def retrieve_training_examples(
    question: str,
    datasource_id: Optional[int] = None,
    oid: int = 1,
    top_k: int = 5,
    use_embedding: bool = True,
) -> str:
    """
    检索训练示例并格式化为模板所需的 XML 格式
    
    Args:
        question: 用户问题
        datasource_id: 数据源ID（可选）
        oid: 组织ID（默认：1）
        top_k: 返回的最大示例数量（默认：5）
        use_embedding: 是否使用 embedding 向量检索（默认：True）
    
    Returns:
        格式化的训练示例 XML 字符串，如果没有找到则返回空字符串
    """
    if not question or not question.strip():
        return ""
    
    if not datasource_id:
        # 如果没有数据源ID，无法检索训练示例
        return ""
    
    try:
        with pool.get_session() as session:
            # 查询匹配的训练示例
            # 注意：_select_training_by_question 是异步函数，需要在异步环境中调用
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
                results = loop.run_until_complete(_select_training_by_question(
                    session=session,
                    question=question,
                    oid=oid,
                    datasource_id=datasource_id,
                    top_k=top_k,
                    use_embedding=use_embedding,
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
            xml_str = _format_training_examples_to_xml(results)
            
            # Text2SQL Prompt 在后续层接入；当前层直接返回原项目 XML
            return xml_str
            
    except Exception as e:
        logger.error(f"检索训练示例失败: {e}", exc_info=True)
        return ""


async def _select_training_by_question(
    session: Session,
    question: str,
    oid: int,
    datasource_id: int,
    top_k: int = 5,
    use_embedding: bool = True,
) -> List[Dict[str, Any]]:
    """
    通过关键词匹配和 embedding 向量检索训练示例
    
    Args:
        session: 数据库会话
        question: 用户问题
        oid: 组织ID
        datasource_id: 数据源ID
        top_k: 返回的最大数量
        use_embedding: 是否使用 embedding 向量检索
    
    Returns:
        训练示例列表，格式为 [{"question": "...", "suggestion-answer": "..."}, ...]
    """
    training_ids = set()
    
    # 1. 关键词匹配
    question_pattern = f"%{question}%"
    stmt = session.query(TDataTraining.id).filter(
        and_(
            TDataTraining.question.ilike(question_pattern),
            TDataTraining.oid == oid,
            TDataTraining.datasource == datasource_id,
            TDataTraining.enabled == True,
        )
    )
    
    keyword_results = stmt.limit(top_k).all()
    for row in keyword_results:
        training_ids.add(row.id)
    
    # 2. Embedding 向量检索（如果启用）
    # 当前层只使用用户配置的在线 embedding 模型
    if use_embedding:
        try:
            # 生成问题的在线 embedding；失败时仅保留关键词结果
            embedding = await generate_embedding(question)
            
            if embedding:
                # 使用 pgvector 的 <=> 操作符计算余弦距离
                # 相似度 = 1 - 余弦距离
                # 将 embedding 列表转换为字符串格式（PostgreSQL vector 格式）
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                
                # 使用 CAST 函数而不是 :: 操作符，避免 SQLAlchemy 参数绑定冲突
                embedding_sql = text("""
                    SELECT id, question, description,
                           (1 - (embedding <=> CAST(:embedding_array AS vector))) AS similarity
                    FROM t_data_training
                    WHERE oid = :oid 
                      AND datasource = :datasource 
                      AND enabled = true
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:embedding_array AS vector)
                    LIMIT :top_k
                """)
                
                embedding_results = session.execute(
                    embedding_sql,
                    {
                        "embedding_array": embedding_str,
                        "oid": oid,
                        "datasource": datasource_id,
                        "top_k": top_k,
                    }
                ).fetchall()
                
                for row in embedding_results:
                    training_ids.add(row.id)
                    
        except Exception as e:
            logger.warning(f"Embedding 检索失败，仅使用关键词匹配: {e}")
    
    if len(training_ids) == 0:
        return []
    
    # 查询完整的训练示例信息
    training_examples = session.query(
        TDataTraining.id,
        TDataTraining.question,
        TDataTraining.description,
    ).filter(TDataTraining.id.in_(list(training_ids)[:top_k])).all()
    
    # 转换为字典格式
    result_list = []
    for row in training_examples:
        result_list.append({
            "question": row.question or "",
            "suggestion-answer": row.description or "",
        })
    
    return result_list


def _format_training_examples_to_xml(examples: List[Dict[str, Any]]) -> str:
    """
    将训练示例列表格式化为 XML 字符串
    
    Args:
        examples: 训练示例列表，格式为 [{"question": "...", "suggestion-answer": "..."}, ...]
    
    Returns:
        XML 字符串
    """
    if not examples:
        return ""
    
    # 构建 XML
    xml_parts = ["<sql-examples>"]
    
    for example in examples:
        question = example.get("question", "")
        suggestion_answer = example.get("suggestion-answer", "")
        
        xml_parts.append("  <sql-example>")
        if question:
            xml_parts.append(f'    <question><![CDATA[{question}]]></question>')
        if suggestion_answer:
            xml_parts.append(f'    <suggestion-answer><![CDATA[{suggestion_answer}]]></suggestion-answer>')
        xml_parts.append("  </sql-example>")
    
    xml_parts.append("</sql-examples>")
    
    return "\n".join(xml_parts)
