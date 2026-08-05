"""
Embedding 数据迁移服务
用于根据当前 embedding 模型重新计算历史数据的 embedding
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from model.db_connection_pool import get_db_pool
from model.db_models import TTerminology, TDataTraining
from model.datasource_models import DatasourceTable, DatasourceField
from services.embedding_service import get_default_embedding_model, generate_embedding
from services.datasource_service import DatasourceService

logger = logging.getLogger(__name__)
pool = get_db_pool()


async def get_current_embedding_model_info() -> Dict[str, Any]:
    """
    获取当前 embedding 模型信息
    
    Returns:
        {
            "model_type": "online",
            "model_name": str,
            "dimension": int | None
        }
    """
    model_config = await get_default_embedding_model()
    
    if model_config:
        # 测试获取维度
        try:
            test_embedding = await generate_embedding("test")
            dimension = len(test_embedding) if test_embedding else None
            return {
                "model_type": "online",
                "model_name": model_config.get("base_model", "unknown"),
                "dimension": dimension
            }
        except Exception as e:
            logger.warning(f"获取在线模型维度失败: {e}")
    
    # 当前层只支持在线 embedding；未配置模型时不回退到本地模型
    return {
        "model_type": "online",
        "model_name": "not configured",
        "dimension": None
    }


async def recalculate_terminology_embeddings(progress_callback: Optional[Callable[[int, int, str], Any]] = None) -> Dict[str, Any]:
    """
    重新计算所有术语的 embedding
    
    Args:
        progress_callback: 进度回调函数 (current, total, message) -> None
    
    Returns:
        {
            "success": bool,
            "total": int,
            "success_count": int,
            "failed_count": int,
            "message": str
        }
    """
    try:
        with pool.get_session() as session:
            # 查询所有术语（只查询父节点）
            terminology_list = session.query(TTerminology).filter(
                TTerminology.pid.is_(None)
            ).all()
            
            total = len(terminology_list)
            if total == 0:
                return {
                    "success": True,
                    "total": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "message": "没有需要重新计算的术语"
                }
            
            if progress_callback:
                await progress_callback(0, total, f"开始重新计算 {total} 个术语的 embedding...")
            
            # 收集所有术语ID
            terminology_ids = [term.id for term in terminology_list]
            
            # 使用现有的批量计算函数
            success_count = 0
            failed_count = 0
            
            try:
                # 重新计算每个术语的 embedding
                from sqlalchemy import update
                
                for idx, term in enumerate(terminology_list):
                    try:
                        if not term.word:
                            failed_count += 1
                            continue
                        
                        # 生成新的 embedding
                        embedding = await generate_embedding(term.word)
                        
                        if embedding:
                            # 更新 embedding
                            stmt = update(TTerminology).where(
                                TTerminology.id == term.id
                            ).values(embedding=embedding)
                            session.execute(stmt)
                            session.commit()
                            success_count += 1
                            
                            # 更新子节点（同义词）的 embedding
                            children = session.query(TTerminology).filter(
                                TTerminology.pid == term.id
                            ).all()
                            
                            for child in children:
                                if child.word:
                                    child_embedding = await generate_embedding(child.word)
                                    if child_embedding:
                                        child_stmt = update(TTerminology).where(
                                            TTerminology.id == child.id
                                        ).values(embedding=child_embedding)
                                        session.execute(child_stmt)
                                        session.commit()
                            
                            if progress_callback and (idx + 1) % 10 == 0:
                                await progress_callback(
                                    idx + 1,
                                    total,
                                    f"术语 embedding 重新计算中: {idx + 1}/{total}"
                                )
                        else:
                            failed_count += 1
                            logger.warning(f"术语 {term.id} 的 embedding 生成失败")
                            
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"重新计算术语 {term.id} 的 embedding 失败: {e}")
                        session.rollback()
                
                if progress_callback:
                    await progress_callback(total, total, f"术语 embedding 重新计算完成：成功 {success_count}，失败 {failed_count}")
                
            except Exception as e:
                logger.error(f"重新计算术语 embedding 失败: {e}", exc_info=True)
                failed_count = total
                if progress_callback:
                    await progress_callback(total, total, f"术语 embedding 重新计算失败: {str(e)}")
            
            return {
                "success": failed_count == 0,
                "total": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "message": f"术语 embedding 重新计算完成：成功 {success_count}，失败 {failed_count}"
            }
            
    except Exception as e:
        logger.error(f"重新计算术语 embedding 异常: {e}", exc_info=True)
        return {
            "success": False,
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "message": f"重新计算失败: {str(e)}"
        }


async def recalculate_training_embeddings(progress_callback: Optional[Callable[[int, int, str], Any]] = None) -> Dict[str, Any]:
    """
    重新计算所有训练数据的 embedding
    
    Args:
        progress_callback: 进度回调函数 (current, total, message) -> None
    
    Returns:
        {
            "success": bool,
            "total": int,
            "success_count": int,
            "failed_count": int,
            "message": str
        }
    """
    try:
        with pool.get_session() as session:
            # 查询所有训练数据
            training_list = session.query(TDataTraining).all()
            
            total = len(training_list)
            if total == 0:
                return {
                    "success": True,
                    "total": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "message": "没有需要重新计算的训练数据"
                }
            
            if progress_callback:
                await progress_callback(0, total, f"开始重新计算 {total} 条训练数据的 embedding...")
            
            success_count = 0
            failed_count = 0
            
            for idx, training in enumerate(training_list):
                # 提前缓存 id，避免回滚后访问属性触发加载异常
                training_id = getattr(training, "id", None)
                try:
                    if not training.question:
                        failed_count += 1
                        continue
                    
                    # 生成新的 embedding
                    embedding = await generate_embedding(training.question)
                    
                    if embedding:
                        # 使用显式 UPDATE，避免 SQLAlchemy 在比较旧值/新值时触发
                        # numpy 向量维度不一致导致的广播错误
                        stmt = (
                            update(TDataTraining)
                            .where(TDataTraining.id == training_id)
                            .values(embedding=embedding)
                        )
                        session.execute(stmt)
                        session.commit()
                        success_count += 1
                        
                        if progress_callback and (idx + 1) % 10 == 0:
                            await progress_callback(
                                idx + 1,
                                total,
                                f"训练数据 embedding 重新计算中: {idx + 1}/{total}"
                            )
                    else:
                        failed_count += 1
                        logger.warning(f"训练数据 {training_id} 的 embedding 生成失败")
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"重新计算训练数据 {training_id} 的 embedding 失败: {e}")
                    session.rollback()
            
            if progress_callback:
                await progress_callback(
                    total,
                    total,
                    f"训练数据 embedding 重新计算完成：成功 {success_count}，失败 {failed_count}"
                )
            
            return {
                "success": failed_count == 0,
                "total": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "message": f"训练数据 embedding 重新计算完成：成功 {success_count}，失败 {failed_count}"
            }
            
    except Exception as e:
        logger.error(f"重新计算训练数据 embedding 异常: {e}", exc_info=True)
        return {
            "success": False,
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "message": f"重新计算失败: {str(e)}"
        }


async def recalculate_table_embeddings(progress_callback: Optional[Callable[[int, int, str], Any]] = None) -> Dict[str, Any]:
    """
    重新计算所有表结构的 embedding
    
    Args:
        progress_callback: 进度回调函数 (current, total, message) -> None
    
    Returns:
        {
            "success": bool,
            "total": int,
            "success_count": int,
            "failed_count": int,
            "message": str
        }
    """
    try:
        with pool.get_session() as session:
            # 查询所有数据源
            from model import Datasource
            datasources = session.query(Datasource).all()
            
            total_tables = 0
            success_count = 0
            failed_count = 0
            
            for ds in datasources:
                try:
                    # 查询该数据源下的所有表
                    tables = session.query(DatasourceTable).filter(
                        DatasourceTable.ds_id == ds.id
                    ).all()
                    
                    if not tables:
                        continue
                    
                    total_tables += len(tables)
                    
                    if progress_callback:
                        await progress_callback(
                            0,
                            total_tables,
                            f"开始重新计算数据源 {ds.name} 的 {len(tables)} 张表的 embedding..."
                        )
                    
                    # 收集表和字段信息
                    items = []
                    for table in tables:
                        # 查询表的字段
                        fields = session.query(DatasourceField).filter(
                            DatasourceField.ds_id == ds.id,
                            DatasourceField.table_id == table.id
                        ).all()
                        
                        fields_data = []
                        for field in fields:
                            fields_data.append({
                                "fieldName": field.field_name,
                                "field_name": field.field_name,
                                "fieldComment": field.field_comment or field.custom_comment or "",
                                "field_comment": field.field_comment or field.custom_comment or "",
                            })
                        
                        items.append({
                            "table": table,
                            "fields": fields_data
                        })
                    
                    # 批量计算 embedding
                    try:
                        DatasourceService._compute_and_save_table_embeddings_batch(session, items)
                        session.commit()
                        
                        # 检查成功数量
                        updated_tables = session.query(DatasourceTable).filter(
                            DatasourceTable.ds_id == ds.id,
                            DatasourceTable.embedding.isnot(None)
                        ).count()
                        
                        success_count += updated_tables
                        failed_count += len(tables) - updated_tables
                        
                        if progress_callback:
                            await progress_callback(
                                success_count,
                                total_tables,
                                f"数据源 {ds.name} 完成：{updated_tables}/{len(tables)} 张表"
                            )
                            
                    except Exception as e:
                        logger.error(f"重新计算数据源 {ds.name} 的表 embedding 失败: {e}", exc_info=True)
                        failed_count += len(tables)
                        session.rollback()
                        
                except Exception as e:
                    logger.error(f"处理数据源 {ds.id} 失败: {e}", exc_info=True)
            
            if progress_callback:
                await progress_callback(
                    total_tables,
                    total_tables,
                    f"表结构 embedding 重新计算完成：成功 {success_count}，失败 {failed_count}"
                )
            
            return {
                "success": failed_count == 0,
                "total": total_tables,
                "success_count": success_count,
                "failed_count": failed_count,
                "message": f"表结构 embedding 重新计算完成：成功 {success_count}，失败 {failed_count}"
            }
            
    except Exception as e:
        logger.error(f"重新计算表结构 embedding 异常: {e}", exc_info=True)
        return {
            "success": False,
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "message": f"重新计算失败: {str(e)}"
        }


async def recalculate_all_embeddings(
    modules: List[str] = None,
    progress_callback: Optional[Callable[[str, int, int, str], Any]] = None
) -> Dict[str, Any]:
    """
    重新计算所有模块的 embedding
    
    Args:
        modules: 要重新计算的模块列表，可选值: ["terminology", "training", "table"]
                 如果为 None，则计算所有模块
        progress_callback: 进度回调函数 (module, current, total, message) -> None
    
    Returns:
        {
            "success": bool,
            "results": {
                "terminology": {...},
                "training": {...},
                "table": {...}
            },
            "message": str
        }
    """
    if modules is None:
        modules = ["terminology", "training", "table"]
    
    results = {}
    all_success = True
    
    # 获取当前模型信息
    model_info = await get_current_embedding_model_info()
    
    if progress_callback:
        await progress_callback(
            "info",
            0,
            0,
            f"当前使用模型: {model_info['model_type']} ({model_info['model_name']}), 维度: {model_info['dimension']}"
        )
    
    # 重新计算术语 embedding
    if "terminology" in modules:
        if progress_callback:
            await progress_callback("terminology", 0, 0, "开始重新计算术语 embedding...")
        
        async def term_progress(current, total, msg):
            if progress_callback:
                await progress_callback("terminology", current, total, msg)
        
        result = await recalculate_terminology_embeddings(term_progress)
        results["terminology"] = result
        if not result["success"]:
            all_success = False
    
    # 重新计算训练数据 embedding
    if "training" in modules:
        if progress_callback:
            await progress_callback("training", 0, 0, "开始重新计算训练数据 embedding...")
        
        async def training_progress(current, total, msg):
            if progress_callback:
                await progress_callback("training", current, total, msg)
        
        result = await recalculate_training_embeddings(training_progress)
        results["training"] = result
        if not result["success"]:
            all_success = False
    
    # 重新计算表结构 embedding
    if "table" in modules:
        if progress_callback:
            await progress_callback("table", 0, 0, "开始重新计算表结构 embedding...")
        
        async def table_progress(current, total, msg):
            if progress_callback:
                await progress_callback("table", current, total, msg)
        
        result = await recalculate_table_embeddings(table_progress)
        results["table"] = result
        if not result["success"]:
            all_success = False
    
    return {
        "success": all_success,
        "model_info": model_info,
        "results": results,
        "message": "所有 embedding 重新计算完成"
    }

