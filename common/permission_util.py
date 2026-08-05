"""权限工具函数。"""

from common.exception import MyException
from constants.code_enum import SysCodeEnum
from model.db_connection_pool import get_db_pool
from model.db_models import TUser


def is_admin(user_id: int) -> bool:
    """按 Aix-DB 源码，通过用户 role 判断管理员。"""
    if not user_id:
        return False

    try:
        with get_db_pool().get_session() as session:
            user = (
                session.query(TUser)
                .filter(TUser.id == user_id)
                .first()
            )
            return bool(user and user.role == "admin")
    except Exception:
        return False


async def check_admin_permission(request):
    """非管理员访问管理接口时抛出权限异常。"""
    from services.user_service import get_user_info

    user_info = await get_user_info(request)
    if user_info.get("role") != "admin":
        raise MyException(
            SysCodeEnum.c_401,
            "权限不足，只有管理员才能操作。",
        )
