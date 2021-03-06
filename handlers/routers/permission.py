# -*- coding: utf-8 -*-
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.sql import and_

from fastapi import APIRouter, Query
from fastapi import Depends

from commons.const import *

from models.mysql import db_engine, t_permission
from models.const import *

from settings import settings

from handlers import tool
from handlers.items import ItemOutOperateSuccess, ItemOutOperateFailed
from handlers.items.permission import ListDataPermission, ItemOutPermissionList, ItemOutPermission, ItemInAddPermission, ItemInEditPermission
from handlers.exp import MyException
from handlers.const import *


router = APIRouter(tags=[TAGS_PERMISSION], dependencies=[Depends(tool.check_token)])


@router.get("/permission", tags=[TAGS_PERMISSION], response_model=ItemOutPermissionList, name='获取权限')
async def get_permissions(userinfo: dict = Depends(tool.get_userinfo_from_token), p: Optional[int] = Query(settings.web.page, description='第几页'), ps: Optional[int] = Query(settings.web.page_size, description='每页条数')):
    item_out = ItemOutPermissionList()

    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_PERMISSION_VIEW)

    with db_engine.connect() as conn:
        # 获取当前有多少数据
        count_sql = select([func.count(t_permission.c.id)])
        total = conn.execute(count_sql).scalar()

        # 获取分页后的权限列表
        permission_sql = select([
            t_permission.c.id,
            t_permission.c.pid,
            t_permission.c.name,
            t_permission.c.code,
            t_permission.c.intro,
            t_permission.c.category,
            t_permission.c.status,
            t_permission.c.sub_status,
        ]).order_by('sort', 'id').limit(ps).offset((p - 1) * ps)
        permission_obj_list = conn.execute(permission_sql).fetchall()

    item_out.data = ListDataPermission(
        result=[ItemOutPermission(
            id=permission_obj.id,
            name=permission_obj.name,
            code=permission_obj.code,
            intro=permission_obj.intro,
            category=permission_obj.category,
            status=permission_obj.status,
            sub_status=permission_obj.sub_status,
        ) for permission_obj in permission_obj_list],
        total=total,
        p=p,
        ps=ps,
    )
    return item_out


@router.post("/permission", tags=[TAGS_PERMISSION], response_model=ItemOutOperateSuccess, name='添加权限')
async def add_permission(item_in: ItemInAddPermission, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    添加权限\n
    :param item_in:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_PERMISSION_ADD)

    conn = db_engine.connect()

    try:
        # 查看是否已经有该code的权限
        if not tool.is_code_unique(t_permission, item_in.code, conn):
            raise MyException(status_code=HTTP_400_BAD_REQUEST, detail={'code': MULTI_DATA, 'msg': 'code repeat'})

        # 新增权限
        permission_sql = t_permission.insert().values({
            'pid': item_in.pid,
            'name': item_in.name,
            'code': item_in.code,
            'intro': item_in.intro,
            'category': item_in.category,
            'creator': userinfo['name']
        })
        conn.execute(permission_sql)
        return ItemOutOperateSuccess()
    except MyException as mex:
        raise mex
    except Exception as ex:
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg=str(ex)))
    finally:
        conn.close()


@router.put("/permission/{permission_id}", tags=[TAGS_PERMISSION], response_model=ItemOutOperateSuccess, name="修改权限")
async def edit_permission(permission_id: int, item_in: ItemInEditPermission, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    修改权限\n
    :param permission_id:\n
    :param item_in:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_PERMISSION_EDIT)

    conn = db_engine.connect()

    try:
        # 查找权限
        permission_sql = t_permission.select().where(t_permission.c.id == permission_id).limit(1).with_for_update()
        permission_obj = conn.execute(permission_sql).fetchone()
        if not permission_obj:
            raise MyException(status_code=HTTP_404_NOT_FOUND, detail={'code': HTTP_404_NOT_FOUND, 'msg': 'permission not exists'})

        # 修改权限
        data = {
            'editor': userinfo['name']
        }
        if item_in.pid:
            data['pid'] = item_in.pid
        if item_in.name:
            data['name'] = item_in.name
        if item_in.intro:
            data['intro'] = item_in.intro

        update_permission_sql = t_permission.update().where(t_permission.c.id == permission_id).values(data)
        conn.execute(update_permission_sql)
        return ItemOutOperateSuccess()
    except MyException as mex:
        raise mex
    except:
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.put("/permission/{permission_id}/disable", tags=[TAGS_PERMISSION], name="禁用权限")
async def disable_permission(permission_id: int, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    禁用权限\n
    :param permission_id:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_PERMISSION_DISABLE)

    conn = db_engine.connect()

    try:
        # 查找权限
        permission_sql = t_permission.select().where(t_permission.c.id == permission_id).limit(1).with_for_update()
        conn.execute(permission_sql).fetchone()

        # 修改权限状态为禁用
        update_permission_sql = t_permission.update().where(and_(
            t_permission.c.id == permission_id,
            t_permission.c.status == TABLE_STATUS_VALID,
            t_permission.c.sub_status == TABLE_SUB_STATUS_VALID,
        )).values({
            'status': TABLE_STATUS_INVALID,
            'sub_status': TABLE_SUB_STATUS_INVALID_DISABLE
        })
        conn.execute(update_permission_sql)
        return ItemOutOperateSuccess()
    except:
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.put("/permission/{permission_id}/enable", tags=[TAGS_PERMISSION], name='启用权限')
async def enable_permission(permission_id: int, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    启用权限\n
    :param permission_id:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_PERMISSION_ENABLE)

    conn = db_engine.connect()

    try:
        # 查找权限
        permission_sql = t_permission.select().where(t_permission.c.id == permission_id).limit(1).with_for_update()
        conn.execute(permission_sql).fetchone()

        # 修改权限状态为启用
        update_permission_sql = t_permission.update().where(and_(
            t_permission.c.id == permission_id,
            t_permission.c.status == TABLE_STATUS_INVALID,
            t_permission.c.sub_status == TABLE_SUB_STATUS_INVALID_DISABLE,
        )).values({
            'status': TABLE_STATUS_VALID,
            'sub_status': TABLE_SUB_STATUS_VALID
        })
        conn.execute(update_permission_sql)
        return ItemOutOperateSuccess()
    except:
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.delete("/permission/{permission_id}", tags=[TAGS_PERMISSION], name='删除权限')
async def del_user(permission_id: int, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    删除权限\n
    :param permission_id:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_PERMISSION_DEL)

    conn = db_engine.connect()
    try:
        # 查找权限
        permission_sql = t_permission.select().where(t_permission.c.id == permission_id).limit(1).with_for_update()
        conn.execute(permission_sql).fetchone()

        # 修改权限状态为无效（软删除）
        update_permission_sql = t_permission.update().where(and_(
            t_permission.c.id == permission_id,
            t_permission.c.sub_status != TABLE_SUB_STATUS_INVALID_DEL,
        )).values({
            'status': TABLE_STATUS_INVALID,
            'sub_status': TABLE_SUB_STATUS_INVALID_DEL
        })
        conn.execute(update_permission_sql)
        return ItemOutOperateSuccess()
    except:
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()

