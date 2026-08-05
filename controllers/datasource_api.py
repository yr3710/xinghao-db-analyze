"""
数据源管理API
"""

import logging

from sanic import Blueprint, request
from sanic_ext import openapi

from common.exception import MyException
from common.param_parser import parse_params
from common.permission_util import check_admin_permission
from common.res_decorator import async_json_resp
from constants.code_enum import SysCodeEnum
from model.db_connection_pool import get_db_pool
from model.schemas import (
    CheckDatasourceRequest,
    CheckDatasourceResponse,
    CreateDatasourceRequest,
    CreateDatasourceResponse,
    DatasourceAuthRequest,
    DatasourceAuthResponse,
    DatasourceDetailResponse,
    DatasourceListResponse,
    DeleteDatasourceResponse,
    GetAuthorizedUsersResponse,
    UpdateDatasourceRequest,
    UpdateDatasourceResponse,
    get_schema,
)
from services.datasource_service import DatasourceService
from services.user_service import get_user_info

logger = logging.getLogger(__name__)

bp = Blueprint("datasource", url_prefix="/datasource")

@bp.get("/list")
@openapi.summary("获取数据源列表")
@openapi.description("获取当前用户的数据源列表")
@openapi.tag("数据服务")
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(DatasourceListResponse),
        }
    },
    description="获取成功",
)
@async_json_resp
async def get_datasource_list(req: request.Request):
    """获取数据源列表"""
    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:

            user_info = await get_user_info(req)
            datasources = DatasourceService.get_datasource_list(
                session, user_info["id"]
            )

            result = []
            for ds in datasources:
                # 解密配置信息
                configuration = ds.configuration
                if configuration:
                    try:
                        import json

                        from common.datasource_util import DatasourceConfigUtil

                        config_dict = DatasourceConfigUtil.decrypt_config(configuration)
                        configuration = json.dumps(config_dict)
                    except Exception as e:
                        logger.error(f"解密配置失败: {e}")
                        # 如果解密失败，尝试判断是否为明文（JSON或Python Dict字符串）并标准化为JSON
                        try:
                            import json

                            # 尝试作为JSON解析
                            json.loads(configuration)
                        except:
                            try:
                                import ast

                                config_dict = ast.literal_eval(configuration)
                            except:
                                # 确实无法解析，保持原样
                                pass
                result.append(
                    {
                        "id": ds.id,
                        "name": ds.name,
                        "description": ds.description,
                        "type": ds.type,
                        "type_name": ds.type_name,
                        "status": ds.status,
                        "num": ds.num,
                        "host": config_dict["host"],
                        "database": config_dict["database"],
                        "create_time": (
                            ds.create_time.isoformat() if ds.create_time else None
                        ),
                    }
                )

            return result
    except MyException:
        raise
    except Exception as e:
        logger.error(f"获取数据源列表失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"获取数据源列表失败: {str(e)}")


@bp.post("/add")
@openapi.summary("创建数据源")
@openapi.description("创建新的数据源")
@openapi.tag("数据服务")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(CreateDatasourceRequest),
        }
    },
    description="数据源信息",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(CreateDatasourceResponse),
        }
    },
    description="创建成功",
)
@async_json_resp
@parse_params
async def create_datasource(req: request.Request, body: CreateDatasourceRequest):
    """创建数据源（仅管理员）
    :param req: 请求对象
    :param body: 创建数据源请求体（自动从请求中解析）
    """
    # 检查管理员权限
    await check_admin_permission(req)

    try:
        data = body.model_dump()

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            user_info = await get_user_info(req)
            datasource = DatasourceService.create_datasource(
                session, data, user_info["id"]
            )

            return {
                "id": datasource.id,
                "name": datasource.name,
                "type": datasource.type,
                "status": datasource.status,
            }
    except MyException:
        raise
    except Exception as e:
        logger.error(f"创建数据源失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"创建数据源失败: {str(e)}")


@bp.post("/update")
@openapi.summary("更新数据源")
@openapi.description("更新数据源信息")
@openapi.tag("数据服务")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(UpdateDatasourceRequest),
        }
    },
    description="数据源信息",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(UpdateDatasourceResponse),
        }
    },
    description="更新成功",
)
@async_json_resp
@parse_params
async def update_datasource(req: request.Request, body: UpdateDatasourceRequest):
    """更新数据源（仅管理员）
    :param req: 请求对象
    :param body: 更新数据源请求体（自动从请求中解析）
    """
    # 检查管理员权限
    await check_admin_permission(req)

    try:
        data = body.model_dump()
        ds_id = data.get("id")
        if not ds_id:
            raise MyException(SysCodeEnum.PARAM_ERROR, "缺少数据源ID")

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            datasource = DatasourceService.update_datasource(session, ds_id, data)
            if not datasource:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND, "数据源不存在")

            return {
                "id": datasource.id,
                "name": datasource.name,
            }
    except MyException:
        raise
    except Exception as e:
        logger.error(f"更新数据源失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"更新数据源失败: {str(e)}")


@bp.post("/delete/<ds_id:int>")
@openapi.summary("删除数据源")
@openapi.description("删除指定的数据源")
@openapi.tag("数据服务")
@openapi.parameter(
    name="ds_id",
    location="path",
    schema={"type": "integer"},
    description="数据源ID",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(DeleteDatasourceResponse),
        }
    },
    description="删除成功",
)
@async_json_resp
@parse_params
async def delete_datasource(req: request.Request, ds_id: int):
    """删除数据源（仅管理员）"""
    # 检查管理员权限
    await check_admin_permission(req)

    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            success = DatasourceService.delete_datasource(session, ds_id)
            if not success:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND.value, "数据源不存在")

            return {"message": "删除成功"}
    except MyException:
        raise
    except Exception as e:
        logger.error(f"删除数据源失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"删除数据源失败: {str(e)}")


@bp.post("/get/<ds_id:int>")
@openapi.summary("获取数据源详情")
@openapi.description("根据ID获取数据源详情")
@openapi.tag("数据服务")
@openapi.parameter(
    name="ds_id",
    location="path",
    schema={"type": "integer"},
    description="数据源ID",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(DatasourceDetailResponse),
        }
    },
    description="获取成功",
)
@async_json_resp
@parse_params
async def get_datasource(req: request.Request, ds_id: int):
    """获取数据源详情"""
    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            datasource = DatasourceService.get_datasource_by_id(session, ds_id)
            if not datasource:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND, "数据源不存在")

            # 解密配置信息
            configuration = datasource.configuration
            if configuration:
                try:
                    import json

                    from common.datasource_util import DatasourceConfigUtil

                    config_dict = DatasourceConfigUtil.decrypt_config(configuration)
                    configuration = json.dumps(config_dict)
                except Exception as e:
                    logger.error(f"解密配置失败: {e}")
                    # 如果解密失败，尝试判断是否为明文（JSON或Python Dict字符串）并标准化为JSON
                    try:
                        import json

                        # 尝试作为JSON解析
                        json.loads(configuration)
                    except:
                        try:
                            # 尝试作为Python Dict解析 (例如 {'a': 1})
                            import ast

                            config_dict = ast.literal_eval(configuration)
                            if isinstance(config_dict, dict):
                                configuration = json.dumps(config_dict)
                        except:
                            # 确实无法解析，保持原样
                            pass

            return {
                "id": datasource.id,
                "name": datasource.name,
                "description": datasource.description,
                "type": datasource.type,
                "type_name": datasource.type_name,
                "configuration": configuration,
                "status": datasource.status,
                "num": datasource.num,
                "table_relation": datasource.table_relation,
                "create_time": (
                    datasource.create_time.isoformat()
                    if datasource.create_time
                    else None
                ),
            }
    except MyException:
        raise
    except Exception as e:
        logger.error(f"获取数据源详情失败: {e}", exc_info=True)
        raise MyException(
            SysCodeEnum.SYSTEM_ERROR.value, f"获取数据源详情失败: {str(e)}"
        )


