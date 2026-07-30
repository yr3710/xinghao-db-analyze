import json
import logging
import httpx
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc

from common.exception import MyException
from constants.code_enum import SysCodeEnum
from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel
from model.serializers import model_to_dict

logger = logging.getLogger(__name__)
pool = get_db_pool()


def _build_openai_headers(api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    detail = error.response.text.strip()
    if not detail:
        return f"HTTP {error.response.status_code}"
    return detail[:500]


def _has_chat_choices(response: httpx.Response) -> bool:
    try:
        choices = response.json().get("choices")
    except (ValueError, AttributeError):
        return False
    return isinstance(choices, list) and bool(choices)


async def _check_embedding_model_legacy(
    supplier: int,
    api_domain: str,
    api_key: str,
) -> dict:
    domain = api_domain.rstrip("/")
    if supplier == 3:
        if domain.endswith("/v1"):
            domain = domain[:-3]
        url = f"{domain}/api/tags"
        headers = None
        timeout = 5
    else:
        url = f"{domain}/models"
        headers = _build_openai_headers(api_key)
        timeout = 10

    async with httpx.AsyncClient() as client:
        request_kwargs = {"timeout": timeout}
        if headers is not None:
            request_kwargs["headers"] = headers
        response = await client.get(url, **request_kwargs)
        response.raise_for_status()

    return {"success": True, "message": "连接成功"}


async def _check_rerank_model(
    supplier: int,
    api_domain: str,
    api_key: str,
    base_model: str,
) -> dict:
    documents = [
        "文本排序模型根据相关性对候选文本进行排序",
        "量子计算是计算科学的前沿领域",
    ]
    is_dashscope = supplier == 6 or "aliyuncs" in api_domain
    if is_dashscope:
        payload = {
            "model": base_model,
            "input": {
                "query": "什么是文本排序模型",
                "documents": documents,
            },
            "parameters": {
                "return_documents": False,
                "top_n": len(documents),
            },
        }
    else:
        payload = {
            "query": "什么是文本排序模型",
            "documents": documents,
        }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            api_domain.rstrip("/"),
            headers=_build_openai_headers(api_key),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

    try:
        response_data = response.json()
    except ValueError:
        return {"success": False, "message": "Rerank 测试失败: 响应不是有效 JSON"}

    if is_dashscope:
        results = (response_data.get("output") or {}).get("results")
    else:
        results = response_data.get("results") if isinstance(response_data, dict) else response_data
    if not isinstance(results, list) or not results:
        return {"success": False, "message": "Rerank 测试失败: 响应中未返回排序结果"}

    return {"success": True, "message": "连接成功"}


async def _check_openai_compatible_model(
    api_domain: str,
    api_key: str,
    base_model: str,
) -> dict:
    domain = api_domain.rstrip("/")
    headers = _build_openai_headers(api_key)
    capabilities = {
        "models": False,
        "chat": False,
        "tool_calling": False,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{domain}/models",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            capabilities["models"] = True
        except httpx.HTTPStatusError:
            # 部分兼容服务未实现 /models，但不影响按已配置模型名称调用。
            pass

        chat_body = {
            "model": base_model,
            "messages": [{"role": "user", "content": "请回复 ok"}],
            "stream": False,
        }
        try:
            response = await client.post(
                f"{domain}/chat/completions",
                headers=headers,
                json=chat_body,
                timeout=30,
            )
            response.raise_for_status()
            if not _has_chat_choices(response):
                return {
                    "success": False,
                    "message": "基础对话测试失败: 模型响应格式异常，未返回 choices",
                    "capabilities": capabilities,
                }
            capabilities["chat"] = True
        except httpx.HTTPStatusError as error:
            return {
                "success": False,
                "message": f"基础对话测试失败: {_http_error_detail(error)}",
                "capabilities": capabilities,
            }

        tool_body = {
            **chat_body,
            "messages": [
                {
                    "role": "user",
                    "content": "请判断是否需要调用 connection_test 工具",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "connection_test",
                        "description": "用于测试模型服务是否支持 Agent 工具调用",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        }
        try:
            response = await client.post(
                f"{domain}/chat/completions",
                headers=headers,
                json=tool_body,
                timeout=30,
            )
            response.raise_for_status()
            if not _has_chat_choices(response):
                return {
                    "success": False,
                    "message": "基础对话可用，但 Agent 工具调用测试响应格式异常",
                    "capabilities": capabilities,
                }
            capabilities["tool_calling"] = True
        except httpx.HTTPStatusError as error:
            detail = _http_error_detail(error)
            if "--enable-auto-tool-choice" in detail:
                message = (
                    "基础对话可用，但 Agent 工具调用不可用: "
                    f"{detail}。请在模型服务启用自动工具调用。"
                )
            else:
                message = f"基础对话可用，但 Agent 工具调用测试失败: {detail}"
            return {
                "success": False,
                "message": message,
                "capabilities": capabilities,
            }

    message = "连接成功，基础对话和 Agent 工具调用均可用"
    if not capabilities["models"]:
        message += "；模型列表接口不可用"

    return {
        "success": True,
        "message": message,
        "capabilities": capabilities,
    }


async def query_model_list(keyword: str = None, model_type: int = None) -> List[dict]:
    with pool.get_session() as session:
        query = session.query(TAiModel)
        if keyword:
            query = query.filter(TAiModel.name.like(f"%{keyword}%"))
        
        if model_type:
            query = query.filter(TAiModel.model_type == model_type)
        
        # Order by default_model desc, then name
        models = query.order_by(desc(TAiModel.default_model), TAiModel.name).all()
        
        result = []
        for model in models:
            m_dict = model_to_dict(model)
            result.append(m_dict)
        return result

async def get_model_detail(model_id: int) -> dict:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
        
        data = model_to_dict(model)
        if data.get('config'):
            try:
                data['config_list'] = json.loads(data['config'])
            except:
                data['config_list'] = []
        else:
            data['config_list'] = []
        return data

async def add_model(data: dict) -> bool:
    with pool.get_session() as session:
        # Check if default
        model_type = data.get('model_type', 1)
        
        # Only LLM (type 1) can be default
        is_default = False
        if model_type == 1:
            count = session.query(TAiModel).filter(
                TAiModel.model_type == 1
            ).count()
            is_default = (count == 0) # First LLM is default

        config_list = data.get('config_list', [])
        config_str = json.dumps(config_list)

        # 处理 api_key：空字符串转换为 None
        api_key = data.get('api_key')
        if api_key is not None and api_key.strip() == '':
            api_key = None

        new_model = TAiModel(
            name=data['name'],
            base_model=data['base_model'],
            model_type=data.get('model_type', 1), # Default to 1 (LLM)
            supplier=data.get('supplier', 1),
            protocol=data.get('protocol', 1),
            api_domain=data['api_domain'],
            api_key=api_key,
            config=config_str,
            default_model=is_default,
            status=1,
            create_time=int(datetime.now().timestamp())
        )
        session.add(new_model)
        session.commit()
        return True

async def update_model(model_id: int, data: dict) -> bool:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
        
        # 更新所有可修改的字段
        if 'name' in data:
            model.name = data['name']
        if 'base_model' in data:
            model.base_model = data['base_model']
        if 'supplier' in data:
            model.supplier = data['supplier']
        if 'model_type' in data:
            model.model_type = data['model_type']
        if 'protocol' in data:
            model.protocol = data['protocol']
        if 'api_domain' in data:
            model.api_domain = data['api_domain']
        if 'api_key' in data:
            # 处理 api_key：空字符串转换为 None
            api_key = data['api_key']
            if api_key is not None and api_key.strip() == '':
                api_key = None
            model.api_key = api_key
        
        if 'config_list' in data:
            model.config = json.dumps(data['config_list'])
            
        session.commit()
        return True

async def delete_model(model_id: int) -> bool:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
             raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
        
        if model.default_model:
             raise MyException(SysCodeEnum.PARAM_ERROR, "Cannot delete default model")
             
        session.delete(model)
        session.commit()
        return True

async def set_default_model(model_id: int) -> bool:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
            
        if model.model_type != 1:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Only LLM can be set as default")

        if model.default_model:
            return True
            
        # Unset previous default for LLM
        session.query(TAiModel).filter(
            TAiModel.default_model == True,
            TAiModel.model_type == 1
        ).update({TAiModel.default_model: False})
        
        model.default_model = True
        session.commit()
        return True

async def get_default_model() -> Optional[dict]:
    """
    查询默认模型
    :return: 默认模型信息，如果不存在返回None
    """
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(
            TAiModel.default_model == True,
            TAiModel.model_type == 1
        ).first()
        
        if not model:
            return None
        
        return model_to_dict(model)

async def check_llm_status(data: dict) -> dict:
    """
    测试模型连接状态
    :param data: 模型配置数据
    :return: 测试结果
    """
    supplier = data.get('supplier', 1)
    model_type = data.get('model_type', 1)
    api_key = data.get('api_key') or ''
    api_domain = data.get('api_domain', '')
    base_model = data.get('base_model', '')
    
    if not api_domain:
        return {"success": False, "message": "API 域名不能为空"}
    
    try:
        if model_type == 2:
            return await _check_embedding_model_legacy(supplier, api_domain, api_key)
        if model_type == 3:
            if not base_model:
                return {"success": False, "message": "基础模型不能为空"}
            return await _check_rerank_model(
                supplier,
                api_domain,
                api_key,
                base_model,
            )

        if supplier == 3:
            domain = api_domain.rstrip("/")
            if domain.endswith('/v1'):
                domain = domain[:-3]
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{domain}/api/tags", timeout=5)
                resp.raise_for_status()
                return {
                    "success": True,
                    "message": "连接成功",
                    "capabilities": {"models": True},
                }

        if not base_model:
            return {"success": False, "message": "基础模型不能为空"}

        return await _check_openai_compatible_model(api_domain, api_key, base_model)
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"success": False, "message": "API Key 无效或未授权"}
        elif e.response.status_code == 404:
            return {"success": False, "message": "API 端点不存在，请检查 API 域名"}
        else:
            return {"success": False, "message": f"连接失败: HTTP {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"success": False, "message": "连接超时，请检查网络或 API 域名"}
    except httpx.ConnectError:
        return {"success": False, "message": "无法连接到服务器，请检查 API 域名"}
    except Exception as e:
        logger.error(f"测试模型连接失败: {e}")
        return {"success": False, "message": f"连接失败: {str(e)}"}

async def fetch_base_models(supplier: int, api_key: str = None, api_domain: str = None) -> List[str]:
    try:
        # OpenAI
        if supplier == 1:
            if not api_key:
                return []
            domain = api_domain or "https://api.openai.com/v1"
            url = f"{domain}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                models = [m['id'] for m in data.get('data', []) if 'gpt' in m['id']]
                return sorted(models)
        
        # Ollama
        elif supplier == 3:
            domain = api_domain or "http://localhost:11434"
            # Ollama API structure: GET /api/tags
            if domain.endswith('/v1'):
                 domain = domain[:-3] # Strip /v1 if present
            
            url = f"{domain}/api/tags"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                models = [m['name'] for m in data.get('models', [])]
                return sorted(models)
        
        # vLLM
        elif supplier == 4:
             if not api_domain:
                 return []
             url = f"{api_domain}/models"
             headers = {}
             if api_key:
                 headers["Authorization"] = f"Bearer {api_key}"
             async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                models = [m['id'] for m in data.get('data', [])]
                return sorted(models)
        
        # DeepSeek
        elif supplier == 5:
             # Similar to OpenAI
             if not api_key:
                 return []
             domain = api_domain or "https://api.deepseek.com"
             url = f"{domain}/models"
             headers = {"Authorization": f"Bearer {api_key}"}
             async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                models = [m['id'] for m in data.get('data', [])]
                return sorted(models)
        
        # MiniMax
        elif supplier == 10:
            if not api_key:
                return []
            domain = api_domain or "https://api.minimaxi.com/v1"
            url = f"{domain}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, headers=headers, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    # 根据OpenAI兼容API格式提取模型列表
                    if 'data' in data:
                        models = [m['id'] for m in data.get('data', [])]
                    else:
                        # 如果没有data字段，尝试其他格式
                        models = [m['id'] for m in data] if isinstance(data, list) else []
                    return sorted(models)
            except:
                # 如果获取模型列表失败，返回一些常见的MiniMax模型名称
                return ["MiniMax-M2.1", "abab6.5s-chat", "abab5.5-chat"]
        
        # Fallback or other providers: Return empty list or hardcoded common ones?
        # For now return empty, frontend can allow manual entry
        return []

    except Exception as e:
        logger.error(f"Failed to fetch models for supplier {supplier}: {e}")
        # Return empty list on error
        return []
