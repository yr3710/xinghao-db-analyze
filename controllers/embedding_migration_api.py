"""
数据迁移 API
"""
import logging
from sanic import Blueprint, Request
from sanic_ext import openapi
from sanic.response import ResponseStream
import json
import asyncio

from common.res_decorator import async_json_resp
from common.token_decorator import check_token
from common.param_parser import parse_params
from services.embedding_migration_service import (
    get_current_embedding_model_info,
    recalculate_all_embeddings,
    recalculate_terminology_embeddings,
    recalculate_training_embeddings,
    recalculate_table_embeddings,
)

logger = logging.getLogger(__name__)
bp = Blueprint("embeddingMigration", url_prefix="/system/embedding-migration")


@bp.get("/model-info")
@openapi.summary("获取当前 embedding 模型信息")
@openapi.tag("数据迁移")
@check_token
@async_json_resp
async def get_model_info(request: Request):
    """获取当前使用的 embedding 模型信息"""
    return await get_current_embedding_model_info()


@bp.post("/recalculate")
@openapi.summary("重新计算 embedding")
@openapi.tag("数据迁移")
@openapi.body({
    "application/json": {
        "schema": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["terminology", "training", "table"]},
                    "description": "要重新计算的模块列表，为空则计算所有模块"
                }
            }
        }
    }
})
@openapi.response(
    200,
    {"text/event-stream": {"schema": {"type": "string"}}},
    description="流式返回进度数据",
)
@check_token
async def recalculate_embeddings(request: Request):
    """
    重新计算 embedding（支持 SSE 流式返回进度）
    """
    body = request.json or {}
    modules = body.get("modules")
    
    async def stream_fn(response):
        """生成 SSE 流"""
        progress_queue = asyncio.Queue()
        
        async def progress_wrapper(module, current, total, message):
            """包装进度回调为异步"""
            await progress_queue.put({
                "type": "progress",
                "module": module,
                "current": current,
                "total": total,
                "message": message,
                "percentage": int((current / total * 100)) if total > 0 else 0
            })
        
        try:
            # 发送开始事件
            await response.write(f"data: {json.dumps({'type': 'start', 'message': '开始重新计算 embedding...'})}\n\n")
            
            # 启动重新计算任务
            task = asyncio.create_task(
                recalculate_all_embeddings(modules, progress_wrapper)
            )
            
            # 轮询进度队列并发送
            while True:
                try:
                    # 等待进度更新（超时 0.5 秒）
                    progress_data = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                    await response.write(f"data: {json.dumps(progress_data)}\n\n")
                except asyncio.TimeoutError:
                    # 检查任务是否完成
                    if task.done():
                        break
                    # 发送心跳保持连接
                    await response.write(f"data: {json.dumps({'type': 'heartbeat'})}\n\n")
                    continue
            
            # 等待任务完成
            result = await task
            
            # 发送完成事件
            await response.write(f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n")
            
        except Exception as e:
            logger.error(f"重新计算 embedding 失败: {e}", exc_info=True)
            error_data = {
                "type": "error",
                "message": f"重新计算失败: {str(e)}"
            }
            await response.write(f"data: {json.dumps(error_data)}\n\n")
    
    return ResponseStream(stream_fn, content_type="text/event-stream")


@bp.post("/recalculate-sync")
@openapi.summary("重新计算 embedding（同步方式，不推荐用于大量数据）")
@openapi.tag("数据迁移")
@openapi.body({
    "application/json": {
        "schema": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["terminology", "training", "table"]},
                    "description": "要重新计算的模块列表，为空则计算所有模块"
                }
            }
        }
    }
})
@check_token
@async_json_resp
async def recalculate_embeddings_sync(request: Request):
    """
    重新计算 embedding（同步返回，不推荐用于大量数据）
    """
    body = request.json or {}
    modules = body.get("modules")
    
    # 简单的进度回调（仅记录日志）
    def progress_callback(module, current, total, message):
        logger.info(f"[{module}] {message} ({current}/{total})")
    
    result = await recalculate_all_embeddings(modules, progress_callback)
    return result
