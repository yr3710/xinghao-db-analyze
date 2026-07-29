"""
参数解析中间件
用于在接口方法执行前自动提取和转换请求参数
"""
from functools import wraps
from typing import Any, Type, get_type_hints, get_origin, get_args, Optional
from inspect import signature, Parameter
from pydantic import BaseModel, ValidationError
from sanic import Request
from common.exception import MyException
from constants.code_enum import SysCodeEnum


def parse_params(handler):
    """
    参数解析装饰器中间件
    自动根据函数签名提取和转换请求参数

    支持的参数类型：
    1. Pydantic BaseModel - 从请求体解析
    2. 基础类型（int, str, float, bool）- 从查询参数或表单解析
    3. Optional[类型] - 可选参数

    使用示例：
    @app.post("/api/user")
    @parse_params
    async def create_user(request: Request, user: UserModel, age: int, name: Optional[str] = None):
        # user 会自动从 request.json 解析
        # age 会自动从 query/form 解析并转换为 int
        # name 是可选参数
        pass
    """

    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        # 获取函数签名
        sig = signature(handler)
        type_hints = get_type_hints(handler)

        # 解析参数
        parsed_kwargs = {}

        for param_name, param in sig.parameters.items():
            # 跳过 request 参数
            if param_name == 'request':
                continue

            # 跳过已经传入的参数
            if param_name in kwargs:
                continue

            # 获取参数类型
            param_type = type_hints.get(param_name, str)

            # 通过类型判断是否为 Request 对象
            if param_type is Request or (isinstance(param_type, type) and issubclass(param_type, Request)):
                continue

            # 检查是否是 Optional 类型
            is_optional = get_origin(param_type) is type(Optional[int])
            if is_optional:
                actual_type = get_args(param_type)[0]
            else:
                actual_type = param_type

            # 获取默认值
            has_default = param.default != Parameter.empty
            default_value = param.default if has_default else None
            required = not has_default and not is_optional

            # 判断参数来源并解析
            if isinstance(actual_type, type) and issubclass(actual_type, BaseModel):
                # Pydantic 模型，从请求体解析
                parsed_kwargs[param_name] = _parse_body(request, actual_type, required)
            else:
                # 基础类型，从查询参数或表单解析
                parsed_kwargs[param_name] = _parse_query_or_form(
                    request, param_name, actual_type, default_value, required
                )

        # 合并解析的参数
        kwargs.update(parsed_kwargs)

        # 调用原始处理函数
        return await handler(request, *args, **kwargs)

    return wrapper


def _parse_body(request: Request, model: Type[BaseModel], required: bool = True) -> Optional[BaseModel]:
    """解析请求体为 Pydantic 模型"""
    try:
        data = request.json or {}
        if not data and not required:
            return None
        return model.model_validate(data)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            field = '.'.join(str(x) for x in error['loc'])
            msg = error['msg']
            errors.append(f"{field}: {msg}")
        raise MyException(SysCodeEnum.PARAM_ERROR, f"参数验证失败: {'; '.join(errors)}")
    except Exception as e:
        raise MyException(SysCodeEnum.PARAM_ERROR, f"解析请求体失败: {str(e)}")


def _parse_query_or_form(request: Request, param_name: str, param_type: Type,
                         default: Any = None, required: bool = False) -> Any:
    """解析查询参数或表单参数"""
    # 优先从查询参数获取
    value = request.args.get(param_name)

    # 如果查询参数没有，尝试从表单获取
    if value is None and request.form:
        value = request.form.get(param_name)

    # 如果都没有，尝试从路径参数获取
    if value is None and hasattr(request, 'match_info'):
        value = request.match_info.get(param_name)

    if value is None:
        if required:
            raise MyException(SysCodeEnum.PARAM_ERROR, f"缺少必需参数: {param_name}")
        return default

    # 类型转换
    return _convert_type(value, param_name, param_type)


def _convert_type(value: Any, param_name: str, param_type: Type) -> Any:
    """类型转换"""
    try:
        if param_type == int:
            return int(value)
        elif param_type == float:
            return float(value)
        elif param_type == bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on')
            return bool(value)
        elif param_type == str:
            return str(value)
        elif param_type == list:
            # 如果是列表类型，尝试解析
            if isinstance(value, list):
                return value
            return [value]
        else:
            return value
    except (ValueError, TypeError) as e:
        raise MyException(SysCodeEnum.PARAM_ERROR, f"参数 {param_name} 类型转换失败: {str(e)}")


# 保留原有的辅助函数，用于手动解析（向后兼容）
def parse_body(request: Request, model: Type[BaseModel]) -> BaseModel:
    """解析请求体为 Pydantic 模型（手动调用）"""
    return _parse_body(request, model, required=True)


def parse_query(request: Request, param_name: str, param_type: Type, default: Any = None,
                required: bool = False) -> Any:
    """解析查询参数（手动调用）"""
    return _parse_query_or_form(request, param_name, param_type, default, required)


def parse_form(request: Request, param_name: str, param_type: Type, default: Any = None, required: bool = False) -> Any:
    """解析表单参数（手动调用）"""
    return _parse_query_or_form(request, param_name, param_type, default, required)

