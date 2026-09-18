"""
管理后台页面 - 包含用户管理、系统配置、规则管理、数据统计等功能
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
import requests
import time

API_BASE_URL = os.environ.get("API_URL", "http://localhost:8000/api/v1")

# 注意：不在这里调用 set_page_config，由主程序统一配置


def init_session_state():
    """初始化 session 状态"""
    if 'auth_token' not in st.session_state:
        st.session_state.auth_token = None
    if 'user_info' not in st.session_state:
        st.session_state.user_info = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "dashboard"
    # 添加API响应缓存
    if 'api_cache' not in st.session_state:
        st.session_state.api_cache = {}
    if 'cache_timestamp' not in st.session_state:
        st.session_state.cache_timestamp = {}


def get_cached_api_data(url, headers=None, params=None, timeout=10, cache_seconds=300):
    """获取缓存的API数据"""
    # 生成缓存键
    cache_key = f"{url}_{str(params)}"
    
    # 检查缓存是否存在且未过期
    current_time = time.time()
    if cache_key in st.session_state.api_cache:
        cached_time = st.session_state.cache_timestamp.get(cache_key, 0)
        if current_time - cached_time < cache_seconds:
            return st.session_state.api_cache[cache_key]
    
    # 缓存过期或不存在，发送API请求
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            # 更新缓存
            st.session_state.api_cache[cache_key] = data
            st.session_state.cache_timestamp[cache_key] = current_time
            return data
    except Exception:
        pass
    
    return None


def login_page():
    """登录页面"""
    st.markdown("""
    <div style="text-align: center; padding: 3rem 0;">
        <h1 style="font-size: 2.5rem; margin-bottom: 1rem;">🔐 管理后台登录</h1>
        <p style="color: #666; font-size: 1.1rem;">GEO 虚假内容检测平台</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            username = st.text_input("用户名", value="admin")
            password = st.text_input("密码", type="password", value="admin123")
            
            submitted = st.form_submit_button("登录", use_container_width=True)
            
            if submitted:
                try:
                    # 优化API调用，使用更简洁的URL
                    login_url = f"{API_BASE_URL.replace('/api/v1', '')}/api/v1/auth/login"
                    response = requests.post(
                        login_url,
                        json={"username": username, "password": password},
                        timeout=5  # 减少超时时间
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        # 直接获取 token 和用户信息（API 直接返回 LoginResponse）
                        st.session_state.auth_token = data.get("access_token")
                        user_info = data.get("user", {})
                        st.session_state.user_info = {
                            "username": username,
                            "role": user_info.get("role", "user"),
                            "user_id": user_info.get("id"),
                            "email": user_info.get("email"),
                            "tenant_id": user_info.get("tenant_id")
                        }
                        st.success("登录成功！")
                        # 移除st.rerun()，直接继续执行
                    else:
                        st.error(f"登录失败：{response.status_code}")
                        try:
                            error_data = response.json()
                            st.error(f"错误信息：{error_data.get('detail', '未知错误')}")
                        except:
                            pass
                except requests.exceptions.ConnectionError:
                    st.error("无法连接到 API 服务，请检查后端是否启动")
                except Exception as e:
                    st.error(f"登录失败：{str(e)}")


def render_sidebar():
    """渲染侧边栏导航"""
    st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem;">
        <h2 style="color: white; font-size: 1.3rem;">⚙️ 管理后台</h2>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    
    menu_items = {
        "dashboard": "📊 数据看板",
        "users": "👥 用户管理",
        "rules": "📋 规则配置",
        "keywords": "🏷️ 关键词库",
        "alerts": "🚨 告警管理",
        "stats": "📈 统计报表",
        "system": "🔧 系统配置",
        "logs": "📜 检测日志"
    }
    
    for key, label in menu_items.items():
        if st.sidebar.button(
            label, 
            key=f"menu_{key}", 
            use_container_width=True,
            type="primary" if st.session_state.current_page == key else "secondary"
        ):
            st.session_state.current_page = key
            # 移除st.rerun()，直接更新页面状态
    
    st.sidebar.markdown("---")
    
    if st.session_state.user_info:
        st.sidebar.info(f"""
        **当前用户**: {st.session_state.user_info.get('username', 'unknown')}\n
        **角色**: {st.session_state.user_info.get('role', 'user')}
        """)
        
        if st.sidebar.button("退出登录", use_container_width=True):
            st.session_state.auth_token = None
            st.session_state.user_info = None
            # 移除st.rerun()，直接更新状态


def render_dashboard():
    """渲染数据看板"""
    st.markdown("### 📊 数据看板")
    
    # 获取统计数据（使用缓存）
    try:
        headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
        
        # 检测统计（使用缓存）
        stats_data = get_cached_api_data(
            f"{API_BASE_URL}/stats/summary",
            headers=headers,
            timeout=5,
            cache_seconds=60  # 缓存1分钟
        )
        
        if stats_data:
            stats_data = stats_data.get("data", {})
        else:
            stats_data = {}
        
    except Exception:
        stats_data = {}
    
    # 显示指标卡片
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="今日检测量",
            value=stats_data.get("today_count", 0),
            delta=stats_data.get("today_delta", 0)
        )
    
    with col2:
        st.metric(
            label="虚假数据",
            value=stats_data.get("fake_count", 0),
            delta=f"{stats_data.get('fake_rate', 0):.1f}%"
        )
    
    with col3:
        st.metric(
            label="可疑数据",
            value=stats_data.get("suspicious_count", 0),
            delta=f"{stats_data.get('suspicious_rate', 0):.1f}%"
        )
    
    with col4:
        st.metric(
            label="平均置信度",
            value=f"{stats_data.get('avg_confidence', 0):.1f}%",
            delta=stats_data.get("confidence_delta", 0)
        )
    
    st.markdown("---")
    
    # 趋势图表
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 检测趋势（近 7 天）")
        
        dates = [(datetime.now() - timedelta(days=i)).strftime("%m-%d") for i in range(6, -1, -1)]
        
        chart_data = pd.DataFrame({
            "日期": dates,
            "检测量": [stats_data.get(f"day_{i}_count", 0) for i in range(7)]
        })
        
        fig = px.line(chart_data, x="日期", y="检测量", markers=True)
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("#### 风险等级分布")
        
        risk_data = pd.DataFrame({
            "风险等级": ["真实", "可疑", "虚假"],
            "数量": [
                stats_data.get("real_count", 0),
                stats_data.get("suspicious_only_count", 0),
                stats_data.get("fake_count", 0)
            ]
        })
        
        fig = px.pie(risk_data, values="数量", names="风险等级", hole=0.4)
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)


