"""
地图可视化组件
=============

提供交互式地图展示功能，支持POI标记、热力图、风险等级着色等。
"""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class MapLayerType(str, Enum):
    MARKERS = "markers"
    HEATMAP = "heatmap"
    CLUSTERS = "clusters"
    POLYGONS = "polygons"
    POLYLINES = "polylines"


class MarkerColor(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    BLUE = "blue"
    GRAY = "gray"


@dataclass
class MapMarker:
    """地图标记"""
    lat: float
    lon: float
    title: str
    popup: str = ""
    color: MarkerColor = MarkerColor.BLUE
    icon: str = "info-sign"
    draggable: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MapPolygon:
    """地图多边形"""
    coordinates: List[Tuple[float, float]]
    color: str = "#3388ff"
    fill_color: str = "#3388ff"
    fill_opacity: float = 0.2
    weight: int = 2
    popup: str = ""


@dataclass
class HeatmapPoint:
    """热力图点"""
    lat: float
    lon: float
    intensity: float = 1.0


@dataclass
class MapConfig:
    """地图配置"""
    center_lat: float = 35.8617
    center_lon: float = 104.1954
    zoom: int = 5
    min_zoom: int = 3
    max_zoom: int = 18
    tile_url: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    tile_attribution: str = "© OpenStreetMap contributors"


class MapVisualizer:
    """
    地图可视化器
    """

    def __init__(self, config: Optional[MapConfig] = None):
        self.config = config or MapConfig()
        self.markers: List[MapMarker] = []
        self.polygons: List[MapPolygon] = []
        self.heatmap_points: List[HeatmapPoint] = []
        self.layers: Dict[str, List[Any]] = {}

    def add_marker(self, marker: MapMarker):
        """添加标记"""
        self.markers.append(marker)

    def add_markers_from_detection_results(
        self,
        results: List[Dict[str, Any]],
        risk_colors: Optional[Dict[str, str]] = None
    ):
        """
        从检测结果添加标记

        Args:
            results: 检测结果列表，每项需包含 lat, lon, record_id, risk_level 等字段
            risk_colors: 风险等级颜色映射
        """
        if risk_colors is None:
            risk_colors = {
                "high": "red",
                "medium": "yellow",
                "low": "green",
                "unknown": "gray"
            }

        for result in results:
            lat = result.get("lat")
            lon = result.get("lon")

            if lat is not None and lon is not None:
                risk_level = result.get("risk_level", "unknown")
                color = risk_colors.get(risk_level, "gray")

                popup_content = self._create_popup_content(result)

                marker = MapMarker(
                    lat=lat,
                    lon=lon,
                    title=result.get("record_id", "未知POI"),
                    popup=popup_content,
                    color=MarkerColor(color),
                    metadata={
                        "record_id": result.get("record_id"),
                        "risk_level": risk_level,
                        "suspicion_score": result.get("suspicion_score"),
                        "is_fake": result.get("is_fake")
                    }
                )
                self.add_marker(marker)

    def add_heatmap_from_results(
        self,
        results: List[Dict[str, Any]]
    ):
        """
        从检测结果添加热力图数据

        Args:
            results: 检测结果列表，每项需包含 lat, lon, risk_level, is_fake 等字段
        """
        for result in results:
            lat = result.get("lat")
            lon = result.get("lon")

            if lat is not None and lon is not None:
                risk_level = result.get("risk_level", "unknown")
                is_fake = result.get("is_fake", False)

                if is_fake or risk_level == "high":
                    intensity = 1.0
                elif risk_level == "medium":
                    intensity = 0.6
                else:
                    intensity = 0.2

                self.heatmap_points.append(HeatmapPoint(
                    lat=lat,
                    lon=lon,
                    intensity=intensity
                ))

    def add_risk_area_polygon(
        self,
        coordinates: List[Tuple[float, float]],
        risk_level: str = "high",
        label: str = ""
    ):
        """
        添加风险区域多边形

        Args:
            coordinates: 坐标列表
            risk_level: 风险等级
            label: 区域标签
        """
        color_map = {
            "high": {"color": "#dc3545", "fill": "#dc3545"},
            "medium": {"color": "#ffc107", "fill": "#ffc107"},
            "low": {"color": "#28a745", "fill": "#28a745"}
        }

        colors = color_map.get(risk_level, color_map["medium"])

        polygon = MapPolygon(
            coordinates=coordinates,
            color=colors["color"],
            fill_color=colors["fill"],
            fill_opacity=0.2,
            popup=label or f"风险区域: {risk_level}"
        )
        self.polygons.append(polygon)

    def generate_html(
        self,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成交互式地图HTML

        Args:
            output_path: 输出文件路径

        Returns:
            HTML字符串
        """
        markers_js = self._generate_markers_js()
        heatmap_js = self._generate_heatmap_js()
        polygons_js = self._generate_polygons_js()

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEO虚假内容检测 - 地图可视化</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        #map {{
            width: 100%;
            height: 100vh;
        }}
        .info-panel {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 1000;
            max-width: 300px;
        }}
        .legend {{
            position: absolute;
            bottom: 30px;
            left: 10px;
            background: white;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 1000;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 10px;
        }}
        .popup-content {{
            max-width: 250px;
        }}
        .popup-content h3 {{
            margin: 0 0 10px 0;
            color: #333;
        }}
        .popup-content .risk-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            color: white;
            font-size: 12px;
            margin-bottom: 10px;
        }}
        .popup-content .info-row {{
            margin: 5px 0;
            font-size: 13px;
        }}
        .popup-content .info-label {{
            color: #666;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="info-panel">
        <h3 style="margin: 0 0 10px 0; color: #333;">GEO虚假检测</h3>
        <div id="stats">加载中...</div>
    </div>

    <div class="legend">
        <strong>风险等级</strong>
        <div class="legend-item">
            <div class="legend-color" style="background: #28a745;"></div>
            <span>真实</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #ffc107;"></div>
            <span>可疑</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #dc3545;"></div>
            <span>虚假</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #6c757d;"></div>
            <span>未知</span>
        </div>
    </div>

    <script>
        // 初始化地图
        var map = L.map('map').setView([{self.config.center_lat}, {self.config.center_lon}], {self.config.zoom});

        // 添加底图
        L.tileLayer('{self.config.tile_url}', {{
            attribution: '{self.config.tile_attribution}',
            maxZoom: {self.config.max_zoom}
        }}).addTo(map);

        // 标记数据
        var markers = {markers_js};

        // 热力图数据
        var heatmapData = {heatmap_js};

        // 多边形数据
        var polygons = {polygons_js};

        // 添加标记
        var markerCluster = L.markerClusterGroup();
        markers.forEach(function(marker) {{
            var icon = L.AwesomeMarkers ? L.AwesomeMarkers.icon({{
                icon: marker.icon,
                markerColor: marker.color,
                prefix: 'fa'
            }}) : L.circleMarker({{
                radius: 8,
                fillColor: marker.color,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            }});

            var m = L.marker([marker.lat, marker.lon], {{icon: icon}});
            if (marker.popup) {{
                m.bindPopup(marker.popup, {{maxWidth: 300}});
            }}
            markerCluster.addLayer(m);
        }});
        map.addLayer(markerCluster);

        // 添加热力图
        if (heatmapData.length > 0) {{
            L.heatLayer(heatmapData, {{
                radius: 25,
                blur: 15,
                maxZoom: 17,
                max: 1.0,
                gradient: {{
                    0.2: '#0000ff',
                    0.4: '#00ffff',
                    0.6: '#00ff00',
                    0.8: '#ffff00',
                    1.0: '#ff0000'
                }}
            }}).addTo(map);
        }}

        // 添加多边形
        polygons.forEach(function(polygon) {{
            L.polygon(polygon.coordinates, {{
                color: polygon.color,
                fillColor: polygon.fill_color,
                fillOpacity: polygon.fill_opacity,
                weight: polygon.weight
            }}).addTo(map).bindPopup(polygon.popup);
        }});

        // 更新统计信息
        var statsHtml = '<div style="font-size: 14px;">';
        statsHtml += '<p>标记数量: ' + markers.length + '</p>';
        statsHtml += '<p>热力点: ' + heatmapData.length + '</p>';
        statsHtml += '<p>区域: ' + polygons.length + '</p>';
        statsHtml += '</div>';
        document.getElementById('stats').innerHTML = statsHtml;
    </script>
</body>
</html>"""

        if output_path:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)

        return html

    def generate_streamlit_map(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成Streamlit地图数据

        Args:
            results: 检测结果列表，每项需包含 lat, lon 等字段

        Returns:
            适用于Streamlit的地图数据
        """
        markers_data = []
        heatmap_data = []

        risk_colors = {
            "high": "red",
            "medium": "yellow",
            "low": "green",
            "unknown": "gray"
        }

        for result in results:
            lat = result.get("lat")
            lon = result.get("lon")

            if lat is not None and lon is not None:
                risk_level = result.get("risk_level", "unknown")
                is_fake = result.get("is_fake", False)
                suspicion_score = result.get("suspicion_score", 0)

                markers_data.append({
                    "lat": lat,
                    "lon": lon,
                    "name": result.get("record_id", "未知"),
                    "risk_level": risk_level,
                    "color": risk_colors.get(risk_level, "gray"),
                    "suspicion_score": suspicion_score,
                    "is_fake": is_fake,
                    "popup": self._create_popup_content(result)
                })

                if is_fake or risk_level == "high":
                    intensity = 1.0
                elif risk_level == "medium":
                    intensity = 0.6
                else:
                    intensity = 0.2
                heatmap_data.append([lat, lon, intensity])

        return {
            "center": [self.config.center_lat, self.config.center_lon],
            "zoom": self.config.zoom,
            "markers": markers_data,
            "heatmap": heatmap_data
        }

    def _create_popup_content(self, result: Dict[str, Any]) -> str:
        """创建弹出窗口内容"""
        risk_level = result.get("risk_level", "unknown")
        suspicion_score = result.get("suspicion_score", 0)
        is_fake = result.get("is_fake", False)
        record_id = result.get("record_id", "未知")

        risk_labels = {
            "high": "虚假",
            "medium": "可疑",
            "low": "真实",
            "unknown": "未知"
        }

        risk_colors = {
            "high": "#dc3545",
            "medium": "#ffc107",
            "low": "#28a745",
            "unknown": "#6c757d"
        }

        fake_label = "是" if is_fake else "否"

        html = f"""
        <div class="popup-content">
            <h3>{record_id}</h3>
            <span class="risk-badge" style="background: {risk_colors.get(risk_level, '#6c757d')};">
                {risk_labels.get(risk_level, '未知')}
            </span>
            <div class="info-row">
                <span class="info-label">可疑分数:</span>
                <span>{suspicion_score:.1f}/100</span>
            </div>
            <div class="info-row">
                <span class="info-label">是否虚假:</span>
                <span>{fake_label}</span>
            </div>
        </div>
        """
        return html

    def _generate_markers_js(self) -> str:
        """生成标记JavaScript数据"""
        markers_data = []
        for marker in self.markers:
            markers_data.append({
                "lat": marker.lat,
                "lon": marker.lon,
                "title": marker.title,
                "popup": marker.popup,
                "color": marker.color.value,
                "icon": marker.icon,
                "draggable": marker.draggable
            })
        return json.dumps(markers_data, ensure_ascii=False)

    def _generate_heatmap_js(self) -> str:
        """生成热力图JavaScript数据"""
        heatmap_data = [[p.lat, p.lon, p.intensity] for p in self.heatmap_points]
        return json.dumps(heatmap_data)

    def _generate_polygons_js(self) -> str:
        """生成多边形JavaScript数据"""
        polygons_data = []
        for polygon in self.polygons:
            polygons_data.append({
                "coordinates": polygon.coordinates,
                "color": polygon.color,
                "fill_color": polygon.fill_color,
                "fill_opacity": polygon.fill_opacity,
                "weight": polygon.weight,
                "popup": polygon.popup
            })
        return json.dumps(polygons_data, ensure_ascii=False)

    def clear(self):
        """清除所有数据"""
        self.markers.clear()
        self.polygons.clear()
        self.heatmap_points.clear()
        self.layers.clear()


def create_map_from_results(
    results: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    show_heatmap: bool = True,
    show_markers: bool = True
) -> str:
    """
    从检测结果创建地图

    Args:
        results: 检测结果列表，每项需包含 lat, lon 等字段
        output_path: 输出路径
        show_heatmap: 是否显示热力图
        show_markers: 是否显示标记

    Returns:
        HTML字符串
    """
    visualizer = MapVisualizer()

    if show_markers:
        visualizer.add_markers_from_detection_results(results)

    if show_heatmap:
        visualizer.add_heatmap_from_results(results)

    return visualizer.generate_html(output_path)
