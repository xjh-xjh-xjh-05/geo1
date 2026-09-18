"""
结果输出与预警模块
"""
import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import base64


class RiskLevel(str, Enum):
    REAL = "real"
    SUSPICIOUS = "suspicious"
    FAKE = "fake"


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class DetectionOutput:
    poi_id: str
    poi_name: str
    risk_level: RiskLevel
    confidence: float
    score: int
    violations: List[str]
    evidence: List[Dict[str, Any]]
    recommendations: List[str]
    detection_time: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    alert_id: str
    alert_level: AlertLevel
    title: str
    message: str
    poi_data: Dict[str, Any]
    created_at: str
    is_read: bool = False
    actions: List[str] = field(default_factory=list)


class ResultFormatter:
    """
    检测结果格式化器
    """
    
    def __init__(self):
        self.risk_colors = {
            RiskLevel.REAL: "#28a745",
            RiskLevel.SUSPICIOUS: "#ffc107",
            RiskLevel.FAKE: "#dc3545"
        }
        
        self.risk_labels = {
            RiskLevel.REAL: "真实",
            RiskLevel.SUSPICIOUS: "可疑",
            RiskLevel.FAKE: "虚假"
        }
        
        self.score_ranges = {
            RiskLevel.REAL: (80, 100),
            RiskLevel.SUSPICIOUS: (50, 79),
            RiskLevel.FAKE: (0, 49)
        }
    
    def format_result(
        self,
        poi_data: Dict[str, Any],
        detection_result: Dict[str, Any],
        cross_validation: Optional[Dict[str, Any]] = None,
        rule_check: Optional[Dict[str, Any]] = None
    ) -> DetectionOutput:
        """
        格式化检测结果
        """
        poi_id = poi_data.get("id", str(hash(poi_data.get("name", ""))))
        poi_name = poi_data.get("name", "未知POI")
        
        confidence = detection_result.get("confidence", 0.0)
        label = detection_result.get("label", "unknown")
        
        risk_level = self._map_label_to_risk(label)
        score = self._calculate_score(confidence, risk_level, cross_validation, rule_check)
        
        violations = self._collect_violations(
            detection_result, cross_validation, rule_check
        )
        
        evidence = self._collect_evidence(
            poi_data, detection_result, cross_validation, rule_check
        )
        
        recommendations = self._generate_recommendations(
            risk_level, violations, cross_validation
        )
        
        details = {
            "original_data": poi_data,
            "detection_details": detection_result,
            "cross_validation": cross_validation,
            "rule_check": rule_check
        }
        
        return DetectionOutput(
            poi_id=poi_id,
            poi_name=poi_name,
            risk_level=risk_level,
            confidence=confidence,
            score=score,
            violations=violations,
            evidence=evidence,
            recommendations=recommendations,
            detection_time=datetime.now().isoformat(),
            details=details
        )
    
    def _map_label_to_risk(self, label: str) -> RiskLevel:
        mapping = {
            "real": RiskLevel.REAL,
            "suspicious": RiskLevel.SUSPICIOUS,
            "fake": RiskLevel.FAKE,
            "unknown": RiskLevel.SUSPICIOUS
        }
        return mapping.get(label, RiskLevel.SUSPICIOUS)
    
    def _calculate_score(
        self,
        confidence: float,
        risk_level: RiskLevel,
        cross_validation: Optional[Dict[str, Any]],
        rule_check: Optional[Dict[str, Any]]
    ) -> int:
        """
        计算综合评分
        """
        base_score = int(confidence * 100)
        
        if risk_level == RiskLevel.FAKE:
            base_score = min(base_score, 49)
        elif risk_level == RiskLevel.SUSPICIOUS:
            base_score = min(max(base_score, 50), 79)
        else:
            base_score = max(base_score, 80)
        
        if cross_validation:
            platform_count = cross_validation.get("platform_count", 0)
            if platform_count >= 3:
                base_score = min(base_score + 5, 100)
            elif platform_count == 0:
                base_score = max(base_score - 10, 0)
        
        if rule_check:
            violation_count = len(rule_check.get("violations", []))
            base_score = max(base_score - violation_count * 5, 0)
        
        return base_score
    
    def _collect_violations(
        self,
        detection_result: Dict[str, Any],
        cross_validation: Optional[Dict[str, Any]],
        rule_check: Optional[Dict[str, Any]]
    ) -> List[str]:
        """
        收集违规项
        """
        violations = []
        
        if detection_result.get("risk_factors"):
            violations.extend(detection_result["risk_factors"])
        
        if cross_validation:
            if cross_validation.get("risk_reasons"):
                violations.extend(cross_validation["risk_reasons"])
            
            if cross_validation.get("platform_count", 0) == 0:
                violations.append("所有平台均未找到匹配POI")
        
        if rule_check:
            if rule_check.get("violations"):
                violations.extend(rule_check["violations"])
        
        return list(set(violations))
    
    def _collect_evidence(
        self,
        poi_data: Dict[str, Any],
        detection_result: Dict[str, Any],
        cross_validation: Optional[Dict[str, Any]],
        rule_check: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        收集核验依据
        """
        evidence = []
        
        evidence.append({
            "type": "ai_detection",
            "source": "AI模型",
            "description": f"AI模型检测结果: {detection_result.get('label', 'unknown')}",
            "confidence": detection_result.get("confidence", 0.0),
            "timestamp": datetime.now().isoformat()
        })
        
        if cross_validation and cross_validation.get("platform_matches"):
            for platform, match in cross_validation["platform_matches"].items():
                evidence.append({
                    "type": "cross_validation",
                    "source": platform,
                    "description": f"平台匹配结果: {'找到' if match.get('found') else '未找到'}",
                    "similarity": match.get("similarity_score", 0.0),
                    "timestamp": datetime.now().isoformat()
                })
        
        if rule_check and rule_check.get("violations"):
            evidence.append({
                "type": "rule_check",
                "source": "规则引擎",
                "description": f"发现{len(rule_check['violations'])}项违规",
                "violations": rule_check["violations"],
                "timestamp": datetime.now().isoformat()
            })
        
        return evidence
    
    def _generate_recommendations(
        self,
        risk_level: RiskLevel,
        violations: List[str],
        cross_validation: Optional[Dict[str, Any]]
    ) -> List[str]:
        """
        生成核验建议
        """
        recommendations = []
        
        if risk_level == RiskLevel.FAKE:
            recommendations.append("建议标记为虚假数据并从数据库中移除")
            recommendations.append("建议对上传账号进行审查")
            recommendations.append("建议实地考察核实")
        elif risk_level == RiskLevel.SUSPICIOUS:
            recommendations.append("建议进一步核实数据来源")
            if cross_validation and cross_validation.get("platform_count", 0) < 2:
                recommendations.append("建议与其他权威数据源交叉验证")
            recommendations.append("建议联系平台核实信息")
        else:
            recommendations.append("数据可信度较高，可正常使用")
        
        if any("营销" in v for v in violations):
            recommendations.append("建议清理营销性描述")
        
        if any("坐标" in v for v in violations):
            recommendations.append("建议核实坐标准确性")
        
        return recommendations
    
    def to_dict(self, output: DetectionOutput) -> Dict[str, Any]:
        """
        转换为字典格式
        """
        return {
            "poi_id": output.poi_id,
            "poi_name": output.poi_name,
            "risk_level": output.risk_level.value,
            "risk_label": self.risk_labels[output.risk_level],
            "risk_color": self.risk_colors[output.risk_level],
            "confidence": output.confidence,
            "score": output.score,
            "violations": output.violations,
            "evidence": output.evidence,
            "recommendations": output.recommendations,
            "detection_time": output.detection_time,
            "details": output.details
        }


class AlertManager:
    """
    预警管理器
    """
    
    def __init__(self):
        self.alerts: List[Alert] = []
        self.alert_handlers: List[callable] = []
        self.thresholds = {
            "fake_count_per_hour": 10,
            "suspicious_ratio": 0.3,
            "single_platform_only": True
        }
    
    def check_and_alert(
        self,
        output: DetectionOutput,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Alert]:
        """
        检查并生成预警
        """
        alert = None
        
        if output.risk_level == RiskLevel.FAKE:
            alert = self._create_fake_alert(output, context)
        elif output.risk_level == RiskLevel.SUSPICIOUS:
            if output.confidence < 0.4:
                alert = self._create_suspicious_alert(output, context)
        
        if alert:
            self.alerts.append(alert)
            self._notify_handlers(alert)
        
        return alert
    
    def _create_fake_alert(
        self,
        output: DetectionOutput,
        context: Optional[Dict[str, Any]]
    ) -> Alert:
        """
        创建虚假数据预警
        """
        return Alert(
            alert_id=f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}_{output.poi_id}",
            alert_level=AlertLevel.CRITICAL,
            title="检测到虚假POI数据",
            message=f"POI '{output.poi_name}' 被判定为虚假数据，置信度: {output.confidence:.1%}",
            poi_data=output.details.get("original_data", {}),
            created_at=datetime.now().isoformat(),
            actions=[
                "标记为虚假",
                "移除数据",
                "审查上传账号",
                "实地核实"
            ]
        )
    
    def _create_suspicious_alert(
        self,
        output: DetectionOutput,
        context: Optional[Dict[str, Any]]
    ) -> Alert:
        """
        创建可疑数据预警
        """
        return Alert(
            alert_id=f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}_{output.poi_id}",
            alert_level=AlertLevel.WARNING,
            title="检测到可疑POI数据",
            message=f"POI '{output.poi_name}' 存在可疑特征，置信度: {output.confidence:.1%}",
            poi_data=output.details.get("original_data", {}),
            created_at=datetime.now().isoformat(),
            actions=[
                "进一步核实",
                "交叉验证",
                "联系平台"
            ]
        )
    
    def add_handler(self, handler: callable):
        """
        添加预警处理器
        """
        self.alert_handlers.append(handler)
    
    def _notify_handlers(self, alert: Alert):
        """
        通知所有处理器
        """
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                pass
    
    def get_alerts(
        self,
        level: Optional[AlertLevel] = None,
        unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取预警列表
        """
        alerts = self.alerts
        
        if level:
            alerts = [a for a in alerts if a.alert_level == level]
        
        if unread_only:
            alerts = [a for a in alerts if not a.is_read]
        
        return [self._alert_to_dict(a) for a in alerts]
    
    def mark_read(self, alert_id: str) -> bool:
        """
        标记预警为已读
        """
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.is_read = True
                return True
        return False
    
    def _alert_to_dict(self, alert: Alert) -> Dict[str, Any]:
        return {
            "alert_id": alert.alert_id,
            "alert_level": alert.alert_level.value,
            "title": alert.title,
            "message": alert.message,
            "poi_data": alert.poi_data,
            "created_at": alert.created_at,
            "is_read": alert.is_read,
            "actions": alert.actions
        }


class ReportGenerator:
    """
    报告生成器
    """
    
    def __init__(self):
        self.formatter = ResultFormatter()
    
    def generate_summary_report(
        self,
        results: List[DetectionOutput],
        title: str = "GEO虚假内容检测报告"
    ) -> Dict[str, Any]:
        """
        生成汇总报告
        """
        total = len(results)
        if total == 0:
            return {"error": "无检测数据"}
        
        real_count = sum(1 for r in results if r.risk_level == RiskLevel.REAL)
        suspicious_count = sum(1 for r in results if r.risk_level == RiskLevel.SUSPICIOUS)
        fake_count = sum(1 for r in results if r.risk_level == RiskLevel.FAKE)
        
        avg_confidence = sum(r.confidence for r in results) / total
        avg_score = sum(r.score for r in results) / total
        
        all_violations = []
        for r in results:
            all_violations.extend(r.violations)
        
        violation_stats = {}
        for v in all_violations:
            violation_stats[v] = violation_stats.get(v, 0) + 1
        
        top_violations = sorted(
            violation_stats.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "title": title,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_count": total,
                "real_count": real_count,
                "suspicious_count": suspicious_count,
                "fake_count": fake_count,
                "real_ratio": real_count / total,
                "suspicious_ratio": suspicious_count / total,
                "fake_ratio": fake_count / total
            },
            "statistics": {
                "average_confidence": avg_confidence,
                "average_score": avg_score,
                "high_risk_count": fake_count + suspicious_count
            },
            "violation_analysis": {
                "total_violations": len(all_violations),
                "unique_violations": len(violation_stats),
                "top_violations": [
                    {"violation": v, "count": c} for v, c in top_violations
                ]
            },
            "recommendations": self._generate_summary_recommendations(
                real_count, suspicious_count, fake_count, total
            )
        }
    
    def _generate_summary_recommendations(
        self,
        real_count: int,
        suspicious_count: int,
        fake_count: int,
        total: int
    ) -> List[str]:
        """
        生成汇总建议
        """
        recommendations = []
        
        fake_ratio = fake_count / total if total > 0 else 0
        suspicious_ratio = suspicious_count / total if total > 0 else 0
        
        if fake_ratio > 0.2:
            recommendations.append(f"虚假数据比例较高({fake_ratio:.1%})，建议加强数据审核")
        
        if suspicious_ratio > 0.3:
            recommendations.append(f"可疑数据比例较高({suspicious_ratio:.1%})，建议进行人工复核")
        
        if fake_count > 0:
            recommendations.append(f"发现{fake_count}条虚假数据，建议及时清理")
        
        if suspicious_count > 0:
            recommendations.append(f"发现{suspicious_count}条可疑数据，建议进一步核实")
        
        if not recommendations:
            recommendations.append("数据质量良好，建议继续保持审核标准")
        
        return recommendations
    
    def export_to_json(
        self,
        results: List[DetectionOutput],
        filepath: str
    ) -> bool:
        """
        导出为JSON文件
        """
        try:
            data = {
                "export_time": datetime.now().isoformat(),
                "total_count": len(results),
                "results": [self.formatter.to_dict(r) for r in results]
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            return False
    
    def export_to_csv(
        self,
        results: List[DetectionOutput],
        filepath: str
    ) -> bool:
        """
        导出为CSV文件
        """
        try:
            import csv
            
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                
                writer.writerow([
                    "POI ID", "POI名称", "风险等级", "置信度",
                    "评分", "违规项", "检测时间"
                ])
                
                for r in results:
                    writer.writerow([
                        r.poi_id,
                        r.poi_name,
                        r.risk_level.value,
                        f"{r.confidence:.2%}",
                        r.score,
                        "; ".join(r.violations[:3]),
                        r.detection_time
                    ])
            
            return True
        except Exception as e:
            return False
    
    def generate_pdf_report(
        self,
        results: List[DetectionOutput],
        filepath: str
    ) -> bool:
        """
        生成PDF报告（需要reportlab库）
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            
            doc = SimpleDocTemplate(filepath, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []
            
            elements.append(Paragraph("GEO虚假内容检测报告", styles['Title']))
            elements.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
            elements.append(Spacer(1, 20))
            
            summary = self.generate_summary_report(results)
            elements.append(Paragraph("检测概要", styles['Heading2']))
            
            summary_data = [
                ["指标", "数值"],
                ["总检测数", str(summary["summary"]["total_count"])],
                ["真实数据", str(summary["summary"]["real_count"])],
                ["可疑数据", str(summary["summary"]["suspicious_count"])],
                ["虚假数据", str(summary["summary"]["fake_count"])],
                ["平均置信度", f"{summary['statistics']['average_confidence']:.2%}"],
            ]
            
            summary_table = Table(summary_data, colWidths=[200, 100])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(summary_table)
            
            doc.build(elements)
            return True
            
        except ImportError:
            return False
        except Exception as e:
            return False


class ResultOutputModule:
    """
    结果输出模块主类
    """
    
    def __init__(self):
        self.formatter = ResultFormatter()
        self.alert_manager = AlertManager()
        self.report_generator = ReportGenerator()
    
    def process_detection_result(
        self,
        poi_data: Dict[str, Any],
        detection_result: Dict[str, Any],
        cross_validation: Optional[Dict[str, Any]] = None,
        rule_check: Optional[Dict[str, Any]] = None,
        generate_alert: bool = True
    ) -> Dict[str, Any]:
        """
        处理检测结果并生成输出
        """
        output = self.formatter.format_result(
            poi_data, detection_result, cross_validation, rule_check
        )
        
        result = self.formatter.to_dict(output)
        
        if generate_alert:
            alert = self.alert_manager.check_and_alert(output)
            if alert:
                result["alert"] = self.alert_manager._alert_to_dict(alert)
        
        return result
    
    def batch_process(
        self,
        poi_list: List[Dict[str, Any]],
        detection_results: List[Dict[str, Any]],
        cross_validations: Optional[List[Dict[str, Any]]] = None,
        rule_checks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        批量处理检测结果
        """
        results = []
        
        for i, (poi, detection) in enumerate(zip(poi_list, detection_results)):
            cv = cross_validations[i] if cross_validations and i < len(cross_validations) else None
            rc = rule_checks[i] if rule_checks and i < len(rule_checks) else None
            
            result = self.process_detection_result(poi, detection, cv, rc)
            results.append(result)
        
        return results
    
    def get_alerts(
        self,
        level: Optional[str] = None,
        unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取预警列表
        """
        alert_level = AlertLevel(level) if level else None
        return self.alert_manager.get_alerts(alert_level, unread_only)
    
    def generate_report(
        self,
        results: List[Dict[str, Any]],
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        生成检测报告
        """
        outputs = []
        for r in results:
            output = DetectionOutput(
                poi_id=r["poi_id"],
                poi_name=r["poi_name"],
                risk_level=RiskLevel(r["risk_level"]),
                confidence=r["confidence"],
                score=r["score"],
                violations=r["violations"],
                evidence=r["evidence"],
                recommendations=r["recommendations"],
                detection_time=r["detection_time"]
            )
            outputs.append(output)
        
        report = self.report_generator.generate_summary_report(outputs)
        
        if format == "json":
            report["format"] = "json"
        elif format == "csv":
            report["format"] = "csv"
        elif format == "pdf":
            report["format"] = "pdf"
        
        return report
