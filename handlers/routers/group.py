# -*- coding: utf-8 -*-
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.sql import and_

from fastapi import APIRouter, Query
from fastapi import Depends

from commons.const import *

from models.mysql import db_engine, t_group
from models.const import *

from settings import settings

from handlers import tool
from handlers.items import ItemOutOperateSuccess, ItemOutOperateFailed
from handlers.items.group import ItemOutGroupList, ItemInAddGroup, ItemInEditGroup, ItemOutGroup, ListDataGroup, ItemInBindGroupRole
from handlers.exp import MyException
from handlers.const import *


router = APIRouter(tags=[TAGS_GROUP], dependencies=[Depends(tool.check_token)])


@router.get("/group", tags=[TAGS_GROUP], response_model=ItemOutGroupList, name='获取用户组')
async def get_groups(userinfo: dict = Depends(tool.get_userinfo_from_token), p: Optional[int] = Query(settings.web.page, description='第几页'), ps: Optional[int] = Query(settings.web.page_size, description='每页条数')):
    item_out = ItemOutGroupList()

    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_GROUP_VIEW)

    with db_engine.connect() as conn:
        # 获取当前有多少数据
        count_sql = select([func.count(t_group.c.id)])
        total = conn.execute(count_sql).scalar()

        # 获取分页后的用户组列表
        group_sql = select([
            t_group.c.id,
            t_group.c.pid,
            t_group.c.name,
            t_group.c.code,
            t_group.c.intro,
            t_group.c.status,
            t_group.c.sub_status,
        ]).order_by('sort', 'id').limit(ps).offset((p - 1) * ps)
        group_obj_list = conn.execute(group_sql).fetchall()

    item_out.data = ListDataGroup(
        result=[ItemOutGroup(
        id=group_obj.id,
        name=group_obj.name,
        code=group_obj.code,
        intro=group_obj.intro,
        status=group_obj.status,
        sub_status=group_obj.sub_status,
    ) for group_obj in group_obj_list],
        total=total,
        p=p,
        ps=ps,
    )
    return item_out


@router.post("/group", tags=[TAGS_GROUP], response_model=ItemOutOperateSuccess, name='添加用户组')
async def add_group(item_in: ItemInAddGroup, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    添加用户组\n
    :param item_in:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_GROUP_ADD)

    conn = db_engine.connect()
    trans = conn.begin()

    try:
        # 查看是否已经有该code的用户组
        if not tool.is_code_unique(t_group, item_in.code, conn):
            raise MyException(status_code=HTTP_400_BAD_REQUEST, detail={'code': MULTI_DATA, 'msg': 'code repeat'})

        # 新增用户组
        print('insert group start')
        group_sql = t_group.insert().values({
            'pid': item_in.pid,
            'name': item_in.name,
            'code': item_in.code,
            'intro': item_in.intro,
            'creator': userinfo['name']
        })
        group_res = conn.execute(group_sql)

        if item_in.role_id:
            # 指定了角色，绑定用户组 - 角色关系
            tool.bind_group_role(group_res.lastrowid, item_in.role_id, userinfo, conn)

        trans.commit()
        return ItemOutOperateSuccess()
    except MyException as mex:
        trans.rollback()
        raise mex
    except Exception as ex:
        trans.rollback()
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg=str(ex)))
    finally:
        conn.close()


