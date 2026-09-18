"""
AI驱动GEO虚假投喂检测系统 - Streamlit主界面 (优化版)
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import json
import sys
import os
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import app_config, scorer_config, geo_config, text_config
from models import InputRecord, GeoData, ContentData, Metadata
from generator.mock_data import MockDataGenerator
from engine.scorer import Scorer
from modules.ui_components.result_display import (
    render_complete_results,
    render_detailed_results_with_alerts,
    render_export_section,
    render_share_section,
    render_statistics_overview,
    render_alert_summary
)
from modules.ui_components.map_component import MapVisualizer, create_map_from_results
from modules.ui_components.data_input import DataInputManager, get_input_form_fields

API_BASE_URL = os.environ.get("API_URL", "http://localhost:8000/api/v1")

st.set_page_config(
    page_title="GEO虚假内容检测平台",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "GEO虚假内容检测平台 v1.0.0\n商用地理信息虚假投喂检测系统"
    }
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
    
    * {
        font-family: 'Noto Sans SC', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
    }
    
    .main .block-container {
        background-color: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        margin-top: 1rem;
        margin-bottom: 1rem;
    }
    
    .stSidebar {
        background: linear-gradient(180deg, #1e40af 0%, #3b82f6 100%);
    }
    
    .stSidebar .element-container {
        color: white;
    }
    
    h1 {
        color: #1e40af;
        font-weight: 700;
    }
    
    h2 {
        color: #1e40af;
        border-bottom: 2px solid #3b82f6;
        padding-bottom: 0.5rem;
    }
    
    h3 {
        color: #374151;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
        color: white;
        padding: 1.25rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }
    
    .metric-card-green {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
    }
    
    .metric-card-red {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
    }
    
    .metric-card-orange {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
    }
    
    .metric-label {
        font-size: 1rem;
        opacity: 0.9;
        margin-top: 0.5rem;
    }
    
    .risk-badge-high {
        background-color: #eb3349;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
    }
    
    .risk-badge-medium {
        background-color: #f5576c;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
    }
    
    .risk-badge-low {
        background-color: #38ef7d;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: 600;
    }
    
    .stButton>button {
        background: linear-gradient(90deg, #3b82f6, #1e40af);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.625rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }
    
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
    }
    
    .stButton>button:active {
        transform: translateY(0);
    }
    
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        background-color: #f1f5f9;
        color: #374151;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #3b82f6, #1e40af);
        color: white;
    }
    
    .info-box {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border-left: 4px solid #3b82f6;
        padding: 1rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
    
    .warning-box {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border-left: 4px solid #f59e0b;
        padding: 1rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
    
    .success-box {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        border-left: 4px solid #10b981;
        padding: 1rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
    
    .error-box {
        background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
        border-left: 4px solid #ef4444;
        padding: 1rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
    
    .map-container {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    .sidebar-title {
        color: white;
        font-size: 1.3rem;
        font-weight: 700;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .sidebar-section {
        background: rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 1.25rem;
        margin: 1rem 0;
    }
    
    div[data-testid="stSidebar"] label {
        color: white !important;
    }
    
    div[data-testid="stSidebar"] .stSlider label {
        color: white !important;
    }
    
    .stProgress .st-bo {
        background-color: #667eea;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    .pulse-animation {
        animation: pulse 2s infinite;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """初始化session状态"""
    if 'records' not in st.session_state:
        st.session_state.records = []
    if 'results' not in st.session_state:
        st.session_state.results = None
    # 延迟初始化Scorer，只在需要时加载
    if 'scorer_loaded' not in st.session_state:
        st.session_state.scorer_loaded = False
        st.session_state.scorer = None
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'token' not in st.session_state:
        st.session_state.token = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "检测"
    if 'app_mode' not in st.session_state:
        st.session_state.app_mode = "detection"
    # 缓存MockDataGenerator实例
    if 'generator' not in st.session_state:
        from generator.mock_data import MockDataGenerator
        st.session_state.generator = MockDataGenerator(seed=42)


def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem;">
        <h1 style="color: white; font-size: 1.5rem; margin-bottom: 0.5rem;">GEO检测平台</h1>
        <p style="color: rgba(255,255,255,0.8); font-size: 0.9rem;">虚假内容智能识别系统</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    
    st.sidebar.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.sidebar.markdown("### 数据生成")
    
    # 使用 session state 保持滑块值
    if 'normal_count' not in st.session_state:
        st.session_state.normal_count = 50
    if 'fake_count' not in st.session_state:
        st.session_state.fake_count = 50
    
    normal_count = st.sidebar.slider(
        "正常数据", 
        0, 200, 
        key='normal_count',
        help="生成正常数据的数量"
    )
    fake_count = st.sidebar.slider(
        "虚假数据", 
        0, 200, 
        key='fake_count',
        help="生成虚假数据的数量"
    )
    
    # 显示当前配置
    st.sidebar.info(f"将生成：**{normal_count}** 条正常 + **{fake_count}** 条虚假 = **{normal_count + fake_count}** 条")
    
    st.sidebar.markdown('</div>', unsafe_allow_html=True)
    
    st.sidebar.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.sidebar.markdown("### 检测参数")
    high_threshold = st.sidebar.slider("高风险阈值", 50, 100, 80)
    medium_threshold = st.sidebar.slider("中风险阈值", 20, 80, 60)
    st.sidebar.markdown('</div>', unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    
    st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.1); border-radius: 12px;">
        <p style="color: white; font-size: 0.9rem; margin: 0;">
            <strong>版本:</strong> v1.0.0<br>
            <strong>状态:</strong> <span style="color: #10b981;">运行中</span>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    return normal_count, fake_count, high_threshold, medium_threshold


def render_metrics():
    """渲染顶部指标卡片"""
    if not st.session_state.results:
        return
    
    results = st.session_state.results
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{results.total_count}</p>
            <p class="metric-label">[统计] 总记录数</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card metric-card-red">
            <p class="metric-value">{results.fake_count}</p>
            <p class="metric-label">[!] 虚假记录</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card metric-card-green">
            <p class="metric-value">{results.normal_count}</p>
            <p class="metric-label">[OK] 正常记录</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card metric-card-orange">
            <p class="metric-value">{results.suspicious_count}</p>
            <p class="metric-label">[!] 可疑记录</p>
        </div>
        """, unsafe_allow_html=True)