@bp.post("/check")
@openapi.summary("测试数据源连接")
@openapi.description("测试数据源连接是否正常")
@openapi.tag("数据服务")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(CheckDatasourceRequest),
        }
    },
    description="测试连接请求",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(CheckDatasourceResponse),
        }
    },
    description="测试成功",
)
@async_json_resp
@parse_params
async def check_datasource(req: request.Request, body: CheckDatasourceRequest):
    """测试数据源连接
    :param req: 请求对象
    :param body: 测试连接请求体（自动从请求中解析）
    """
    try:
        ds_id = body.id
        ds_type = body.type
        configuration = body.configuration

        # 如果提供了配置信息，直接测试
        if ds_type and configuration:
            is_connected, error_message = DatasourceService.check_connection_by_config(
                ds_type, configuration
            )
            return {"connected": is_connected, "error_message": error_message}

        # 否则根据ID获取数据源测试
        if not ds_id:
            raise MyException(SysCodeEnum.PARAM_ERROR, "缺少数据源ID或配置信息")

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            datasource = DatasourceService.get_datasource_by_id(session, ds_id)
            if not datasource:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND, "数据源不存在")

            # 测试连接
            is_connected, error_message = DatasourceService.check_connection(datasource)

            return {"connected": is_connected, "error_message": error_message}
    except MyException:
        raise
    except Exception as e:
        logger.error(f"测试连接失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR.value, f"测试连接失败: {str(e)}")


@bp.post("/getAuthorizedUsers/<datasource_id:int>")
@openapi.summary("获取已授权用户")
@openapi.description("获取数据源已授权的用户ID列表（仅管理员）")
@openapi.tag("数据服务")
@openapi.parameter(
    name="datasource_id",
    location="path",
    schema={"type": "integer"},
    description="数据源ID",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(GetAuthorizedUsersResponse),
        }
    },
    description="获取成功",
)
@async_json_resp
async def get_authorized_users(req: request.Request, datasource_id: int):
    """获取已授权用户（仅管理员）
    :param req: 请求对象
    :param datasource_id: 数据源ID
    """
    # 检查管理员权限
    await check_admin_permission(req)

    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            # 检查数据源是否存在
            datasource = DatasourceService.get_datasource_by_id(session, datasource_id)
            if not datasource:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND, "数据源不存在")

            # 获取已授权的用户ID列表
            user_ids = DatasourceService.get_authorized_users(session, datasource_id)
            return user_ids
    except MyException:
        raise
    except Exception as e:
        logger.error(f"获取已授权用户失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"获取已授权用户失败: {str(e)}")


@bp.post("/authorize")
@openapi.summary("数据源授权")
@openapi.description("授权用户使用数据源（仅管理员）")
@openapi.tag("数据服务")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(DatasourceAuthRequest),
        }
    },
    description="授权信息",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(DatasourceAuthResponse),
        }
    },
    description="授权成功",
)
@async_json_resp
@parse_params
async def authorize_datasource(req: request.Request, body: DatasourceAuthRequest):
    """数据源授权（仅管理员）
    :param req: 请求对象
    :param body: 授权请求体（自动从请求中解析）
    """
    # 检查管理员权限
    await check_admin_permission(req)

    try:
        datasource_id = body.datasource_id
        user_ids = body.user_ids

        if not datasource_id:
            raise MyException(SysCodeEnum.PARAM_ERROR, "缺少数据源ID")
        # 允许空列表，用于清空授权
        if user_ids is None:
            raise MyException(SysCodeEnum.PARAM_ERROR, "缺少用户ID列表")

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            # 检查数据源是否存在
            datasource = DatasourceService.get_datasource_by_id(session, datasource_id)
            if not datasource:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND, "数据源不存在")

            # 执行授权
            success = DatasourceService.authorize_datasource(
                session, datasource_id, user_ids
            )
            if not success:
                raise MyException(SysCodeEnum.SYSTEM_ERROR, "授权失败")

            return {"message": "授权成功"}
    except MyException:
        raise
    except Exception as e:
        logger.error(f"数据源授权失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"数据源授权失败: {str(e)}")
