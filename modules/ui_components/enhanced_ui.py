"""
增强的用户交互模块 - Streamlit界面
补充缺失功能：Excel/CSV上传、地图选点、历史记录、自定义模板
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
import io
import uuid
from typing import List, Dict, Any, Optional
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import InputRecord, GeoData, ContentData, Metadata
from generator.mock_data import MockDataGenerator
from engine.scorer import Scorer

API_BASE_URL = os.environ.get("API_URL", "http://localhost:8000/api/v1")

st.set_page_config(
    page_title="GEO虚假内容检测平台",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)


def init_session_state():
    """初始化增强的session状态"""
    if 'records' not in st.session_state:
        st.session_state.records = []
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'scorer' not in st.session_state:
        st.session_state.scorer = Scorer()
    if 'history' not in st.session_state:
        st.session_state.history = []
    if 'templates' not in st.session_state:
        st.session_state.templates = {}
    if 'detection_tasks' not in st.session_state:
        st.session_state.detection_tasks = {}
    if 'favorites' not in st.session_state:
        st.session_state.favorites = []
    if 'map_selected_point' not in st.session_state:
        st.session_state.map_selected_point = None


def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem;">
        <h1 style="color: white; font-size: 1.5rem; margin-bottom: 0.5rem;">🗺️ GEO检测平台</h1>
        <p style="color: rgba(255,255,255,0.8); font-size: 0.85rem;">虚假内容智能识别系统</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    
    st.sidebar.markdown("### [图表] 数据生成")
    normal_count = st.sidebar.slider("正常数据", 0, 200, 50)
    fake_count = st.sidebar.slider("虚假数据", 0, 200, 50)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 检测参数")
    high_threshold = st.sidebar.slider("高风险阈值", 50, 100, 80)
    medium_threshold = st.sidebar.slider("中风险阈值", 20, 80, 60)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📌 常用功能")
    if st.sidebar.button("📂 批量上传Excel/CSV", use_container_width=True):
        st.session_state.current_page = "数据输入"
        st.rerun()
    
    if st.sidebar.button("🗺️ 地图选点", use_container_width=True):
        st.session_state.current_page = "地图选点"
        st.rerun()
    
    if st.sidebar.button("📋 检测历史", use_container_width=True):
        st.session_state.current_page = "历史记录"
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.1); border-radius: 10px;">
        <p style="color: white; font-size: 0.85rem; margin: 0;">
            <strong>版本:</strong> v1.1.0<br>
            <strong>状态:</strong> <span style="color: #38ef7d;">● 运行中</span>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    return normal_count, fake_count, high_threshold, medium_threshold


def render_file_upload():
    """渲染文件上传组件"""
    st.markdown("### 📂 批量数据上传")
    
    col1, col2 = st.columns(2)
    
    with col1:
        uploaded_file = st.file_uploader(
            "上传Excel/CSV文件",
            type=['xlsx', 'xls', 'csv'],
            help="支持.xlsx, .xls, .csv格式\n请确保文件包含以下列：\n- name/名称: POI名称\n- address/地址: POI地址\n- latitude/纬度: 纬度\n- longitude/经度: 经度\n- category/类别: POI类别\n- phone/电话: 联系电话"
        )
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.success(f"[OK] 成功读取文件，共 {len(df)} 条数据")
                
                column_mapping = {
                    'name': 'name', '名称': 'name',
                    'address': 'address', '地址': 'address',
                    'latitude': 'latitude', '纬度': 'latitude',
                    'longitude': 'longitude', '经度': 'longitude',
                    'category': 'category', '类别': 'category',
                    'phone': 'phone', '电话': 'phone'
                }
                
                df.columns = [column_mapping.get(col, col) for col in df.columns]
                
                required_cols = ['name', 'latitude', 'longitude']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    st.error(f"[X] 缺少必需列: {', '.join(missing_cols)}")
                else:
                    st.dataframe(df.head(10), use_container_width=True)
                    
                    if st.button("📥 导入数据", type="primary"):
                        records = []
                        for idx, row in df.iterrows():
                            try:
                                lat = float(row.get('latitude', 0))
                                lon = float(row.get('longitude', 0))
                                
                                record = InputRecord(
                                    record_id=f"R_BATCH_{idx}_{hash(row.get('name', ''))[:8]}",
                                    device_id=row.get('device_id', 'BATCH_IMPORT'),
                                    user_id=row.get('user_id', 'SYSTEM'),
                                    timestamp=int(datetime.now().timestamp()),
                                    geo=GeoData(latitude=lat, longitude=lon),
                                    content=ContentData(
                                        text=row.get('name', ''),
                                        type=row.get('category', 'unknown')
                                    ),
                                    metadata=Metadata()
                                )
                                records.append(record)
                            except Exception as e:
                                continue
                        
                        st.session_state.records.extend(records)
                        st.success(f"[OK] 成功导入 {len(records)} 条数据")
                        st.rerun()
                        
            except Exception as e:
                st.error(f"[X] 读取文件失败: {str(e)}")
    
    with col2:
        st.markdown("#### 📋 文件格式示例")
        sample_data = {
            'name': ['测试餐厅', '示例加油站', '测试超市'],
            'address': ['北京市朝阳区测试路1号', '上海市浦东新区示例路2号', '广州市天河区测试路3号'],
            'latitude': [39.9042, 31.2304, 23.1291],
            'longitude': [116.4074, 121.4737, 113.2644],
            'category': ['餐饮', '加油站', '超市'],
            'phone': ['010-12345678', '021-87654321', '020-11223344']
        }
        sample_df = pd.DataFrame(sample_data)
        st.dataframe(sample_df, use_container_width=True)
        
        csv_buffer = io.StringIO()
        sample_df.to_csv(csv_buffer, index=False)
        st.download_button(
            "📥 下载示例CSV",
            csv_buffer.getvalue(),
            "sample_poi_data.csv",
            "text/csv",
            use_container_width=True
        )


def render_map_picker():
    """渲染地图选点组件"""
    st.markdown("### 🗺️ 地图选点录入")
    st.markdown("点击地图选择位置，自动获取坐标")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### 点击地图选择位置")
        
        default_lat = 39.9042
        default_lon = 116.4074
        
        selected_lat = st.number_input(
            "纬度",
            value=default_lat,
            format="%.6f",
            min_value=-90.0,
            max_value=90.0,
            key="map_lat"
        )
        
        selected_lon = st.number_input(
            "经度",
            value=default_lon,
            format="%.6f",
            min_value=-180.0,
            max_value=180.0,
            key="map_lon"
        )
        
        if st.button("📍 在地图上显示位置", type="primary"):
            st.session_state.map_selected_point = {
                "latitude": selected_lat,
                "longitude": selected_lon
            }
        
        if st.session_state.map_selected_point:
            point = st.session_state.map_selected_point
            df = pd.DataFrame({
                'lat': [point['latitude']],
                'lon': [point['longitude']]
            })
            
            fig = px.scatter_mapbox(
                df,
                lat='lat',
                lon='lon',
                zoom=15,
                height=400
            )
            fig.update_layout(
                mapbox_style="open-street-map",
                margin={"r": 0, "t": 0, "l": 0, "b": 0}
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("#### [列表] POI信息录入")
        
        with st.form("map_poi_form", clear_on_submit=True):
            poi_name = st.text_input("POI名称", key="map_poi_name")
            poi_address = st.text_input("地址", key="map_poi_address")
            poi_category = st.selectbox(
                "类别",
                ["餐饮", "购物", "生活服务", "丽人", "旅游", "娱乐", "运动", "教育", "医疗", "金融", "房地产", "汽车", "其他"],
                key="map_poi_category"
            )
            poi_phone = st.text_input("电话", key="map_poi_phone")
            poi_description = st.text_area("描述", key="map_poi_desc", height=80)
            
            submitted = st.form_submit_button("➕ 添加到检测列表", use_container_width=True)
            
            if submitted and st.session_state.map_selected_point:
                point = st.session_state.map_selected_point
                
                record = InputRecord(
                    record_id=f"R_MAP_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:4]}",
                    device_id="MAP_PICKER",
                    user_id="USER",
                    timestamp=int(datetime.now().timestamp()),
                    geo=GeoData(latitude=point['latitude'], longitude=point['longitude']),
                    content=ContentData(
                        text=poi_name,
                        type=poi_category
                    ),
                    metadata=Metadata()
                )
                
                st.session_state.records.append(record)
                st.success(f"[OK] 已添加: {poi_name}")
                st.rerun()
            elif submitted and not st.session_state.map_selected_point:
                st.warning("[!] 请先点击地图选择位置")


def render_template_manager():
    """渲染自定义模板管理"""
    st.markdown("### 📋 检测模板管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### ➕ 创建新模板")
        
        with st.form("template_form", clear_on_submit=True):
            template_name = st.text_input("模板名称")
            
            st.markdown("**默认参数**")
            t_lat = st.number_input("默认纬度", value=39.9042, format="%.6f")
            t_lon = st.number_input("默认经度", value=116.4074, format="%.6f")
            t_category = st.selectbox(
                "默认类别",
                ["餐饮", "购物", "生活服务", "其他"]
            )
            t_threshold_high = st.slider("高风险阈值", 50, 100, 80)
            t_threshold_medium = st.slider("中风险阈值", 20, 80, 60)
            
            submitted = st.form_submit_button("💾 保存模板", use_container_width=True)
            
            if submitted and template_name:
                st.session_state.templates[template_name] = {
                    "latitude": t_lat,
                    "longitude": t_lon,
                    "category": t_category,
                    "high_threshold": t_threshold_high,
                    "medium_threshold": t_threshold_medium
                }
                st.success(f"[OK] 模板 '{template_name}' 已保存")
                st.rerun()
    
    with col2:
        st.markdown("#### 📂 已保存的模板")
        
        if st.session_state.templates:
            for name, params in st.session_state.templates.items():
                with st.expander(f"📋 {name}"):
                    st.json(params)
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(f"▶️ 使用模板", key=f"use_{name}"):
                            st.session_state.current_template = params
                            st.success(f"已应用模板: {name}")
                    
                    with col_b:
                        if st.button(f"🗑️ 删除", key=f"del_{name}"):
                            del st.session_state.templates[name]
                            st.rerun()
        else:
            st.info("暂无保存的模板")


def render_favorites():
    """渲染常用检测项收藏"""
    st.markdown("### ⭐ 常用检测项收藏")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### ➕ 添加到收藏")
        
        with st.form("favorite_form", clear_on_submit=True):
            fav_name = st.text_input("名称")
            fav_lat = st.number_input("纬度", value=39.9042, format="%.6f")
            fav_lon = st.number_input("经度", value=116.4074, format="%.6f")
            fav_category = st.selectbox("类别", ["餐饮", "购物", "生活服务", "其他"])
            
            submitted = st.form_submit_button("⭐ 添加收藏", use_container_width=True)
            
            if submitted and fav_name:
                st.session_state.favorites.append({
                    "name": fav_name,
                    "latitude": fav_lat,
                    "longitude": fav_lon,
                    "category": fav_category
                })
                st.success(f"[OK] 已添加收藏: {fav_name}")
                st.rerun()
    
    with col2:
        st.markdown("#### 📂 我的收藏")
        
        if st.session_state.favorites:
            for i, fav in enumerate(st.session_state.favorites):
                with st.expander(f"⭐ {fav['name']}"):
                    st.json(fav)
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(f"🔍 检测", key=f"fav_detect_{i}"):
                            record = InputRecord(
                                record_id=f"R_FAV_{i}_{datetime.now().strftime('%H%M%S')}",
                                device_id="FAVORITE",
                                user_id="USER",
                                timestamp=int(datetime.now().timestamp()),
                                geo=GeoData(latitude=fav['latitude'], longitude=fav['longitude']),
                                content=ContentData(text=fav['name'], type=fav['category']),
                                metadata=Metadata()
                            )
                            st.session_state.records.append(record)
                            st.success("已添加到检测列表")
                    
                    with col_b:
                        if st.button(f"🗑️ 删除", key=f"fav_del_{i}"):
                            st.session_state.favorites.pop(i)
                            st.rerun()
        else:
            st.info("暂无收藏项")


def render_history():
    """渲染检测历史记录"""
    st.markdown("### 📋 检测历史记录")
    
    if not st.session_state.history:
        st.info("暂无检测历史")
        return
    
    for i, hist_item in enumerate(reversed(st.session_state.history[-10:])):
        with st.expander(f"🕐 {hist_item['time']} - {hist_item['count']}条记录"):
            st.json(hist_item)
            
            if st.button(f"[图表] 查看结果", key=f"hist_view_{i}"):
                st.session_state.results = hist_item.get('results')
                st.session_state.current_page = "检测结果"
                st.rerun()


def render_data_input_tab(normal_count, fake_count):
    """渲染数据输入标签页"""
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "[列表] 模拟数据",
        "📂 文件上传",
        "🗺️ 地图选点",
        "📋 模板管理",
        "⭐ 收藏夹"
    ])
    
    with tab1:
        render_mock_data_generation(normal_count, fake_count)
    
    with tab2:
        render_file_upload()
    
    with tab3:
        render_map_picker()
    
    with tab4:
        render_template_manager()
    
    with tab5:
        render_favorites()


def render_mock_data_generation(normal_count, fake_count):
    """渲染模拟数据生成"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🎲 数据生成")
        
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        
        with btn_col1:
            if st.button("🎲 混合数据", use_container_width=True):
                generator = MockDataGenerator(seed=42)
                records = generator.generate_batch(
                    normal_count=normal_count,
                    fake_count=fake_count
                )
                st.session_state.records = records
                st.success(f"[OK] 生成 {len(records)} 条数据")
        
        with btn_col2:
            if st.button("🚀 瞬移异常", use_container_width=True):
                generator = MockDataGenerator(seed=42)
                records = generator.generate_teleport_records(count=20)
                st.session_state.records = records
                st.success(f"[OK] 生成 {len(records)} 条瞬移数据")
        
        with btn_col3:
            if st.button("[列表] 批量相似", use_container_width=True):
                generator = MockDataGenerator(seed=42)
                records = generator.generate_batch_similar_records(count=30)
                st.session_state.records = records
                st.success(f"[OK] 生成 {len(records)} 条相似数据")
    
    with col2:
        st.markdown("#### ✏️ 单条输入")
        
        with st.form("single_input", clear_on_submit=False):
            col_a, col_b = st.columns(2)
            with col_a:
                device_id = st.text_input("设备ID", "D_TEST_001")
            with col_b:
                user_id = st.text_input("用户ID", "U_TEST_001")
            
            col_c, col_d = st.columns(2)
            with col_c:
                latitude = st.number_input("纬度", value=39.9042, format="%.6f")
            with col_d:
                longitude = st.number_input("经度", value=116.4074, format="%.6f")
            
            text = st.text_area("文本内容", height=80)
            
            submitted = st.form_submit_button("➕ 添加记录", use_container_width=True)
            
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
                st.success("[OK] 记录已添加")
    
    if st.session_state.records:
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("[统计] 总记录", len(st.session_state.records))
        with col2:
            normal = sum(1 for r in st.session_state.records if r.label == "normal")
            st.metric("[OK] 正常", normal)
        with col3:
            fake = sum(1 for r in st.session_state.records if r.label == "fake")
            st.metric("[!] 虚假", fake)
        with col4:
            if st.button("🗑️ 清空列表"):
                st.session_state.records = []
                st.rerun()