def render_data_input_tab(normal_count, fake_count):
    """渲染数据输入标签页"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 模拟数据生成")
        
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        
        # 使用缓存的MockDataGenerator实例
        generator = st.session_state.generator
        
        with btn_col1:
            if st.button("生成混合数据", use_container_width=True):
                with st.spinner("正在生成数据..."):
                    records = generator.generate_batch(
                        normal_count=normal_count,
                        fake_count=fake_count
                    )
                    st.session_state.records = records
                    # 清除之前的检测结果
                    if 'results' in st.session_state:
                        del st.session_state.results
                    st.success(f"[OK] 成功生成 {len(records)} 条数据！（正常：{normal_count} 条，虚假：{fake_count} 条）")
        
        with btn_col2:
            if st.button("瞬移异常数据", use_container_width=True):
                records = generator.generate_teleport_records(count=20)
                st.session_state.records = records
                st.success(f"[OK] 生成 {len(records)} 条瞬移异常数据！")
        
        with btn_col3:
            if st.button("批量相似数据", use_container_width=True):
                records = generator.generate_batch_similar_records(count=30)
                st.session_state.records = records
                st.success(f"[OK] 生成 {len(records)} 条批量相似数据！")
    
    with col2:
        st.markdown("### 单条数据输入")
        
        with st.form("single_input", clear_on_submit=False):
            col_a, col_b = st.columns(2)
            with col_a:
                device_id = st.text_input("设备ID", "D_TEST_001")
            with col_b:
                user_id = st.text_input("用户ID", "U_TEST_001")
            
            col_c, col_d = st.columns(2)
            with col_c:
                latitude = st.number_input("纬度", value=39.9042, format="%.6f", min_value=-90.0, max_value=90.0)
            with col_d:
                longitude = st.number_input("经度", value=116.4074, format="%.6f", min_value=-180.0, max_value=180.0)
            
            text = st.text_area("文本内容", "这家店味道不错，环境干净，服务态度好", height=80)
            
            submitted = st.form_submit_button("添加记录", use_container_width=True)
            if submitted:
                record = InputRecord(
                    record_id=f"R_MANUAL_{datetime.now().strftime('%H%M%S')}",
                    device_id=device_id,
                    user_id=user_id,
                    timestamp=int(datetime.now().timestamp()),
                    geo=GeoData(latitude=latitude, longitude=longitude),
                    content=ContentData(text=text),
                    metadata=Metadata()
                )
                st.session_state.records.append(record)
                st.success("[OK] 记录已添加！")
    
    if st.session_state.records:
        st.markdown("---")
        
        # 如果有检测结果，显示检测结果；否则显示原始数据标签
        if hasattr(st.session_state, 'results') and st.session_state.results:
            st.markdown("---")
            results = st.session_state.results
            
            # 正确的统计逻辑：
            # - 虚假记录：is_fake=True
            # - 正常记录：is_fake=False
            # - 可疑记录：is_fake=False 但风险等级为 medium
            # - 高风险记录：is_fake=True 且风险等级为 high
            
            # 重新计算不重复的统计
            fake_records = [r for r in results.results if r.is_fake]
            normal_records = [r for r in results.results if not r.is_fake]
            high_risk = [r for r in results.results if r.risk_level == "high"]
            medium_risk = [r for r in results.results if r.risk_level == "medium"]
            low_risk = [r for r in results.results if r.risk_level == "low"]
            
            # 可疑记录 = 正常记录中的中风险
            suspicious_only = [r for r in normal_records if r.risk_level == "medium"]
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("[统计] 总记录数", results.total_count)
            with col2:
                st.metric("[!] 虚假记录", len(fake_records))
            with col3:
                st.metric("[OK] 正常记录", len(normal_records))
            with col4:
                st.metric("[!] 可疑记录", len(suspicious_only))
            
            # 显示详细分类
            st.markdown("---")
            st.markdown("##### 📋 风险等级分布")
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.info(f"🔴 高风险：{len(high_risk)} 条")
            with col_b:
                st.warning(f"🟡 中风险：{len(medium_risk)} 条")
            with col_c:
                st.success(f"🟢 低风险：{len(low_risk)} 条")
        else:
            # 显示原始数据标签（未检测状态）
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("[统计] 总记录数", len(st.session_state.records))
            with col2:
                normal = sum(1 for r in st.session_state.records if r.label == "normal")
                st.metric("[OK] 正常记录 (真实标签)", normal)
            with col3:
                fake = sum(1 for r in st.session_state.records if r.label == "fake")
                st.metric("[!] 虚假记录 (真实标签)", fake)
            
            st.info('[提示] 点击"开始检测"按钮后，将显示 AI 检测结果')


def render_detection_tab():
    """渲染检测标签页"""
    if not st.session_state.records:
        st.markdown("""
        <div class="warning-box">
            <p style="margin: 0; font-size: 1.1rem;">[!] 请先生成或输入数据后再进行检测</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button("▶️ 开始检测", type="primary", use_container_width=True):
            with st.spinner("🔍 正在检测中..."):
                progress_bar = st.progress(0)
                
                try:
                    # 延迟加载Scorer
                    if not st.session_state.scorer_loaded:
                        progress_bar.progress(10)
                        from engine.scorer import Scorer
                        st.session_state.scorer = Scorer()
                        st.session_state.scorer_loaded = True
                        progress_bar.progress(30)
                    
                    scorer = st.session_state.scorer
                    scorer.clear_history()
                    scorer.config.high_risk_threshold = 80
                    scorer.config.medium_risk_threshold = 60
                    
                    progress_bar.progress(50)
                    
                    results = scorer.analyze_batch_with_clustering(st.session_state.records)
                    st.session_state.results = results
                    
                    progress_bar.progress(100)
                    st.success(f"[OK] 检测完成！共分析 {results.total_count} 条记录")
                except Exception as e:
                    st.session_state.scorer_loaded = False
                    st.session_state.scorer_error = str(e)
                    st.error(f"[X] 检测失败: {str(e)}")
                    progress_bar.progress(0)
    
    if hasattr(st.session_state, 'results') and st.session_state.results:
        st.markdown("---")
        render_metrics()