@router.put("/group/{group_id}", tags=[TAGS_GROUP], response_model=ItemOutOperateSuccess, name="修改用户组")
async def edit_group(group_id: int, item_in: ItemInEditGroup, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    修改用户组\n
    :param group_id:\n
    :param item_in:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_GROUP_EDIT)

    conn = db_engine.connect()
    trans = conn.begin()

    try:
        # 查找用户组
        group_sql = t_group.select().where(t_group.c.id == group_id).limit(1).with_for_update()
        group_obj = conn.execute(group_sql).fetchone()
        if not group_obj:
            raise MyException(status_code=HTTP_404_NOT_FOUND, detail={'code': HTTP_404_NOT_FOUND, 'msg': 'group not exists'})

        # 修改用户组
        group_val = {
            'editor': userinfo['name']
        }

        if item_in.pid:
            group_val['pid'] = item_in.pid
        if item_in.name:
            group_val['name'] = item_in.name
        if item_in.intro:
            group_val['intro'] = item_in.intro

        update_group_sql = t_group.update().where(t_group.c.id == group_id).values(group_val)
        conn.execute(update_group_sql)

        if item_in.role_id:
            # 指定了角色，绑定用户组 - 角色关系
            tool.bind_group_role(group_id, item_in.role_id, userinfo, conn)

        # 提交事务
        trans.commit()

        return ItemOutOperateSuccess()
    except MyException as mex:
        raise mex
    except:
        trans.rollback()
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.put("/group/{group_id}/disable", tags=[TAGS_GROUP], name="禁用用户组")
async def disable_group(group_id: int, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    禁用用户组\n
    :param group_id:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_GROUP_DISABLE)

    conn = db_engine.connect()
    trans = conn.begin()

    try:
        # 查找用户组
        group_sql = t_group.select().where(t_group.c.id == group_id).limit(1).with_for_update()
        conn.execute(group_sql).fetchone()

        # 修改用户组状态为禁用
        update_group_sql = t_group.update().where(and_(
            t_group.c.id == group_id,
            t_group.c.status == TABLE_STATUS_VALID,
            t_group.c.sub_status == TABLE_SUB_STATUS_VALID,
        )).values({
            'status': TABLE_STATUS_INVALID,
            'sub_status': TABLE_SUB_STATUS_INVALID_DISABLE
        })
        conn.execute(update_group_sql)

        # 提交事务
        trans.commit()

        return ItemOutOperateSuccess()
    except MyException as mex:
        raise mex
    except:
        trans.rollback()
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.put("/group/{group_id}/enable", tags=[TAGS_GROUP], name='启用用户组')
async def enable_group(group_id: int, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    启用用户组\n
    :param group_id:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_GROUP_ENABLE)

    conn = db_engine.connect()
    trans = conn.begin()

    try:
        # 查找用户组
        group_sql = t_group.select().where(t_group.c.id == group_id).limit(1).with_for_update()
        conn.execute(group_sql).fetchone()

        # 修改用户组状态为启用
        update_group_sql = t_group.update().where(and_(
            t_group.c.id == group_id,
            t_group.c.status == TABLE_STATUS_INVALID,
            t_group.c.sub_status == TABLE_SUB_STATUS_INVALID_DISABLE,
        )).values({
            'status': TABLE_STATUS_VALID,
            'sub_status': TABLE_SUB_STATUS_VALID
        })
        conn.execute(update_group_sql)

        # 提交事务
        trans.commit()

        return ItemOutOperateSuccess()
    except:
        trans.rollback()
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.delete("/group/{group_id}", tags=[TAGS_GROUP], name='删除用户组')
async def del_user(group_id: int, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    删除用户组\n
    :param group_id:\n
    :param userinfo:\n
    :return:
    """
    # 鉴权
    tool.check_operation_permission(userinfo['id'], PERMISSION_GROUP_DEL)

    conn = db_engine.connect()
    trans = conn.begin()

    try:
        # 查找用户组
        group_sql = t_group.select().where(t_group.c.id == group_id).limit(1).with_for_update()
        conn.execute(group_sql).fetchone()

        # 修改用户组状态为无效（软删除）
        update_group_sql = t_group.update().where(and_(
            t_group.c.id == group_id,
            t_group.c.sub_status != TABLE_SUB_STATUS_INVALID_DEL,
        )).values({
            'status': TABLE_STATUS_INVALID,
            'sub_status': TABLE_SUB_STATUS_INVALID_DEL
        })
        conn.execute(update_group_sql)

        # 提交事务
        trans.commit()

        return ItemOutOperateSuccess()
    except:
        trans.rollback()
        raise MyException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=ItemOutOperateFailed(code=HTTP_500_INTERNAL_SERVER_ERROR, msg='inter server error'))
    finally:
        conn.close()


@router.post("/group_role", tags=[TAGS_GROUP], response_model=ItemOutOperateSuccess, name="绑定用户组-角色")
async def bind_group_role(item_in: ItemInBindGroupRole, userinfo: dict = Depends(tool.get_userinfo_from_token)):
    """
    绑定用户组-角色\n
    :param item_in:\n
    :param userinfo:\n
    :return:
    """
    with db_engine.connect() as conn:
        tool.bind_group_role(item_in.group_id, item_in.role_id, userinfo, conn)

    return ItemOutOperateSuccess()

