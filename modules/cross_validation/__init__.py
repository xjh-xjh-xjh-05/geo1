"""
多源交叉核验模块
"""
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib
import math


@dataclass
class CrossValidationResult:
    is_valid: bool
    confidence: float
    platform_matches: Dict[str, Any]
    risk_level: str
    risk_reasons: List[str]
    recommendations: List[str]


@dataclass
class PlatformMatch:
    platform: str
    found: bool
    similarity_score: float
    matched_data: Dict[str, Any]
    differences: List[Dict[str, Any]]


class MultiSourceValidator:
    """
    多源交叉核验器
    支持与多个地图平台进行数据比对
    """
    
    def __init__(self):
        self.platforms = {
            "amap": {
                "name": "高德地图",
                "api_url": "https://restapi.amap.com/v3",
                "api_key_env": "AMAP_API_KEY",
                "enabled": True
            },
            "baidu": {
                "name": "百度地图",
                "api_url": "https://api.map.baidu.com",
                "api_key_env": "BAIDU_MAP_API_KEY",
                "enabled": True
            },
            "tencent": {
                "name": "腾讯地图",
                "api_url": "https://apis.map.qq.com",
                "api_key_env": "TENCENT_MAP_API_KEY",
                "enabled": True
            },
            "osm": {
                "name": "OpenStreetMap",
                "api_url": "https://nominatim.openstreetmap.org",
                "api_key_env": None,
                "enabled": True
            },
            "tianditu": {
                "name": "天地图",
                "api_url": "http://api.tianditu.gov.cn",
                "api_key_env": "TIANDITU_API_KEY",
                "enabled": False
            }
        }
        
        self.similarity_thresholds = {
            "name": 0.8,
            "address": 0.7,
            "coordinate": 500,
            "category": 0.6
        }
    
    async def validate(self, poi_data: Dict[str, Any]) -> CrossValidationResult:
        """
        执行多源交叉核验
        """
        platform_matches = {}
        risk_reasons = []
        recommendations = []
        
        tasks = []
        for platform_id, platform_config in self.platforms.items():
            if platform_config["enabled"]:
                tasks.append(self._query_platform(platform_id, platform_config, poi_data))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for platform_id, result in zip(self.platforms.keys(), results):
                if isinstance(result, Exception):
                    platform_matches[platform_id] = PlatformMatch(
                        platform=platform_id,
                        found=False,
                        similarity_score=0.0,
                        matched_data={},
                        differences=[{"error": str(result)}]
                    )
                else:
                    platform_matches[platform_id] = result
        
        match_count = sum(1 for m in platform_matches.values() if m.found)
        total_platforms = len([p for p in self.platforms.values() if p["enabled"]])
        
        if match_count == 0:
            risk_reasons.append("所有平台均未找到匹配POI，可能是虚构数据")
            risk_level = "high"
            recommendations.append("建议实地考察核实")
        elif match_count == 1:
            risk_reasons.append("仅单个平台存在记录，存在虚假风险")
            risk_level = "medium"
            recommendations.append("建议与其他权威数据源交叉验证")
        else:
            consistency_issues = self._check_consistency(platform_matches, poi_data)
            risk_reasons.extend(consistency_issues)
            
            if len(consistency_issues) > 2:
                risk_level = "medium"
            elif len(consistency_issues) > 0:
                risk_level = "low"
            else:
                risk_level = "low"
        
        confidence = self._calculate_confidence(platform_matches, match_count, total_platforms)
        
        return CrossValidationResult(
            is_valid=risk_level != "high",
            confidence=confidence,
            platform_matches={k: self._match_to_dict(v) for k, v in platform_matches.items()},
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            recommendations=recommendations
        )
    
    async def _query_platform(
        self, 
        platform_id: str, 
        platform_config: Dict[str, Any],
        poi_data: Dict[str, Any]
    ) -> PlatformMatch:
        """
        查询单个平台
        """
        try:
            if platform_id == "amap":
                return await self._query_amap(platform_config, poi_data)
            elif platform_id == "baidu":
                return await self._query_baidu(platform_config, poi_data)
            elif platform_id == "osm":
                return await self._query_osm(platform_config, poi_data)
            else:
                return PlatformMatch(
                    platform=platform_id,
                    found=False,
                    similarity_score=0.0,
                    matched_data={},
                    differences=[{"error": "平台暂不支持"}]
                )
        except Exception as e:
            return PlatformMatch(
                platform=platform_id,
                found=False,
                similarity_score=0.0,
                matched_data={},
                differences=[{"error": str(e)}]
            )
    
    async def _query_amap(
        self, 
        config: Dict[str, Any], 
        poi_data: Dict[str, Any]
    ) -> PlatformMatch:
        """
        查询高德地图API
        """
        return PlatformMatch(
            platform="amap",
            found=False,
            similarity_score=0.0,
            matched_data={},
            differences=[{"note": "高德地图API需要配置API Key"}]
        )
    
    async def _query_baidu(
        self, 
        config: Dict[str, Any], 
        poi_data: Dict[str, Any]
    ) -> PlatformMatch:
        """
        查询百度地图API
        """
        return PlatformMatch(
            platform="baidu",
            found=False,
            similarity_score=0.0,
            matched_data={},
            differences=[{"note": "百度地图API需要配置API Key"}]
        )
    
    async def _query_osm(
        self, 
        config: Dict[str, Any], 
        poi_data: Dict[str, Any]
    ) -> PlatformMatch:
        """
        查询OpenStreetMap
        """
        lat = poi_data.get("latitude")
        lon = poi_data.get("longitude")
        name = poi_data.get("name", "")
        
        if not lat or not lon:
            return PlatformMatch(
                platform="osm",
                found=False,
                similarity_score=0.0,
                matched_data={},
                differences=[{"error": "缺少坐标信息"}]
            )
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{config['api_url']}/reverse"
                params = {
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "addressdetails": 1
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get("display_name"):
                            similarity = self._calculate_name_similarity(
                                name, 
                                data.get("display_name", "")
                            )
                            
                            return PlatformMatch(
                                platform="osm",
                                found=True,
                                similarity_score=similarity,
                                matched_data={
                                    "display_name": data.get("display_name"),
                                    "type": data.get("type"),
                                    "address": data.get("address", {})
                                },
                                differences=[]
                            )
        except Exception as e:
            pass
        
        return PlatformMatch(
            platform="osm",
            found=False,
            similarity_score=0.0,
            matched_data={},
            differences=[]
        )
    
    def _check_consistency(
        self, 
        platform_matches: Dict[str, PlatformMatch],
        original_data: Dict[str, Any]
    ) -> List[str]:
        """
        检查多平台数据一致性
        """
        issues = []
        
        found_matches = [m for m in platform_matches.values() if m.found]
        
        if len(found_matches) < 2:
            return issues
        
        coordinates = []
        for match in found_matches:
            if match.matched_data.get("latitude") and match.matched_data.get("longitude"):
                coordinates.append((
                    match.matched_data["latitude"],
                    match.matched_data["longitude"]
                ))
        
        if len(coordinates) >= 2:
            max_distance = 0
            for i in range(len(coordinates)):
                for j in range(i + 1, len(coordinates)):
                    dist = self._haversine_distance(
                        coordinates[i][0], coordinates[i][1],
                        coordinates[j][0], coordinates[j][1]
                    )
                    max_distance = max(max_distance, dist)
            
            if max_distance > self.similarity_thresholds["coordinate"]:
                issues.append(f"多平台坐标差异过大: 最大偏移{max_distance:.0f}米")
        
        return issues
    
    def _calculate_confidence(
        self, 
        platform_matches: Dict[str, PlatformMatch],
        match_count: int,
        total_platforms: int
    ) -> float:
        """
        计算置信度
        """
        if total_platforms == 0:
            return 0.0
        
        base_confidence = match_count / total_platforms
        
        similarity_scores = [
            m.similarity_score for m in platform_matches.values() 
            if m.found and m.similarity_score > 0
        ]
        
        if similarity_scores:
            avg_similarity = sum(similarity_scores) / len(similarity_scores)
            confidence = base_confidence * 0.6 + avg_similarity * 0.4
        else:
            confidence = base_confidence
        
        return min(confidence, 1.0)
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        计算名称相似度
        """
        if not name1 or not name2:
            return 0.0
        
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        if name1 == name2:
            return 1.0
        
        if name1 in name2 or name2 in name1:
            return 0.9
        
        from difflib import SequenceMatcher
        return SequenceMatcher(None, name1, name2).ratio()
    
    def _haversine_distance(
        self, 
        lat1: float, lon1: float, 
        lat2: float, lon2: float
    ) -> float:
        """
        计算两点间的球面距离（米）
        """
        R = 6371000
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def _match_to_dict(self, match: PlatformMatch) -> Dict[str, Any]:
        """
        转换为字典格式
        """
        return {
            "platform": match.platform,
            "found": match.found,
            "similarity_score": match.similarity_score,
            "matched_data": match.matched_data,
            "differences": match.differences
        }


class AuthorityDataValidator:
    """
    权威数据核验器
    """
    
    def __init__(self):
        self.admin_boundaries = {}
        self.road_network = {}
        self.building_footprints = {}
    
    def validate_administrative_boundary(
        self, 
        lat: float, 
        lon: float,
        claimed_admin: str
    ) -> Dict[str, Any]:
        """
        行政区划边界校验
        """
        return {
            "valid": True,
            "claimed": claimed_admin,
            "actual": "待实现",
            "match": True,
            "note": "行政区划边界校验需要配置边界数据"
        }
    
    def validate_road_network(
        self, 
        lat: float, 
        lon: float
    ) -> Dict[str, Any]:
        """
        道路网络校验
        """
        return {
            "valid": True,
            "on_road": False,
            "distance_to_road": 0,
            "note": "道路网络校验需要配置路网数据"
        }
    
    def validate_building_footprint(
        self, 
        lat: float, 
        lon: float
    ) -> Dict[str, Any]:
        """
        建筑轮廓校验
        """
        return {
            "valid": True,
            "in_building": False,
            "building_info": {},
            "note": "建筑轮廓校验需要配置建筑数据"
        }


def validate_poi(poi_data: Dict[str, Any]) -> CrossValidationResult:
    """
    同步版本的POI验证接口
    """
    validator = MultiSourceValidator()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(validator.validate(poi_data))
    finally:
        loop.close()


async def validate_poi_async(poi_data: Dict[str, Any]) -> CrossValidationResult:
    """
    异步版本的POI验证接口
    """
    validator = MultiSourceValidator()
    return await validator.validate(poi_data)