def render_users_page():
    """渲染用户管理页面"""
    st.markdown("### 👥 用户管理")
    
    tab1, tab2, tab3 = st.tabs(["用户列表", "添加用户", "权限管理"])
    
    with tab1:
        st.markdown("#### 用户列表")
        
        try:
            headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
            response_data = get_cached_api_data(
                f"{API_BASE_URL}/users",
                headers=headers,
                timeout=5,
                cache_seconds=300  # 缓存5分钟
            )
            
            if response_data:
                users_data = response_data.get("data", [])
            else:
                # 缓存未命中，使用传统方式请求
                response = requests.get(
                    f"{API_BASE_URL}/users",
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 200:
                    users_data = response.json().get("data", [])
                else:
                    users_data = []
            
            if users_data:
                df = pd.DataFrame(users_data)
                # 重命名列以匹配前端显示
                rename_map = {
                    "id": "用户 ID",
                    "username": "用户名",
                    "email": "邮箱",
                    "role": "角色",
                    "status": "状态",
                    "phone": "电话",
                    "created_at": "创建时间"
                }
                # 只选择存在的列
                available_cols = [col for col in rename_map.keys() if col in df.columns]
                if available_cols:
                    df = df[available_cols].copy()
                    df.rename(columns=rename_map, inplace=True, errors='ignore')
                    st.dataframe(df, use_container_width=True)
                else:
                    st.dataframe(df, use_container_width=True)
            else:
                st.info("暂无用户数据")
        except Exception as e:
            st.error(f"请求失败：{str(e)}")
    
    with tab2:
        st.markdown("#### 添加用户")
        
        with st.form("add_user_form"):
            new_username = st.text_input("用户名")
            new_email = st.text_input("邮箱")
            new_password = st.text_input("密码", type="password")
            new_role = st.selectbox("角色", ["user", "operator", "admin"])
            
            submitted = st.form_submit_button("添加用户")
            
            if submitted and new_username and new_email and new_password:
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                    response = requests.post(
                        f"{API_BASE_URL}/users",
                        json={
                            "username": new_username,
                            "email": new_email,
                            "password": new_password,
                            "role": new_role
                        },
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        st.success("用户添加成功")
                        # 移除st.rerun()，直接更新状态
                    else:
                        st.error(f"添加失败：{response.status_code}")
                except Exception as e:
                    st.error(f"请求失败：{str(e)}")
    
    with tab3:
        st.markdown("#### 权限管理")
        st.info("权限管理功能开发中...")


def render_rules_page():
    """渲染规则配置页面"""
    st.markdown("### 📋 规则配置")
    
    tab1, tab2 = st.tabs(["规则列表", "添加规则"])
    
    with tab1:
        st.markdown("#### 检测规则")
        
        try:
            headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
            response_data = get_cached_api_data(
                f"{API_BASE_URL}/rules",
                headers=headers,
                timeout=5,
                cache_seconds=300  # 缓存5分钟
            )
            
            if response_data:
                rules_data = response_data.get("data", [])
            else:
                # 缓存未命中，使用传统方式请求
                response = requests.get(
                    f"{API_BASE_URL}/rules",
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 200:
                    rules_data = response.json().get("data", [])
                else:
                    rules_data = []
            
            if rules_data:
                df = pd.DataFrame(rules_data)
                display_cols = [col for col in ["rule_id", "rule_name", "rule_type", "enabled", "priority"] if col in df.columns]
                st.dataframe(df[display_cols], use_container_width=True)
            else:
                st.info("暂无规则数据")
        except Exception as e:
            st.error(f"请求失败：{str(e)}")
    
    with tab2:
        st.markdown("#### 添加检测规则")
        
        with st.form("add_rule_form"):
            rule_name = st.text_input("规则名称")
            rule_type = st.selectbox("规则类型", ["geo", "text", "behavior"])
            rule_config = st.text_area("规则配置（JSON 格式）", value='{}')
            enabled = st.checkbox("启用", value=True)
            
            submitted = st.form_submit_button("添加规则")
            
            if submitted and rule_name:
                try:
                    config = json.loads(rule_config) if rule_config else {}
                    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                    response = requests.post(
                        f"{API_BASE_URL}/rules",
                        json={
                            "rule_name": rule_name,
                            "rule_type": rule_type,
                            "rule_config": config,
                            "enabled": enabled
                        },
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        st.success("规则添加成功")
                        # 移除st.rerun()，直接更新状态
                    else:
                        st.error(f"添加失败：{response.status_code}")
                except json.JSONDecodeError:
                    st.error("规则配置必须是有效的 JSON 格式")
                except Exception as e:
                    st.error(f"请求失败：{str(e)}")


def render_keywords_page():
    """渲染关键词库页面"""
    st.markdown("### 🏷️ 关键词库")
    
    tab1, tab2, tab3 = st.tabs(["关键词列表", "添加关键词", "批量导入"])
    
    with tab1:
        st.markdown("#### 关键词列表")
        
        try:
            headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
            response_data = get_cached_api_data(
                f"{API_BASE_URL}/keywords",
                headers=headers,
                timeout=5,
                cache_seconds=300  # 缓存5分钟
            )
            
            if response_data:
                keywords_data = response_data.get("data", [])
            else:
                # 缓存未命中，使用传统方式请求
                response = requests.get(
                    f"{API_BASE_URL}/keywords",
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 200:
                    keywords_data = response.json().get("data", [])
                else:
                    keywords_data = []
            
            if keywords_data:
                df = pd.DataFrame(keywords_data)
                display_cols = [col for col in ["keyword_id", "keyword", "category", "enabled"] if col in df.columns]
                st.dataframe(df[display_cols], use_container_width=True)
            else:
                st.info("暂无关键词数据")
        except Exception as e:
            st.error(f"请求失败：{str(e)}")
    
    with tab2:
        st.markdown("#### 添加关键词")
        
        with st.form("add_keyword_form"):
            keyword = st.text_input("关键词")
            category = st.selectbox("类别", ["营销词", "违规词", "敏感词", "其他"])
            enabled = st.checkbox("启用", value=True)
            
            submitted = st.form_submit_button("添加关键词")
            
            if submitted and keyword:
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                    response = requests.post(
                        f"{API_BASE_URL}/keywords",
                        json={
                            "keyword": keyword,
                            "category": category,
                            "enabled": enabled
                        },
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        st.success("关键词添加成功")
                        # 移除st.rerun()，直接更新状态
                    else:
                        st.error(f"添加失败：{response.status_code}")
                except Exception as e:
                    st.error(f"请求失败：{str(e)}")
    
    with tab3:
        st.markdown("#### 批量导入关键词")
        
        uploaded_file = st.file_uploader("上传 CSV 文件", type=["csv"])
        
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                st.dataframe(df.head(10), use_container_width=True)
                
                if st.button("导入"):
                    st.success("导入成功（功能实现中）")
            except Exception as e:
                st.error(f"读取文件失败：{str(e)}")


def render_alerts_page():
    """渲染告警管理页面"""
    st.markdown("### 🚨 告警管理")
    
    tab1, tab2 = st.tabs(["告警列表", "告警规则"])
    
    with tab1:
        st.markdown("#### 告警历史")
        
        try:
            headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
            response = requests.get(
                f"{API_BASE_URL}/alerts",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                alerts_data = response.json().get("data", [])
                
                if alerts_data:
                    df = pd.DataFrame(alerts_data)
                    display_cols = [col for col in ["alert_id", "alert_level", "title", "created_at", "is_read"] if col in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)
                else:
                    st.info("暂无告警数据")
            else:
                st.error(f"获取告警列表失败：{response.status_code}")
        except Exception as e:
            st.error(f"请求失败：{str(e)}")
    
    with tab2:
        st.markdown("#### 告警规则配置")
        
        try:
            headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
            response = requests.get(
                f"{API_BASE_URL}/alert-rules",
                headers=headers,
                params={"page": 1, "page_size": 50},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                rules_data = result.get("data", {})
                rules_list = rules_data.get("list", [])
                
                if rules_list:
                    for rule in rules_list:
                        with st.expander(
                            f"{'[OK]' if rule.get('enabled') else '[X]'} {rule.get('name', '未命名规则')} - {rule.get('alert_type', 'unknown')}",
                            expanded=False
                        ):
                            st.write(f"**描述**: {rule.get('description', '无')}")
                            st.write(f"**严重程度**: {rule.get('severity', 'unknown')}")
                            st.write(f"**冷却时间**: {rule.get('cooldown_minutes', 0)} 分钟")
                            st.write(f"**触发次数**: {rule.get('trigger_count', 0)}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("编辑", key=f"edit_rule_{rule.get('id')}"):
                                    st.info("编辑功能开发中...")
                            with col2:
                                if st.button("删除", key=f"delete_rule_{rule.get('id')}", type="secondary"):
                                    st.warning("删除功能开发中...")
                else:
                    st.info("暂无告警规则")
                    
                # 创建新规则
                st.markdown("---")
                st.markdown("#### 创建新规则")
                
                with st.form("create_alert_rule_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        rule_name = st.text_input("规则名称")
                        alert_type = st.selectbox(
                            "告警类型",
                            ["high_risk", "batch_fake", "anomaly_detection", "custom"]
                        )
                        severity = st.selectbox(
                            "严重程度",
                            ["critical", "high", "medium", "low"]
                        )
                    with col2:
                        description = st.text_area("描述")
                        cooldown = st.number_input("冷却时间 (分钟)", min_value=0, value=60)
                        enabled = st.checkbox("启用规则", value=True)
                    
                    submitted = st.form_submit_button("创建规则", use_container_width=True)
                    
                    if submitted:
                        st.success("规则创建功能开发中...")
            else:
                st.error(f"获取告警规则失败：{response.status_code}")
        except Exception as e:
            st.error(f"请求失败：{str(e)}")


def render_stats_page():
    """渲染统计报表页面"""
    st.markdown("### 📈 统计报表")
    
    tab1, tab2, tab3 = st.tabs(["检测统计", "趋势分析", "导出报表"])
    
    with tab1:
        st.markdown("#### 检测统计")
        
        # 实现延迟加载
        if 'stats_loaded' not in st.session_state:
            st.session_state.stats_loaded = False
        
        if not st.session_state.stats_loaded:
            with st.spinner("加载数据中..."):
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                    response_data = get_cached_api_data(
                        f"{API_BASE_URL}/stats/summary",
                        headers=headers,
                        timeout=5,
                        cache_seconds=60  # 缓存1分钟
                    )
                    
                    if response_data:
                        stats_data = response_data.get("data", {})
                    else:
                        # 缓存未命中，使用传统方式请求
                        response = requests.get(
                            f"{API_BASE_URL}/stats/summary",
                            headers=headers,
                            timeout=10
                        )
                        if response.status_code == 200:
                            stats_data = response.json().get("data", {})
                        else:
                            stats_data = {}
                    
                    st.session_state.stats_data = stats_data
                    st.session_state.stats_loaded = True
                except Exception:
                    stats_data = {}
                    st.session_state.stats_data = stats_data
                    st.session_state.stats_loaded = True
        else:
            stats_data = st.session_state.get('stats_data', {})
        
        # 关键指标卡片
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="📊 今日检测量",
                value=stats_data.get("today_count", 0),
                delta=stats_data.get("today_delta", 0)
            )
        
        with col2:
            st.metric(
                label="[!] 今日疑似虚假",
                value=stats_data.get("today_fake", 0),
                delta=None
            )
        
        with col3:
            st.metric(
                label="📈 累计检测量",
                value=stats_data.get("total_count", 0),
                delta=None
            )
        
        with col4:
            st.metric(
                label="🎯 累计疑似虚假",
                value=stats_data.get("total_fake", 0),
                delta=None
            )
        
        # 第二行指标
        col5, col6 = st.columns(2)
        
        with col5:
            pending_count = stats_data.get("pending_count", 0)
            st.metric(
                label="⏳ 待审核",
                value=pending_count,
                delta=None
            )
        
        with col6:
            fake_rate = stats_data.get("fake_rate", 0) * 100
            st.metric(
                label="📉 今日虚假率",
                value=f"{fake_rate:.2f}%",
                delta=None
            )
        
        # 进度条展示
        st.markdown("---")
        st.markdown("#### 数据概览")
        
        total_fake = stats_data.get("total_fake", 0)
        total_count = stats_data.get("total_count", 0)
        
        if total_count > 0:
            fake_percentage = (total_fake / total_count) * 100
            st.progress(fake_percentage / 100)
            st.caption(f"累计虚假率：{fake_percentage:.2f}%")
        else:
            st.info("暂无检测数据")
    
    with tab2:
        st.markdown("#### 趋势分析")
        st.info("趋势分析功能开发中...")
    
    with tab3:
        st.markdown("#### 导出报表")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 导出 Excel 报表", use_container_width=True):
                st.success("报表导出功能开发中...")
        
        with col2:
            if st.button("📄 导出 PDF 报表", use_container_width=True):
                st.success("报表导出功能开发中...")


def render_system_page():
    """渲染系统配置页面"""
    st.markdown("### 🔧 系统配置")
    
    tab1, tab2, tab3 = st.tabs(["系统设置", "缓存管理", "系统监控"])
    
    with tab1:
        st.markdown("#### 系统设置")
        
        try:
            headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
            response = requests.get(
                f"{API_BASE_URL}/system/configs",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                configs_data = response.json().get("data", {})
                
                for category, items in configs_data.items():
                    with st.expander(f"{category}", expanded=False):
                        for item in items:
                            st.text_input(
                                item.get("key", ""),
                                value=str(item.get("value", "")),
                                key=item.get("key", "")
                            )
                
                if st.button("保存配置"):
                    st.success("配置保存成功（功能实现中）")
            else:
                st.error(f"获取配置失败：{response.status_code}")
        except Exception as e:
            st.error(f"请求失败：{str(e)}")
    
    with tab2:
        st.markdown("#### 缓存管理")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 查看缓存统计", use_container_width=True):
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                    response = requests.get(
                        f"{API_BASE_URL}/system/cache/stats",
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        stats = response.json().get("data", {})
                        
                        # 美观的展示缓存统计
                        st.markdown("##### 内存缓存状态")
                        
                        mem_stats = stats.get("memory_cache_stats", {})
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.metric("缓存大小", f"{mem_stats.get('size', 0)} / {mem_stats.get('max_size', 10000)}")
                            st.progress(mem_stats.get('size', 0) / max(mem_stats.get('max_size', 1), 1))
                        
                        with col_b:
                            hit_rate = mem_stats.get('hit_rate', 0) * 100
                            st.metric("命中率", f"{hit_rate:.1f}%")
                            st.progress(hit_rate / 100)
                        
                        st.divider()
                        
                        col_c, col_d = st.columns(2)
                        with col_c:
                            st.metric("命中次数", mem_stats.get('hits', 0))
                        with col_d:
                            st.metric("未命中次数", mem_stats.get('misses', 0))
                            
                        # 详细信息
                        with st.expander("📋 详细统计", expanded=False):
                            st.json(stats)
                    else:
                        st.error(f"获取缓存统计失败：{response.status_code}")
                except Exception as e:
                    st.error(f"请求失败：{str(e)}")
        
        with col2:
            if st.button("🗑️ 清空缓存", use_container_width=True, type="secondary"):
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                    response = requests.post(
                        f"{API_BASE_URL}/system/cache/clear",
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        st.success("[OK] 缓存已清空")
                    else:
                        st.error(f"清空缓存失败：{response.status_code}")
                except Exception as e:
                    st.error(f"请求失败：{str(e)}")
    
    with tab3:
        st.markdown("#### 系统监控")
        
        if st.button("🔍 查看系统状态", use_container_width=True):
            try:
                headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
                response = requests.get(
                    f"{API_BASE_URL}/system/health",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    health = response.json()
                    
                    # 美观的系统状态展示
                    status = health.get("status", "unknown")
                    
                    # 状态指示器
                    if status == "healthy":
                        st.success("[OK] 系统运行正常")
                    elif status == "degraded":
                        st.warning("[!] 系统性能下降")
                    else:
                        st.error("[X] 系统异常")
                    
                    st.markdown("---")
                    
                    # 组件状态卡片
                    st.markdown("##### 组件状态")
                    
                    components = health.get("components", {})
                    
                    # 数据库状态
                    db_status = components.get("database", "unknown")
                    col1, col2 = st.columns(2)
                    with col1:
                        if db_status == "up":
                            st.success("[OK] **数据库**: 正常运行")
                        else:
                            st.error(f"[X] **数据库**: {db_status}")
                    
                    # 缓存状态
                    cache_status = components.get("cache", "unknown")
                    with col2:
                        if "up" in cache_status:
                            st.success(f"[OK] **缓存**: {cache_status}")
                        else:
                            st.warning(f"[!] **缓存**: {cache_status}")
                    
                    st.markdown("---")
                    
                    # 时间戳
                    timestamp = health.get("timestamp", "")
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            st.caption(f"最后检查时间：{dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        except:
                            st.caption(f"时间戳：{timestamp}")
                            
                else:
                    st.error(f"获取系统状态失败：{response.status_code}")
            except Exception as e:
                st.error(f"请求失败：{str(e)}")


def render_logs_page():
    """渲染检测日志页面"""
    st.markdown("### 📜 检测日志")
    
    # 筛选条件
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        risk_level_filter = st.selectbox(
            "风险等级",
            ["全部", "high", "medium", "low"],
            key="risk_level_filter"
        )
    
    with col2:
        review_status_filter = st.selectbox(
            "审核状态",
            ["全部", "pending", "approved", "rejected"],
            key="review_status_filter"
        )
    
    with col3:
        is_fake_filter = st.selectbox(
            "检测结果",
            ["全部", "疑似虚假", "正常"],
            key="is_fake_filter"
        )
    
    with col4:
        if st.button("🔍 查询", use_container_width=True, type="primary"):
            st.session_state.logs_query = True
    
    # 查询日志
    try:
        headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
        
        params = {
            "page": 1,
            "page_size": 50
        }
        
        if risk_level_filter != "全部":
            params["risk_level"] = risk_level_filter
        if review_status_filter != "全部":
            params["review_status"] = review_status_filter
        if is_fake_filter == "疑似虚假":
            params["is_fake"] = True
        elif is_fake_filter == "正常":
            params["is_fake"] = False
        
        response = requests.get(
            f"{API_BASE_URL}/logs",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            logs_data = result.get("data", {})
            logs_list = logs_data.get("list", [])
            
            if logs_list:
                # 显示统计信息
                total = logs_data.get("total", 0)
                st.info(f"共找到 {total} 条记录")
                
                # 转换为 DataFrame
                df = pd.DataFrame(logs_list)
                
                # 选择显示的列
                display_cols = [
                    "record_id", "risk_level", "is_fake", "suspicion_score",
                    "content_text", "platform", "review_status", "created_at"
                ]
                
                # 重命名列
                column_names = {
                    "record_id": "记录 ID",
                    "risk_level": "风险等级",
                    "is_fake": "疑似虚假",
                    "suspicion_score": "可疑度",
                    "content_text": "内容文本",
                    "platform": "平台",
                    "review_status": "审核状态",
                    "created_at": "检测时间"
                }
                
                available_cols = [col for col in display_cols if col in df.columns]
                df_display = df[available_cols].copy()
                df_display.rename(columns=column_names, inplace=True, errors='ignore')
                
                # truncate 长文本
                if "内容文本" in df_display.columns:
                    df_display["内容文本"] = df_display["内容文本"].apply(
                        lambda x: x[:50] + "..." if isinstance(x, str) and len(x) > 50 else x
                    )
                
                st.dataframe(df_display, use_container_width=True)
                
                # 分页信息
                total_pages = logs_data.get("total_pages", 1)
                if total_pages > 1:
                    st.write(f"页码：1 / {total_pages}")
            else:
                st.info("暂无检测日志数据")
        else:
            st.error(f"获取日志失败：{response.status_code}")
    except Exception as e:
        st.error(f"请求失败：{str(e)}")


def main():
    """主函数"""
    init_session_state()
    
    if not st.session_state.auth_token:
        login_page()
        return
    
    render_sidebar()
    
    page = st.session_state.current_page
    
    # 页面切换动画容器
    page_container = st.container()
    
    with page_container:
        # 添加页面标题和加载动画
        page_titles = {
            "dashboard": "📊 数据看板",
            "users": "👥 用户管理",
            "rules": "📋 规则配置",
            "keywords": "🏷️ 关键词库",
            "alerts": "🚨 告警管理",
            "stats": "📈 统计报表",
            "system": "🔧 系统配置",
            "logs": "📜 检测日志"
        }
        
        st.markdown(f"### {page_titles.get(page, '管理后台')}")
        st.markdown("---")
        
        if page == "dashboard":
            render_dashboard()
        elif page == "users":
            render_users_page()
        elif page == "rules":
            render_rules_page()
        elif page == "keywords":
            render_keywords_page()
        elif page == "alerts":
            render_alerts_page()
        elif page == "stats":
            render_stats_page()
        elif page == "system":
            render_system_page()
        elif page == "logs":
            render_logs_page()
        else:
            render_dashboard()


if __name__ == "__main__":
    main()