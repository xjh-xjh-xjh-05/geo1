"""
后台管理API路由
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.backend_management import (
    BackendManagementModule, UserRole
)

router = APIRouter(prefix="/admin", tags=["后台管理"])

admin_module = BackendManagementModule()


class LoginInput(BaseModel):
    """登录输入"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserCreateInput(BaseModel):
    """用户创建输入"""
    username: str = Field(..., description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., description="密码")
    role: Optional[str] = Field("user", description="角色")


class ConfigUpdateInput(BaseModel):
    """配置更新输入"""
    value: Any = Field(..., description="配置值")


@router.post("/login", summary="用户登录")
async def login(input_data: LoginInput, ip_address: str = Query("unknown", description="IP地址")):
    """
    用户登录
    """
    try:
        result = admin_module.login(input_data.username, input_data.password, ip_address)
        if "error" in result:
            raise HTTPException(status_code=401, detail=result["error"])

        return {
            "success": True,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@router.post("/logout", summary="用户登出")
async def logout(token: str = Query(..., description="会话令牌"), user_id: str = Query(..., description="用户ID")):
    """
    用户登出
    """
    try:
        success = admin_module.logout(token, user_id)
        return {
            "success": True,
            "data": {
                "message": "登出成功" if success else "登出失败"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登出失败: {str(e)}")


@router.get("/users", summary="获取用户列表")
async def list_users(
    role: Optional[str] = Query(None, description="角色筛选"),
    is_active: Optional[bool] = Query(None, description="状态筛选")
):
    """
    获取用户列表
    """
    try:
        user_role = UserRole(role) if role else None
        users = admin_module.user_manager.list_users(user_role, is_active)
        return {
            "success": True,
            "data": users
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户列表失败: {str(e)}")


@router.post("/users", summary="创建用户")
async def create_user(input_data: UserCreateInput):
    """
    创建新用户
    """
    try:
        role = UserRole(input_data.role)
        result = admin_module.user_manager.create_user(
            input_data.username,
            input_data.email,
            input_data.password,
            role
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "success": True,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建用户失败: {str(e)}")


@router.get("/users/{user_id}", summary="获取用户信息")
async def get_user(user_id: str):
    """
    获取单个用户信息
    """
    try:
        user = admin_module.user_manager.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        return {
            "success": True,
            "data": user
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")


@router.put("/users/{user_id}", summary="更新用户")
async def update_user(user_id: str, updates: Dict[str, Any]):
    """
    更新用户信息
    """
    try:
        success = admin_module.user_manager.update_user(user_id, updates)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")

        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "message": "更新成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新用户失败: {str(e)}")


@router.delete("/users/{user_id}", summary="删除用户")
async def delete_user(user_id: str):
    """
    删除用户
    """
    try:
        success = admin_module.user_manager.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="用户不存在")

        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "message": "删除成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除用户失败: {str(e)}")


@router.get("/config", summary="获取系统配置")
async def get_configs(category: Optional[str] = Query(None, description="配置类别")):
    """
    获取系统配置
    """
    try:
        if category:
            configs = admin_module.config_manager.get_configs_by_category(category)
        else:
            configs = admin_module.config_manager.get_all_configs()

        return {
            "success": True,
            "data": configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@router.put("/config/{key}", summary="更新配置")
async def update_config(key: str, input_data: ConfigUpdateInput, updated_by: str = Query("admin", description="更新者")):
    """
    更新系统配置
    """
    try:
        success = admin_module.config_manager.set_config(key, input_data.value, updated_by)
        if not success:
            raise HTTPException(status_code=400, detail="配置更新失败或不可编辑")

        return {
            "success": True,
            "data": {
                "key": key,
                "value": input_data.value,
                "message": "配置更新成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.get("/dashboard", summary="获取仪表板数据")
async def get_dashboard():
    """
    获取管理仪表板数据
    """
    try:
        data = admin_module.get_dashboard_data()
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取仪表板数据失败: {str(e)}")


@router.get("/audit-logs", summary="获取审计日志")
async def list_audit_logs(
    user_id: Optional[str] = Query(None, description="用户ID筛选"),
    action: Optional[str] = Query(None, description="操作筛选"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    limit: int = Query(100, description="返回数量")
):
    """
    获取审计日志
    """
    try:
        logs = admin_module.audit_logger.get_logs(
            user_id=user_id,
            action=action,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return {
            "success": True,
            "data": logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取审计日志失败: {str(e)}")


@router.get("/system/status", summary="获取系统状态")
async def get_system_status():
    """
    获取系统运行状态
    """
    try:
        status = admin_module.system_monitor.get_system_status()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")


@router.get("/system/performance", summary="获取性能指标")
async def get_performance_metrics():
    """
    获取系统性能指标
    """
    try:
        metrics = admin_module.system_monitor.get_performance_metrics()
        return {
            "success": True,
            "data": metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取性能指标失败: {str(e)}")


@router.get("/permissions/check", summary="检查权限")
async def check_permission(user_id: str = Query(..., description="用户ID"), action: str = Query(..., description="操作")):
    """
    检查用户权限
    """
    try:
        has_permission = admin_module.check_permission(user_id, action)
        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "action": action,
                "has_permission": has_permission
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查权限失败: {str(e)}")