def render_results_tab():
    """渲染结果标签页（增强版）"""
    if not hasattr(st.session_state, 'results') or not st.session_state.results:
        st.markdown("""
        <div class="info-box">
            <p style="margin: 0; font-size: 1.1rem;">ℹ️ 暂无检测结果，请先进行检测</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    results = st.session_state.results
    
    # 使用增强的结果展示
    render_complete_results(results)


def render_api_test_tab():
    """渲染API测试标签页"""
    st.markdown("### API接口测试")

    st.markdown("""
    <div class="info-box">
        <p style="margin: 0;">API服务地址: <code>http://localhost:8000</code></p>
        <p style="margin: 0.5rem 0 0 0;">API文档: <a href="http://localhost:8000/docs" target="_blank">http://localhost:8000/docs</a></p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 单条检测API测试")

        with st.form("api_single_test"):
            api_device_id = st.text_input("设备ID", "D_API_001")
            api_user_id = st.text_input("用户ID", "U_API_001")
            api_lat = st.number_input("纬度", value=39.9042, format="%.6f")
            api_lon = st.number_input("经度", value=116.4074, format="%.6f")
            api_text = st.text_area("文本内容", "API测试内容")

            if st.form_submit_button("发送API请求", use_container_width=True):
                payload = {
                    "device_id": api_device_id,
                    "user_id": api_user_id,
                    "timestamp": int(datetime.now().timestamp()),
                    "geo": {
                        "latitude": api_lat,
                        "longitude": api_lon
                    },
                    "content": {
                        "text": api_text
                    }
                }

                try:
                    with st.spinner("调用API中..."):
                        response = requests.post(
                            f"{API_BASE_URL}/detect/single",
                            json=payload,
                            timeout=10
                        )

                    if response.status_code == 200:
                        result = response.json()
                        st.json(result)
                        st.success("API调用成功")
                    else:
                        st.error(f"API调用失败: {response.status_code}")
                        st.json(response.json())
                except Exception as e:
                    st.error(f"连接失败: {str(e)}")

    with col2:
        st.markdown("#### 健康检查")

        if st.button("检查API状态", use_container_width=True):
            try:
                response = requests.get(f"{API_BASE_URL.replace('/api/v1', '')}/health", timeout=5)
                if response.status_code == 200:
                    st.json(response.json())
                    st.success("API服务正常")
                else:
                    st.error("API服务异常")
            except Exception as e:
                st.error(f"无法连接API: {str(e)}")


def render_map_tab():
    """渲染地图可视化标签页"""
    st.markdown("### 地图可视化")

    if not hasattr(st.session_state, 'results') or not st.session_state.results:
        st.markdown("""
        <div class="info-box">
            <p style="margin: 0;">暂无检测结果，请先进行检测后再查看地图可视化</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("生成示例数据并检测", use_container_width=True):
            with st.spinner("正在生成示例数据..."):
                from modules.ui_components.data_input import DataInputManager
                input_manager = DataInputManager()
                sample_data = input_manager.generate_sample_data(count=20, include_fake=True)
                st.session_state.records = input_manager.prepare_for_detection(sample_data)
                st.success(f"已生成 {len(sample_data)} 条示例数据，请点击检测按钮进行检测")
        return

    results = st.session_state.results

    col1, col2 = st.columns([3, 1])

    with col2:
        st.markdown("#### 地图选项")
        show_markers = st.checkbox("显示POI标记", value=True)
        show_heatmap = st.checkbox("显示热力图", value=True)

        if st.button("刷新地图", use_container_width=True):
            st.rerun()

    with col1:
        visualizer = MapVisualizer()

        # 构建包含坐标的结果列表
        map_data = []
        for i, r in enumerate(results.results):
            record = st.session_state.records[i] if i < len(st.session_state.records) else None
            lat = None
            lon = None
            if record and hasattr(record, 'geo'):
                lat = record.geo.latitude
                lon = record.geo.longitude
            map_data.append({
                "lat": lat,
                "lon": lon,
                "record_id": r.record_id,
                "risk_level": r.risk_level,
                "suspicion_score": r.suspicion_score,
                "is_fake": r.is_fake
            })

        if show_markers:
            visualizer.add_markers_from_detection_results(map_data)

        if show_heatmap:
            visualizer.add_heatmap_from_results(map_data)

        html = visualizer.generate_html()
        st.components.v1.html(html, height=600, scrolling=False)

    st.markdown("---")
    st.markdown("#### 风险分布统计")

    fake_count = sum(1 for r in results.results if r.is_fake)
    suspicious_count = sum(1 for r in results.results if not r.is_fake and r.risk_level == "medium")
    normal_count = results.total_count - fake_count - suspicious_count

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总记录数", results.total_count)
    with col2:
        st.metric("虚假记录", fake_count, delta=f"{fake_count/results.total_count*100:.1f}%" if results.total_count > 0 else "0%")
    with col3:
        st.metric("可疑记录", suspicious_count, delta=f"{suspicious_count/results.total_count*100:.1f}%" if results.total_count > 0 else "0%")
    with col4:
        st.metric("正常记录", normal_count, delta=f"{normal_count/results.total_count*100:.1f}%" if results.total_count > 0 else "0%")


def render_enhanced_data_input_tab(normal_count, fake_count):
    """渲染增强版数据输入标签页"""
    st.markdown("### 数据输入")

    input_manager = DataInputManager()

    tab1, tab2, tab3 = st.tabs(["模拟数据生成", "手动录入", "文件上传"])

    with tab1:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 批量生成")
            btn_col1, btn_col2, btn_col3 = st.columns(3)

            generator = st.session_state.generator

            with btn_col1:
                if st.button("生成混合数据", use_container_width=True, key="gen_mixed"):
                    with st.spinner("正在生成数据..."):
                        records = generator.generate_batch(
                            normal_count=normal_count,
                            fake_count=fake_count
                        )
                        st.session_state.records = records
                        if 'results' in st.session_state:
                            del st.session_state.results
                        st.success(f"成功生成 {len(records)} 条数据")

            with btn_col2:
                if st.button("瞬移异常数据", use_container_width=True, key="gen_teleport"):
                    records = generator.generate_teleport_records(count=20)
                    st.session_state.records = records
                    st.success(f"生成 {len(records)} 条瞬移异常数据")

            with btn_col3:
                if st.button("批量相似数据", use_container_width=True, key="gen_similar"):
                    records = generator.generate_batch_similar_records(count=30)
                    st.session_state.records = records
                    st.success(f"生成 {len(records)} 条批量相似数据")

        with col2:
            st.markdown("#### 示例数据")
            sample_count = st.slider("示例数据数量", 5, 50, 10)
            if st.button("生成示例POI数据", use_container_width=True):
                sample_data = input_manager.generate_sample_data(count=sample_count, include_fake=True)
                st.session_state.records = input_manager.prepare_for_detection(sample_data)
                st.success(f"生成 {len(sample_data)} 条示例POI数据")

    with tab2:
        st.markdown("#### 单条数据录入")

        with st.form("enhanced_single_input", clear_on_submit=False):
            col_a, col_b = st.columns(2)
            with col_a:
                poi_name = st.text_input("POI名称 *", "", placeholder="请输入POI名称")
            with col_b:
                poi_category = st.selectbox("分类", ["餐饮", "购物", "休闲", "服务", "交通", "其他"])

            col_c, col_d = st.columns(2)
            with col_c:
                latitude = st.number_input("纬度", value=39.9042, format="%.6f", min_value=-90.0, max_value=90.0)
            with col_d:
                longitude = st.number_input("经度", value=116.4074, format="%.6f", min_value=-180.0, max_value=180.0)

            address = st.text_input("详细地址", "", placeholder="请输入详细地址")
            description = st.text_area("描述", "", height=80, placeholder="请输入POI描述")
            phone = st.text_input("联系电话", "", placeholder="请输入联系电话")

            submitted = st.form_submit_button("添加记录", use_container_width=True)
            if submitted:
                if not poi_name:
                    st.error("请输入POI名称")
                else:
                    poi_data = {
                        "name": poi_name,
                        "address": address,
                        "latitude": latitude,
                        "longitude": longitude,
                        "category": poi_category,
                        "description": description,
                        "phone": phone,
                        "source": "manual"
                    }

                    validation = input_manager.validate_poi_data(poi_data)
                    if validation.is_valid:
                        prepared = input_manager.prepare_for_detection([poi_data])
                        if 'records' not in st.session_state:
                            st.session_state.records = []
                        st.session_state.records.extend(prepared)
                        st.success(f"已添加: {poi_name}")
                        if validation.warnings:
                            for warning in validation.warnings:
                                st.warning(warning)
                    else:
                        for error in validation.errors:
                            st.error(error)

    with tab3:
        st.markdown("#### 文件上传")
        st.info("支持格式: CSV, Excel (.xlsx/.xls), JSON")

        uploaded_file = st.file_uploader(
            "选择文件",
            type=['csv', 'xlsx', 'xls', 'json'],
            help="上传包含POI数据的文件"
        )

        if uploaded_file is not None:
            with st.spinner("正在解析文件..."):
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name

                data_list, errors = input_manager.parse_uploaded_file(tmp_path)

                os.unlink(tmp_path)

                if errors:
                    for error in errors:
                        st.error(error)

                if data_list:
                    st.success(f"成功解析 {len(data_list)} 条记录")

                    with st.expander("预览数据", expanded=True):
                        st.dataframe(pd.DataFrame(data_list).head(10))

                    validation_results = input_manager.batch_validate(data_list)
                    st.info(f"验证结果: {validation_results['valid']} 有效, {validation_results['invalid']} 无效")

                    if st.button("导入有效数据", use_container_width=True):
                        valid_data = [
                            data_list[i]
                            for i, detail in enumerate(validation_results['details'])
                            if detail['is_valid']
                        ]

                        prepared = input_manager.prepare_for_detection(valid_data)
                        if 'records' not in st.session_state:
                            st.session_state.records = []
                        st.session_state.records.extend(prepared)
                        st.success(f"成功导入 {len(prepared)} 条记录")

    if st.session_state.records:
        st.markdown("---")
        st.markdown(f"#### 当前数据: {len(st.session_state.records)} 条记录")

        if st.button("清空所有数据", type="secondary"):
            st.session_state.records = []
            if 'results' in st.session_state:
                del st.session_state.results
            st.rerun()


def main():
    """主函数"""
    init_session_state()
    
    # 顶部导航栏
    nav_col1, nav_col2, nav_col3 = st.columns([4, 1, 1])
    
    with nav_col1:
        st.markdown("""
        <div style="padding: 0.5rem 0;">
            <h1 style="font-size: 1.8rem; margin: 0; color: #1e40af;">GEO虚假内容检测平台</h1>
            <p style="color: #64748b; font-size: 0.9rem; margin: 0;">商用地理信息虚假投喂智能识别系统</p>
        </div>
        """, unsafe_allow_html=True)
    
    with nav_col2:
        if st.button("检测主页", use_container_width=True):
            st.session_state.app_mode = "detection"
    
    with nav_col3:
        if st.button("管理后台", use_container_width=True):
            st.session_state.app_mode = "admin"
    
    # 应用模式切换
    if 'app_mode' not in st.session_state:
        st.session_state.app_mode = "detection"
    
    if st.session_state.app_mode == "admin":
        # 导入并显示管理后台
        from modules.ui_components.admin_panel import main as admin_main
        admin_main()
    else:
        # 显示检测主界面
        st.markdown("---")
        
        normal_count, fake_count, high_threshold, medium_threshold = render_sidebar()
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "数据输入",
            "虚假检测",
            "检测结果",
            "地图可视化",
            "API 测试"
        ])

        with tab1:
            render_enhanced_data_input_tab(normal_count, fake_count)

        with tab2:
            render_detection_tab()

        with tab3:
            render_results_tab()

        with tab4:
            render_map_tab()

        with tab5:
            render_api_test_tab()


if __name__ == "__main__":
    main()