def render_detection_tab():
    """渲染检测标签页"""
    if not st.session_state.records:
        st.markdown("""
        <div style="background: #fff8e1; border-left: 5px solid #ffc107; padding: 1rem; border-radius: 0 10px 10px 0;">
            <p style="margin: 0;">[!] 请先在「数据输入」中添加要检测的数据</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button("▶️ 开始检测", type="primary", use_container_width=True):
            with st.spinner("🔍 检测中..."):
                progress_bar = st.progress(0)
                
                scorer = st.session_state.scorer
                scorer.clear_history()
                scorer.config.high_risk_threshold = 80
                scorer.config.medium_risk_threshold = 60
                
                progress_bar.progress(30)
                
                results = scorer.analyze_batch_with_clustering(st.session_state.records)
                
                progress_bar.progress(70)
                
                st.session_state.results = results
                
                st.session_state.history.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "count": len(st.session_state.records),
                    "results": results
                })
                
                progress_bar.progress(100)
                st.success(f"[OK] 检测完成！共分析 {results.total_count} 条记录")
    
    if st.session_state.results:
        render_quick_stats()


def render_quick_stats():
    """渲染快速统计"""
    results = st.session_state.results
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("总记录", results.total_count)
    with col2:
        st.metric("[!] 虚假", results.fake_count)
    with col3:
        st.metric("[OK] 正常", results.normal_count)
    with col4:
        st.metric("[!] 可疑", getattr(results, 'suspicious_count', 0))


def render_results_tab():
    """渲染结果标签页"""
    if not st.session_state.results:
        st.info("ℹ️ 暂无检测结果，请先进行检测")
        return
    
    results = st.session_state.results
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "[统计] 统计概览",
        "🗺️ 地图分布",
        "📋 详细结果",
        "📈 趋势分析",
        "📤 导出"
    ])
    
    with tab1:
        render_stats_overview(results)
    
    with tab2:
        render_map_distribution(results)
    
    with tab3:
        render_detailed_results(results)
    
    with tab4:
        render_trend_analysis(results)
    
    with tab5:
        render_export(results)


def render_stats_overview(results):
    """渲染统计概览"""
    col1, col2 = st.columns(2)
    
    with col1:
        risk_counts = {
            "高风险": sum(1 for r in results.results if r.risk_level == "high"),
            "中风险": sum(1 for r in results.results if r.risk_level == "medium"),
            "低风险": sum(1 for r in results.results if r.risk_level == "low")
        }
        
        fig_pie = go.Figure(data=[go.Pie(
            labels=list(risk_counts.keys()),
            values=list(risk_counts.values()),
            hole=0.4,
            marker_colors=['#eb3349', '#f5576c', '#38ef7d']
        )])
        fig_pie.update_layout(title="风险等级分布", height=400)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        scores = [r.suspicion_score for r in results.results]
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=scores, nbinsx=20, marker_color='#667eea'))
        fig_hist.add_vline(x=60, line_dash="dash", line_color="#f5576c", annotation_text="中风险")
        fig_hist.add_vline(x=80, line_dash="dash", line_color="#eb3349", annotation_text="高风险")
        fig_hist.update_layout(title="可疑分数分布", height=400)
        st.plotly_chart(fig_hist, use_container_width=True)


def render_map_distribution(results):
    """渲染地图分布"""
    st.markdown("#### 🗺️ 地理位置分布")
    
    map_data = []
    for r in results.results:
        original = next((rec for rec in st.session_state.records
                        if rec.record_id == r.record_id), None)
        if original and original.geo:
            map_data.append({
                "lat": original.geo.latitude,
                "lon": original.geo.longitude,
                "risk": r.risk_level,
                "score": r.suspicion_score
            })
    
    if map_data:
        df_map = pd.DataFrame(map_data)
        color_map = {"high": "#eb3349", "medium": "#f5576c", "low": "#38ef7d"}
        
        fig_map = px.scatter_mapbox(
            df_map, lat="lat", lon="lon",
            color="risk", size="score",
            color_discrete_map=color_map,
            zoom=3, height=500
        )
        fig_map.update_layout(
            mapbox_style="open-street-map",
            margin={"r": 0, "t": 0, "l": 0, "b": 0}
        )
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.info("暂无地理数据")


def render_detailed_results(results):
    """渲染详细结果"""
    data = []
    for r in results.results:
        original = next((rec for rec in st.session_state.records
                        if rec.record_id == r.record_id), None)
        
        risk_emoji = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(r.risk_level, "⚪")
        
        data.append({
            "记录ID": r.record_id,
            "可疑分数": r.suspicion_score,
            "风险等级": f"{risk_emoji} {r.risk_level}",
            "是否虚假": "是" if r.is_fake else "否",
            "GEO分数": r.geo_score,
            "文本分数": r.text_score,
            "异常原因": "; ".join(r.reasons[:2]) if r.reasons else "-"
        })
    
    df = pd.DataFrame(data)
    
    risk_filter = st.multiselect(
        "筛选风险等级",
        ["🔴 high", "🟠 medium", "🟢 low"],
        default=["🔴 high", "🟠 medium", "🟢 low"]
    )
    
    risk_values = [r.split()[-1] for r in risk_filter]
    filtered_df = df[df["风险等级"].str.contains("|".join(risk_values))]
    
    st.dataframe(filtered_df, use_container_width=True, height=400)


def render_trend_analysis(results):
    """渲染趋势分析"""
    scores_data = {
        "GEO分数": [r.geo_score for r in results.results],
        "文本分数": [r.text_score for r in results.results],
        "重复分数": [r.simhash_score for r in results.results],
        "聚类分数": [r.semantic_score for r in results.results]
    }
    
    fig_box = go.Figure()
    colors = ['#667eea', '#764ba2', '#f5576c', '#38ef7d']
    for i, (name, scores) in enumerate(scores_data.items()):
        fig_box.add_trace(go.Box(y=scores, name=name, marker_color=colors[i]))
    
    fig_box.update_layout(title="各维度分数箱线图", height=400)
    st.plotly_chart(fig_box, use_container_width=True)


def render_export(results):
    """渲染导出功能"""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        csv = export_to_csv(results)
        st.download_button(
            "📥 导出CSV",
            csv,
            f"detection_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv",
            use_container_width=True
        )
    
    with col2:
        json_data = export_to_json(results)
        st.download_button(
            "📥 导出JSON",
            json_data,
            f"detection_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "application/json",
            use_container_width=True
        )
    
    with col3:
        if st.button("🔗 生成分享链接", use_container_width=True):
            share_id = generate_share_link(results)
            share_url = f"{API_BASE_URL.replace('/api/v1', '')}/share/{share_id}"
            st.text_input("分享链接", share_url, key="share_link")
            st.success("分享链接已生成")


def export_to_csv(results):
    """导出为CSV"""
    data = []
    for r in results.results:
        data.append({
            "record_id": r.record_id,
            "suspicion_score": r.suspicion_score,
            "risk_level": r.risk_level,
            "is_fake": r.is_fake,
            "geo_score": r.geo_score,
            "text_score": r.text_score,
            "simhash_score": r.simhash_score,
            "semantic_score": r.semantic_score,
            "reasons": "; ".join(r.reasons) if r.reasons else ""
        })
    
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode('utf-8-sig')


def export_to_json(results):
    """导出为JSON"""
    data = {
        "export_time": datetime.now().isoformat(),
        "total_count": results.total_count,
        "fake_count": results.fake_count,
        "normal_count": results.normal_count,
        "results": [
            {
                "record_id": r.record_id,
                "suspicion_score": r.suspicion_score,
                "risk_level": r.risk_level,
                "is_fake": r.is_fake,
                "scores": {
                    "geo_score": r.geo_score,
                    "text_score": r.text_score,
                    "simhash_score": r.simhash_score,
                    "semantic_score": r.semantic_score
                },
                "reasons": r.reasons
            }
            for r in results.results
        ]
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')


def generate_share_link(results):
    """生成分享链接ID"""
    share_id = hashlib.md5(
        f"{datetime.now().isoformat()}{len(results.results)}".encode()
    ).hexdigest()[:12]
    return share_id


def render_api_test_tab():
    """渲染API测试标签页"""
    st.markdown("### 🔌 API接口测试")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 单条检测API")
        
        with st.form("api_single_test"):
            api_device_id = st.text_input("设备ID", "D_API_001")
            api_lat = st.number_input("纬度", value=39.9042, format="%.6f")
            api_lon = st.number_input("经度", value=116.4074, format="%.6f")
            api_text = st.text_area("文本内容")
            
            if st.form_submit_button("发送请求", use_container_width=True):
                payload = {
                    "device_id": api_device_id,
                    "user_id": "USER",
                    "timestamp": int(datetime.now().timestamp()),
                    "geo": {"latitude": api_lat, "longitude": api_lon},
                    "content": {"text": api_text}
                }
                
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/detect/single",
                        json=payload,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        st.json(response.json())
                        st.success("[OK] API调用成功")
                    else:
                        st.error(f"[X] 失败: {response.status_code}")
                except Exception as e:
                    st.error(f"[X] 连接失败: {str(e)}")
    
    with col2:
        st.markdown("#### 服务状态")
        
        if st.button("检查API状态"):
            try:
                response = requests.get(
                    f"{API_BASE_URL.replace('/api/v1', '')}/health",
                    timeout=5
                )
                if response.status_code == 200:
                    st.json(response.json())
                    st.success("[OK] 服务正常")
                else:
                    st.error("[X] 服务异常")
            except Exception as e:
                st.error(f"[X] 无法连接: {str(e)}")


def main():
    """主函数"""
    init_session_state()
    
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <h1 style="font-size: 2.2rem; margin-bottom: 0.5rem;">🗺️ GEO虚假内容检测平台</h1>
        <p style="color: #666; font-size: 1rem;">商用地理信息虚假投喂智能识别系统 v1.1</p>
    </div>
    """, unsafe_allow_html=True)
    
    normal_count, fake_count, high_threshold, medium_threshold = render_sidebar()
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📥 数据输入",
        "🔍 虚假检测",
        "[图表] 检测结果",
        "🔌 API测试"
    ])
    
    with tab1:
        render_data_input_tab(normal_count, fake_count)
    
    with tab2:
        render_detection_tab()
    
    with tab3:
        render_results_tab()
    
    with tab4:
        render_api_test_tab()


if __name__ == "__main__":
    main()
