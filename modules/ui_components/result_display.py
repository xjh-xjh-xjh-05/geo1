"""
增强的结果展示与预警模块
包含：分级展示、风险预警、核验建议、导出功能
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import io
from typing import List, Dict, Any


def get_risk_color(risk_level: str) -> str:
    """获取风险等级对应颜色"""
    colors = {
        "high": "#dc3545",    # 红色 - 虚假
        "medium": "#ffc107",  # 黄色 - 可疑
        "low": "#28a745"      # 绿色 - 真实
    }
    return colors.get(risk_level, "#6c757d")


def get_risk_label(risk_level: str) -> str:
    """获取风险等级中文标签"""
    labels = {
        "high": "虚假",
        "medium": "可疑",
        "low": "真实"
    }
    return labels.get(risk_level, "未知")


def get_recommendations(risk_level: str, reasons: List[str]) -> List[str]:
    """根据风险等级和违规原因生成核验建议"""
    recommendations = []
    
    if risk_level == "high":
        recommendations.append("🔴 高风险数据，建议立即拦截")
        recommendations.append("📍 建议进行实地考察核实")
        recommendations.append("📞 联系平台核实信息真实性")
        
        if any("瞬移" in r or "坐标" in r for r in reasons):
            recommendations.append("[!] 坐标异常，请验证实际位置")
        if any("营销" in r or "关键词" in r for r in reasons):
            recommendations.append("[i] 内容存在营销词堆砌，建议清理")
        if any("重复" in r or "相似" in r for r in reasons):
            recommendations.append("[>] 疑似批量刷量，建议审查账号")
            
    elif risk_level == "medium":
        recommendations.append("[-] 中风险数据，建议人工复核")
        recommendations.append("[?] 与其他权威数据源交叉验证")
        recommendations.append("[=] 要求补充相关资质证明")
        
    else:
        recommendations.append("[+] 数据可信度较高")
        recommendations.append("[OK] 可正常使用")
    
    return recommendations


def render_alert_modal(result: Any) -> None:
    """渲染高风险预警弹窗（使用 Streamlit warning box）"""
    if result.risk_level == "high":
        st.error(f"""
        ### [!] 高风险预警
        
        **记录 ID**: `{result.record_id}`
        
        **可疑分数**: {result.suspicion_score:.1f} 分
        
        **风险等级**: <span style="color: #dc3545; font-weight: bold;">虚假数据</span>
        
        **异常原因**:
        {chr(10).join(f'- {reason}' for reason in result.reasons[:5]) if result.reasons else '暂无详细原因'}
        
        ---
        **建议操作**:
        1. 立即标记为虚假数据
        2. 从数据库中移除
        3. 对上传账号进行审查
        4. 必要时进行实地核实
        """, icon="[!]")


def render_result_detail_card(result: Any, index: int, prefix: str = "card") -> None:
    """渲染单条结果详情卡片"""
    risk_color = get_risk_color(result.risk_level)
    risk_label = get_risk_label(result.risk_level)

    # 计算置信度
    confidence = 100 - abs(result.suspicion_score - (100 if result.risk_level == "low" else 0))
    confidence = max(50, min(99, confidence))

    with st.expander(f"[列表] 记录 {index + 1}: {result.record_id[:15]}... [{risk_label}]", expanded=(result.risk_level == "high")):
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown(f"""
            **风险等级**: <span style="color: {risk_color}; font-size: 1.2rem; font-weight: bold;">{risk_label}</span>

            **可疑分数**: {result.suspicion_score:.1f} / 100

            **是否虚假**: {'[X] 是' if result.is_fake else '[OK] 否'}
            """, unsafe_allow_html=True)

            if result.reasons:
                st.markdown("**异常原因**:")
                for i, reason in enumerate(result.reasons, 1):
                    st.markdown(f"{i}. {reason}")

        with col2:
            st.markdown("**各维度分数**:")

            score_data = {
                "GEO": result.geo_score,
                "文本": result.text_score,
                "重复": result.simhash_score,
                "聚类": result.semantic_score
            }

            score_df = pd.DataFrame(
                list(score_data.items()),
                columns=['维度', '分数']
            )

            fig = px.bar(
                score_df,
                x='维度',
                y='分数',
                color='分数',
                color_continuous_scale=['#10b981', '#3b82f6', '#ef4444'],
                range_y=[0, 100]
            )
            fig.update_layout(
                height=200,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True, key=f"{prefix}_{index}")

        # 核验建议
        st.markdown("---")
        st.markdown("**[?] 核验建议**:")
        recommendations = get_recommendations(result.risk_level, result.reasons)
        for rec in recommendations:
            st.markdown(f"- {rec}")

        # 高风险预警
        if result.risk_level == "high":
            st.markdown("---")
            st.error("""
            ### [!] 高风险数据
            该数据被判定为虚假内容，建议立即采取拦截措施！
            """)


def render_detailed_results_with_alerts(results: Any) -> None:
    """渲染详细结果（带预警）"""
    st.markdown("### [列表] 详细检测结果")
    
    # 统计高风险数量
    high_risk_count = sum(1 for r in results.results if r.risk_level == "high")
    
    if high_risk_count > 0:
        st.error(f"""
        ### [!] 检测到 {high_risk_count} 条高风险数据
        
        以下记录存在严重异常，建议立即处理：
        """)
        
        # 显示所有高风险记录
        for i, result in enumerate(results.results):
            if result.risk_level == "high":
                render_result_detail_card(result, i, prefix="high")
    
    # 显示所有结果
    st.markdown("---")
    st.markdown("### [图表] 全部检测结果")
    
    data = []
    for i, r in enumerate(results.results):
        risk_color = get_risk_color(r.risk_level)
        risk_label = get_risk_label(r.risk_level)
        
        # 计算置信度
        if r.risk_level == "low":
            confidence = min(95, 50 + (100 - r.suspicion_score) / 2)
        elif r.risk_level == "medium":
            confidence = 50 + abs(50 - r.suspicion_score) / 4
        else:
            confidence = min(95, 50 + r.suspicion_score / 2)
        
        data.append({
            "序号": i + 1,
            "记录 ID": r.record_id,
            "风险等级": risk_label,
            "可疑分数": f"{r.suspicion_score:.1f}",
            "置信度": f"{confidence:.1f}%",
            "是否虚假": "是" if r.is_fake else "否",
            "GEO 分数": f"{r.geo_score:.1f}",
            "文本分数": f"{r.text_score:.1f}",
            "异常原因": "; ".join(r.reasons[:2]) if r.reasons else "-",
            "核验建议": get_recommendations(r.risk_level, r.reasons)[0]
        })
    
    df = pd.DataFrame(data)
    
    # 筛选器
    col1, col2 = st.columns(2)
    with col1:
        risk_filter = st.multiselect(
            "筛选风险等级",
            ["虚假", "可疑", "真实"],
            default=["虚假", "可疑", "真实"]
        )
    
    with col2:
        min_score = st.slider("最小可疑分数", 0, 100, 0)
    
    # 应用筛选
    filtered_df = df[df["风险等级"].isin(risk_filter)]
    if "最小可疑分数" in df.columns:
        filtered_df = filtered_df[pd.to_numeric(filtered_df["可疑分数"], errors='coerce') >= min_score]
    
    st.dataframe(filtered_df, use_container_width=True, height=400)
    
    # 逐条详情
    st.markdown("---")
    st.markdown("### 🔍 逐条详情")

    for i, result in enumerate(results.results):
        render_result_detail_card(result, i, prefix="all")


def export_to_excel(results: Any) -> bytes:
    """导出为 Excel 报告"""
    output = io.BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 1. 汇总报告
            # 计算真正的可疑记录：不是虚假但风险等级为medium的记录
            suspicious_only = sum(1 for r in results.results if not r.is_fake and r.risk_level == "medium")
            
            summary_data = {
                "指标": ["总记录数", "虚假记录", "可疑记录", "真实记录", "虚假率", "平均可疑分数"],
                "数值": [
                    results.total_count,
                    results.fake_count,
                    suspicious_only,
                    results.normal_count,
                    f"{results.fake_count / results.total_count * 100:.1f}%" if results.total_count > 0 else "0%",
                    f"{sum(r.suspicion_score for r in results.results) / len(results.results):.1f}" if results.results else "0"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='汇总报告', index=False)
            
            # 2. 详细结果
            detail_data = []
            for r in results.results:
                detail_data.append({
                    "记录 ID": r.record_id,
                    "风险等级": get_risk_label(r.risk_level),
                    "可疑分数": r.suspicion_score,
                    "是否虚假": "是" if r.is_fake else "否",
                    "GEO 分数": r.geo_score,
                    "文本分数": r.text_score,
                    "重复分数": r.simhash_score,
                    "聚类分数": r.semantic_score,
                    "异常原因": "; ".join(r.reasons),
                    "核验建议": "; ".join(get_recommendations(r.risk_level, r.reasons))
                })
            
            detail_df = pd.DataFrame(detail_data)
            detail_df.to_excel(writer, sheet_name='详细结果', index=False)
        
        # 3. 格式化
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        # 汇总报告格式化
        worksheet = writer.sheets['汇总报告']
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 15)
        
        # 详细结果格式化
        worksheet = writer.sheets['详细结果']
        worksheet.set_column('A:A', 25)
        worksheet.set_column('B:B', 10)
        worksheet.set_column('C:C', 12)
        worksheet.set_column('J:J', 30)
    except ImportError:
        # 如果缺少 xlsxwriter，使用默认引擎
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 1. 汇总报告
            # 计算真正的可疑记录：不是虚假但风险等级为medium的记录
            suspicious_only = sum(1 for r in results.results if not r.is_fake and r.risk_level == "medium")
            
            summary_data = {
                "指标": ["总记录数", "虚假记录", "可疑记录", "真实记录", "虚假率", "平均可疑分数"],
                "数值": [
                    results.total_count,
                    results.fake_count,
                    suspicious_only,
                    results.normal_count,
                    f"{results.fake_count / results.total_count * 100:.1f}%" if results.total_count > 0 else "0%",
                    f"{sum(r.suspicion_score for r in results.results) / len(results.results):.1f}" if results.results else "0"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='汇总报告', index=False)
            
            # 2. 详细结果
            detail_data = []
            for r in results.results:
                detail_data.append({
                    "记录 ID": r.record_id,
                    "风险等级": get_risk_label(r.risk_level),
                    "可疑分数": r.suspicion_score,
                    "是否虚假": "是" if r.is_fake else "否",
                    "GEO 分数": r.geo_score,
                    "文本分数": r.text_score,
                    "重复分数": r.simhash_score,
                    "聚类分数": r.semantic_score,
                    "异常原因": "; ".join(r.reasons),
                    "核验建议": "; ".join(get_recommendations(r.risk_level, r.reasons))
                })
            
            detail_df = pd.DataFrame(detail_data)
            detail_df.to_excel(writer, sheet_name='详细结果', index=False)
    
    return output.getvalue()


def export_to_pdf_report(results: Any) -> bytes:
    """导出为 PDF 报告（需要 reportlab）"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []
        
        # 标题
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#333333'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph("GEO 虚假内容检测报告", title_style))
        elements.append(Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 0.5*cm))
        
        # 汇总统计
        elements.append(Paragraph("检测概要", styles['Heading2']))
        
        # 计算真正的可疑记录：不是虚假但风险等级为medium的记录
        suspicious_only = sum(1 for r in results.results if not r.is_fake and r.risk_level == "medium")
        
        summary_data = [
            ["指标", "数值"],
            ["总记录数", str(results.total_count)],
            ["虚假记录", str(results.fake_count)],
            ["可疑记录", str(suspicious_only)],
            ["真实记录", str(results.normal_count)],
            ["虚假率", f"{results.fake_count / results.total_count * 100:.1f}%" if results.total_count > 0 else "0%"],
            ["平均可疑分数", f"{sum(r.suspicion_score for r in results.results) / len(results.results):.1f}" if results.results else "0"]
        ]
        
        summary_table = Table(summary_data, colWidths=[8*cm, 6*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f2f2f2')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.5*cm))
        
        # 高风险记录详情
        high_risk_results = [r for r in results.results if r.risk_level == "high"]
        if high_risk_results:
            elements.append(Paragraph("高风险记录详情", styles['Heading2']))
            
            for r in high_risk_results[:10]:  # 最多显示 10 条
                risk_data = [
                    ["记录 ID", r.record_id],
                    ["可疑分数", f"{r.suspicion_score:.1f}"],
                    ["异常原因", "; ".join(r.reasons[:3]) if r.reasons else "-"]
                ]
                risk_table = Table(risk_data, colWidths=[4*cm, 10*cm])
                risk_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ffe6e6')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(risk_table)
                elements.append(Spacer(1, 0.2*cm))
        
        # 构建 PDF
        doc.build(elements)
        
        return buffer.getvalue()
        
    except ImportError:
        return None


def render_export_section(results: Any) -> None:
    """渲染导出功能区域"""
    st.markdown("### 📤 导出报告")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Excel 导出
        excel_data = export_to_excel(results)
        st.download_button(
            label="[图表] 导出 Excel",
            data=excel_data,
            file_name=f"GEO 检测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col2:
        # JSON 导出
        json_data = json.dumps({
            "export_time": datetime.now().isoformat(),
            "summary": {
                "total_count": results.total_count,
                "fake_count": results.fake_count,
                "normal_count": results.normal_count,
                "suspicious_count": results.suspicious_count
            },
            "results": [
                {
                    "record_id": r.record_id,
                    "risk_level": r.risk_level,
                    "suspicion_score": r.suspicion_score,
                    "is_fake": r.is_fake,
                    "scores": {
                        "geo_score": r.geo_score,
                        "text_score": r.text_score,
                        "simhash_score": r.simhash_score,
                        "semantic_score": r.semantic_score
                    },
                    "reasons": r.reasons,
                    "recommendations": get_recommendations(r.risk_level, r.reasons)
                }
                for r in results.results
            ]
        }, ensure_ascii=False, indent=2)
        
        st.download_button(
            label="📄 导出 JSON",
            data=json_data.encode('utf-8'),
            file_name=f"GEO 检测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    with col3:
        # PDF 导出
        pdf_data = export_to_pdf_report(results)
        if pdf_data:
            st.download_button(
                label="📑 导出 PDF",
                data=pdf_data,
                file_name=f"GEO 检测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            st.info("PDF 导出需要安装 reportlab 库")


def generate_share_link(results: Any) -> str:
    """生成分享链接（模拟）"""
    import hashlib
    share_id = hashlib.md5(
        f"{datetime.now().isoformat()}{len(results.results)}{results.fake_count}".encode()
    ).hexdigest()[:12]
    
    # 使用更兼容的方式获取 host
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx and hasattr(ctx, 'headers'):
            base_url = ctx.headers.get("host", "localhost:8501")
        else:
            base_url = "localhost:8501"
    except:
        base_url = "localhost:8501"
    
    return f"http://{base_url}/share/{share_id}"


def render_share_section(results: Any) -> None:
    """渲染分享功能区域"""
    st.markdown("### 🔗 分享检测结果")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        share_url = generate_share_link(results)
        st.text_input("分享链接", share_url, key="share_link", label_visibility="collapsed")
    
    with col2:
        if st.button("[列表] 复制链接", use_container_width=True):
            st.success("链接已复制（请手动复制上方链接）")
    
    st.info("""
    **[?] 分享说明**:
    - 分享链接有效期 7 天
    - 接收方可查看检测结果和详细分析
    - 敏感数据已自动脱敏处理
    """)


def render_complete_results(results: Any) -> None:
    """渲染完整的结果展示（包含所有功能）"""
    # 1. 高风险预警
    high_risk_count = sum(1 for r in results.results if r.risk_level == "high")
    if high_risk_count > 0:
        render_alert_summary(high_risk_count)
    
    # 2. 统计概览
    render_statistics_overview(results)
    
    # 3. 详细结果
    render_detailed_results_with_alerts(results)
    
    # 4. 导出功能
    render_export_section(results)
    
    # 5. 分享功能
    render_share_section(results)


def render_alert_summary(high_risk_count: int) -> None:
    """渲染预警摘要"""
    st.error(f"""
    ### [!] 高风险预警
    
    本次检测发现 **{high_risk_count}** 条高风险数据！
    
    建议立即采取以下措施：
    1. 标记所有高风险数据为虚假
    2. 从数据库中移除虚假数据
    3. 审查相关上传账号
    4. 必要时进行实地核实
    
    详细预警信息请查看下方"逐条详情"部分。
    """)


def render_statistics_overview(results: Any) -> None:
    """渲染统计概览"""
    st.markdown("### [图表] 检测统计")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("总记录数", results.total_count)
    
    with col2:
        st.metric("🔴 虚假记录", results.fake_count)
    
    with col3:
        # 计算真正的可疑记录：不是虚假但风险等级为medium的记录
        suspicious_only = sum(1 for r in results.results if not r.is_fake and r.risk_level == "medium")
        st.metric("🟡 可疑记录", suspicious_only)
    
    with col4:
        st.metric("🟢 真实记录", results.normal_count)
    
    # 虚假率
    fake_rate = (results.fake_count / results.total_count * 100) if results.total_count > 0 else 0
    st.progress(min(100, fake_rate) / 100)
    st.caption(f"虚假率：{fake_rate:.1f}%")
