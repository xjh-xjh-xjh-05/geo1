"""
地址解析与标准化工具
====================

提供详细的地址解析功能，包括省市区街道路门牌号的拆分和标准化。
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict
import jieba
import sys
sys.path.insert(0, '..')


@dataclass
class AddressComponent:
    """地址组件"""
    type: str  # province, city, district, street, number, building, etc.
    value: str
    confidence: float = 0.0
    alternatives: List[str] = field(default_factory=list)


@dataclass
class ParsedAddress:
    """解析后的地址"""
    raw_text: str
    components: Dict[str, AddressComponent]
    full_address: str
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    is_complete: bool = False


class AddressParser:
    """地址解析器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 加载行政区划数据
        self.admin_divisions = self._load_admin_divisions()

        # 初始化分词器
        jieba.initialize()

        # 地址关键词映射
        self.keyword_mapping = {
            # 省级
            '北京': ['北京市'],
            '上海': ['上海市'],
            '天津': ['天津市'],
            '重庆': ['重庆市'],
            '广东': ['广东省'],
            '江苏': ['江苏省'],
            '浙江': ['浙江省'],
            '山东': ['山东省'],
            '河南': ['河南省'],
            '四川': ['四川省'],
            '湖北': ['湖北省'],
            '湖南': ['湖南省'],
            '河北': ['河北省'],
            '福建': ['福建省'],
            '安徽': ['安徽省'],
            '江西': ['江西省'],
            '辽宁': ['辽宁省'],
            '黑龙江': ['黑龙江省'],
            '吉林': ['吉林省'],
            '山西': ['山西省'],
            '陕西': ['陕西省'],
            '甘肃': ['甘肃省'],
            '青海': ['青海省'],
            '新疆': ['新疆维吾尔自治区'],
            '西藏': ['西藏自治区'],
            '宁夏': ['宁夏回族自治区'],
            '广西': ['广西壮族自治区'],
            '内蒙古': ['内蒙古自治区'],
            '海南': ['海南省'],
            '台湾': ['台湾省'],
            '香港': ['香港特别行政区'],
            '澳门': ['澳门特别行政区'],

            # 市级
            '广州': ['广州市'],
            '深圳': ['深圳市'],
            '杭州': ['杭州市'],
            '南京': ['南京市'],
            '成都': ['成都市'],
            '武汉': ['武汉市'],
            '西安': ['西安市'],
            '重庆': ['重庆市'],
            '苏州': ['苏州市'],
            '天津': ['天津市'],
            '郑州': ['郑州市'],
            '长沙': ['长沙市'],
            '东莞': ['东莞市'],
            '青岛': ['青岛市'],
            '沈阳': ['沈阳市'],
            '宁波': ['宁波市'],
            '昆明': ['昆明市'],
            '合肥': ['合肥市'],
            '佛山': ['佛山市'],
            '福州': ['福州市'],
            '厦门': ['厦门市'],
            '哈尔滨': ['哈尔滨市'],
            '济南': ['济南市'],
            '大连': ['大连市'],
            '温州': ['温州市'],
            '南宁': ['南宁市'],
            '南昌': ['南昌市'],
            '贵阳': ['贵阳市'],
            '兰州': ['兰州市'],
            '银川': ['银川市'],
            '西宁': ['西宁市'],
            '海口': ['海口市'],
            '呼和浩特': ['呼和浩特市'],
            '太原': ['太原市'],
            '石家庄': ['石家庄市'],
            '长春': ['长春市'],
            '银川': ['银川市'],
            '拉萨': ['拉萨市'],
            '乌鲁木齐': ['乌鲁木齐市'],
            '香港': ['香港'],
            '澳门': ['澳门'],
            '台北': ['台北市'],

            # 区县级
            '朝阳区': ['朝阳区'],
            '海淀区': ['海淀区'],
            '东城区': ['东城区'],
            '西城区': ['西城区'],
            '丰台区': ['丰台区'],
            '石景山区': ['石景山区'],
            '通州区': ['通州区'],
            '昌平区': ['昌平区'],
            '大兴区': ['大兴区'],
            '顺义区': ['顺义区'],
            '房山区': ['房山区'],
            '门头沟区': ['门头沟区'],
            '怀柔区': ['怀柔区'],
            '平谷区': ['平谷区'],
            '密云区': ['密云区'],
            '延庆区': ['延庆区'],
            '浦东新区': ['浦东新区'],
            '黄浦区': ['黄浦区'],
            '徐汇区': ['徐汇区'],
            '长宁区': ['长宁区'],
            '静安区': ['静安区'],
            '普陀区': ['普陀区'],
            '虹口区': ['虹口区'],
            '杨浦区': ['杨浦区'],
            '闵行区': ['闵行区'],
            '宝山区': ['宝山区'],
            '嘉定区': ['嘉定区'],
            '金山区': ['金山区'],
            '松江区': ['松江区'],
            '青浦区': ['青浦区'],
            '奉贤区': ['奉贤区'],
            '崇明区': ['崇明区'],
        }

        # 街道关键词
        self.street_keywords = [
            '路', '街', '大道', '巷', '弄', '胡同', '道', '线', '公路', '大街',
            '中路', '西路', '东路', '南路', '北路', '支路', '巷', '弄堂', '横街',
            '纵街', '环线', '快速路', '主干道', '次干道', '支路'
        ]

        # 建筑物关键词
        self.building_keywords = [
            '大厦', '大楼', '中心', '广场', '商场', '市场', '城', '堡', '寨',
            '公寓', '小区', '花园', '苑', '庭', '坊', '村', '庄', '家园',
            '广场', '中心', '城', '宫', '馆', '楼', '厦', '屋', '坊',
            '大厦', '办公楼', '写字楼', '综合楼', '商务楼'
        ]

        # 门牌号模式
        self.number_patterns = [
            r'\d+[号|栋|幢|座|层|室|单元]',
            r'\d+[-]\d+[号|栋|幢|座|层|室|单元]',
            r'\d+[区|排|组|栋|幢]',
            r'[A-Za-z0-9]+[-][A-Za-z0-9]+',
            r'\d+[号]',
            r'\d+号',
            r'\d+',
        ]

    def parse_address(self, address_text: str) -> ParsedAddress:
        """
        解析地址文本

        Args:
            address_text: 原始地址文本

        Returns:
            ParsedAddress: 解析后的地址
        """
        parsed = ParsedAddress(raw_text=address_text)

        if not address_text or not address_text.strip():
            parsed.warnings.append("地址文本为空")
            return parsed

        # 1. 文本预处理
        clean_text = self._preprocess_address(address_text)

        # 2. 分词
        tokens = self._tokenize_address(clean_text)

        # 3. 识别行政区划
        components = self._identify_admin_divisions(tokens, clean_text)

        # 4. 识别街道和路名
        street_components = self._identify_street_and_number(clean_text, components)
        components.update(street_components)

        # 5. 识别建筑物
        building_components = self._identify_buildings(clean_text, components)
        components.update(building_components)

        # 6. 补充缺失信息
        self._complement_missing_components(components, clean_text)

        # 7. 构建完整地址
        parsed.full_address = self._build_complete_address(components)

        # 8. 计算置信度
        parsed.confidence = self._calculate_confidence(components)

        # 9. 检查完整性
        parsed.is_complete = self._check_completeness(components)

        # 10. 收集警告
        parsed.warnings = self._collect_warnings(components)

        # 11. 存储组件
        parsed.components = components

        return parsed

    def batch_parse_addresses(self, addresses: List[str]) -> List[ParsedAddress]:
        """
        批量解析地址

        Args:
            addresses: 地址列表

        Returns:
            List[ParsedAddress]: 解析结果列表
        """
        results = []

        for address in addresses:
            try:
                result = self.parse_address(address)
                results.append(result)
            except Exception as e:
                self.logger.error(f"解析地址 '{address}' 时出错: {str(e)}")
                error_result = ParsedAddress(
                    raw_text=address,
                    warnings=[f"解析错误: {str(e)}"]
                )
                results.append(error_result)

        return results

    def get_province_city_district(self, address: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        快速提取省市区信息

        Args:
            address: 地址文本

        Returns:
            Tuple[省份, 城市, 区县]
        """
        parsed = self.parse_address(address)

        province = None
        city = None
        district = None

        if 'province' in parsed.components:
            province = parsed.components['province'].value
        if 'city' in parsed.components:
            city = parsed.components['city'].value
        if 'district' in parsed.components:
            district = parsed.components['district'].value

        return province, city, district

    def normalize_address(self, address: str) -> str:
        """
        标准化地址格式

        Args:
            address: 原始地址

        Returns:
            标准化后的地址
        """
        parsed = self.parse_address(address)

        # 如果解析失败，返回原始地址
        if not parsed.is_complete:
            return address

        # 按标准顺序构建地址
        parts = []

        # 省份
        if 'province' in parsed.components:
            parts.append(parsed.components['province'].value)

        # 城市
        if 'city' in parsed.components:
            parts.append(parsed.components['city'].value)

        # 区县
        if 'district' in parsed.components:
            parts.append(parsed.components['district'].value)

        # 街道
        if 'street' in parsed.components:
            parts.append(parsed.components['street'].value)

        # 门牌号
        if 'number' in parsed.components:
            parts.append(parsed.components['number'].value)

        # 建筑物
        if 'building' in parsed.components:
            parts.append(parsed.components['building'].value)

        return ''.join(parts) if parts else address

    def is_valid_address(self, address: str) -> bool:
        """
        检查地址是否有效

        Args:
            address: 地址文本

        Returns:
            bool: 是否有效
        """
        parsed = self.parse_address(address)

        # 至少要有省份和城市，或者详细的街道地址
        has_province_city = ('province' in parsed.components and 'city' in parsed.components)
        has_detailed_address = ('street' in parsed.components and 'number' in parsed.components)

        return parsed.is_complete and (has_province_city or has_detailed_address)

    def find_similar_addresses(self, address: str, candidate_addresses: List[str], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        查找相似地址

        Args:
            address: 目标地址
            candidate_addresses: 候选地址列表
            top_k: 返回前K个最相似的地址

        Returns:
            List[Tuple[地址, 相似度分数]]
        """
        parsed_target = self.parse_address(address)
        similarities = []

        for candidate in candidate_addresses:
            parsed_candidate = self.parse_address(candidate)

            # 计算相似度
            similarity = self._calculate_address_similarity(parsed_target, parsed_candidate)
            similarities.append((candidate, similarity))

        # 排序并返回前K个
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    # 私有方法
    def _load_admin_divisions(self) -> Dict:
        """加载行政区划数据"""
        # 这里可以加载完整的行政区划数据
        # 实际应用中应该从数据库或文件加载
        return {}

    def _preprocess_address(self, address: str) -> str:
        """地址预处理"""
        # 去除多余的空格和换行
        address = re.sub(r'\s+', ' ', address).strip()

        # 去除特殊符号（保留中文、英文、数字、基本标点）
        address = re.sub(r'[^一-龥a-zA-Z0-9\s，。！？、；：""''（）【】\-\+\.]', '', address)

        # 标准化行政区划名称
        for short_name, full_names in self.keyword_mapping.items():
            for full_name in full_names:
                if full_name in address:
                    address = address.replace(full_name, short_name)
                    break

        return address

    def _tokenize_address(self, address: str) -> List[str]:
        """地址分词"""
        # 使用jieba进行分词
        tokens = list(jieba.cut(address))

        # 添加自定义分词规则
        custom_tokens = []
        for token in tokens:
            # 如果是数字+单位的组合，拆分
            if re.match(r'\d+[号|栋|幢|座|层|室|单元]', token):
                number, unit = re.match(r'(\d+)(.+)', token).groups()
                custom_tokens.extend([number, unit])
            else:
                custom_tokens.append(token)

        return custom_tokens

    def _identify_admin_divisions(self, tokens: List[str], address: str) -> Dict[str, AddressComponent]:
        """识别行政区划"""
        components = {}

        # 1. 识别省份
        province_component = self._identify_province(tokens, address)
        if province_component:
            components['province'] = province_component

        # 2. 识别城市
        city_component = self._identify_city(tokens, address)
        if city_component:
            components['city'] = city_component

        # 3. 识别区县
        district_component = self._identify_district(tokens, address)
        if district_component:
            components['district'] = district_component

        return components

    def _identify_province(self, tokens: List[str], address: str) -> Optional[AddressComponent]:
        """识别省份"""
        for token in tokens:
            # 检查是否是省份
            if token in self.keyword_mapping:
                # 如果是直辖市，也识别为省份
                confidence = 1.0 if token in ['北京', '上海', '天津', '重庆'] else 0.9
                return AddressComponent(
                    type='province',
                    value=token,
                    confidence=confidence
                )

        return None

    def _identify_city(self, tokens: List[str], address: str) -> Optional[AddressComponent]:
        """识别城市"""
        for token in tokens:
            # 检查是否是城市
            if token in self.keyword_mapping and len(token) > 1:
                # 排除已经识别为省的直辖市
                if token not in ['北京', '上海', '天津', '重庆']:
                    return AddressComponent(
                        type='city',
                        value=token,
                        confidence=0.9
                    )

        return None

    def _identify_district(self, tokens: List[str], address: str) -> Optional[AddressComponent]:
        """识别区县"""
        for token in tokens:
            # 检查是否是区县
            if token.endswith('区') or token.endswith('县') or token.endswith('市'):
                # 排除城市名
                if not (token.endswith('市') and token in self.keyword_mapping):
                    return AddressComponent(
                        type='district',
                        value=token,
                        confidence=0.8
                    )

        return None

    def _identify_street_and_number(self, address: str, components: Dict[str, AddressComponent]) -> Dict[str, AddressComponent]:
        """识别街道和门牌号"""
        street_components = {}

        # 如果已经有省市区，从中提取街道信息
        if components:
            # 去除已知行政区划后的剩余部分
            known_parts = [comp.value for comp in components.values()]
            remaining_address = address

            for part in known_parts:
                remaining_address = remaining_address.replace(part, '')

            remaining_address = remaining_address.strip()

            # 提取街道名
            street_component = self._extract_street_name(remaining_address)
            if street_component:
                street_components['street'] = street_component

            # 提取门牌号
            number_component = self._extract_house_number(remaining_address)
            if number_component:
                street_components['number'] = number_component

        return street_components

    def _extract_street_name(self, address: str) -> Optional[AddressComponent]:
        """提取街道名"""
        # 匹配街道关键词
        for keyword in self.street_keywords:
            if keyword in address:
                # 提取街道名
                street_pattern = r'(.+?)' + re.escape(keyword)
                match = re.search(street_pattern, address)
                if match:
                    street_name = match.group(1)
                    return AddressComponent(
                        type='street',
                        value=street_name + keyword,
                        confidence=0.8
                    )

        # 如果没有街道关键词，尝试匹配常见的路名模式
        road_pattern = r'(.+?)(路|街|大道|巷|弄)'
        match = re.search(road_pattern, address)
        if match:
            return AddressComponent(
                type='street',
                value=match.group(0),
                confidence=0.7
            )

        return None

    def _extract_house_number(self, address: str) -> Optional[AddressComponent]:
        """提取门牌号"""
        for pattern in self.number_patterns:
            match = re.search(pattern, address)
            if match:
                return AddressComponent(
                    type='number',
                    value=match.group(0),
                    confidence=0.9
                )

        return None

    def _identify_buildings(self, address: str, components: Dict[str, AddressComponent]) -> Dict[str, AddressComponent]:
        """识别建筑物"""
        building_components = {}

        # 去除已知行政区划和街道信息后的剩余部分
        known_parts = [comp.value for comp in components.values()]
        remaining_address = address

        for part in known_parts:
            remaining_address = remaining_address.replace(part, '')

        remaining_address = remaining_address.strip()

        # 匹配建筑物关键词
        for keyword in self.building_keywords:
            if keyword in remaining_address:
                # 提取建筑物名
                building_pattern = r'(.+?)' + re.escape(keyword)
                match = re.search(building_pattern, remaining_address)
                if match:
                    building_name = match.group(1) + keyword
                    building_components['building'] = AddressComponent(
                        type='building',
                        value=building_name,
                        confidence=0.8
                    )
                    break

        return building_components

    def _complement_missing_components(self, components: Dict[str, AddressComponent], address: str):
        """补充缺失的组件"""
        # 如果缺少省份，尝试从地址中推断
        if 'province' not in components:
            # 根据城市推断省份
            if 'city' in components:
                city = components['city'].value
                for province, cities in self.keyword_mapping.items():
                    if city in cities:
                        components['province'] = AddressComponent(
                            type='province',
                            value=province,
                            confidence=0.7
                        )
                        break

        # 如果缺少城市，尝试从区县推断
        if 'city' not in components and 'district' in components:
            district = components['district'].value
            # 根据区县推断城市（简化处理）
            if district.endswith('区') or district.endswith('县'):
                city_name = district[:-1]
                components['city'] = AddressComponent(
                    type='city',
                    value=city_name,
                    confidence=0.6
                )

    def _build_complete_address(self, components: Dict[str, AddressComponent]) -> str:
        """构建完整地址"""
        # 按标准顺序拼接
        order = ['province', 'city', 'district', 'street', 'number', 'building']
        parts = []

        for component_type in order:
            if component_type in components:
                parts.append(components[component_type].value)

        return ''.join(parts) if parts else ''

    def _calculate_confidence(self, components: Dict[str, AddressComponent]) -> float:
        """计算解析置信度"""
        if not components:
            return 0.0

        total_confidence = 0.0
        component_count = 0

        # 计算各组件的置信度
        for component in components.values():
            total_confidence += component.confidence
            component_count += 1

        # 基础置信度
        base_confidence = 0.5

        # 组件数量加分
        component_bonus = min(component_count * 0.1, 0.3)

        # 连贯性加分
        coherence_bonus = self._calculate_coherence_bonus(components)

        total_confidence = base_confidence + component_bonus + coherence_bonus
        return min(total_confidence, 1.0)

    def _calculate_coherence_bonus(self, components: Dict[str, AddressComponent]) -> float:
        """计算地址连贯性加分"""
        bonus = 0.0

        # 检查省市区连贯性
        if 'province' in components and 'city' in components:
            # 简单的连贯性检查
            bonus += 0.1

        # 检查街道和门牌号连贯性
        if 'street' in components and 'number' in components:
            bonus += 0.1

        return min(bonus, 0.2)

    def _check_completeness(self, components: Dict[str, AddressComponent]) -> bool:
        """检查地址完整性"""
        # 至少要有省市区，或者街道+门牌号
        has_province_city_district = all(
            comp_type in components for comp_type in ['province', 'city', 'district']
        )

        has_street_number = all(
            comp_type in components for comp_type in ['street', 'number']
        )

        return has_province_city_district or has_street_number

    def _collect_warnings(self, components: Dict[str, AddressComponent]) -> List[str]:
        """收集警告信息"""
        warnings = []

        # 检查缺失的组件
        if 'province' not in components:
            warnings.append("缺少省份信息")

        if 'city' not in components:
            warnings.append("缺少城市信息")

        if 'district' not in components:
            warnings.append("缺少区县信息")

        if 'street' not in components and 'number' not in components:
            warnings.append("缺少街道和门牌号信息")

        # 检查置信度
        if components:
            min_confidence = min(comp.confidence for comp in components.values())
            if min_confidence < 0.5:
                warnings.append(f"部分信息置信度较低（{min_confidence:.2f}）")

        return warnings

    def _calculate_address_similarity(self, addr1: ParsedAddress, addr2: ParsedAddress) -> float:
        """计算两个地址的相似度"""
        # 使用组件相似度计算
        similarity = 0.0
        component_count = 0

        # 比较相同类型的组件
        for comp_type in addr1.components:
            if comp_type in addr2.components:
                comp1 = addr1.components[comp_type]
                comp2 = addr2.components[comp_type]

                # 字符串相似度
                string_similarity = self._string_similarity(comp1.value, comp2.value)

                # 取最小置信度
                confidence_factor = min(comp1.confidence, comp2.confidence)

                similarity += string_similarity * confidence_factor
                component_count += 1

        # 计算平均相似度
        if component_count > 0:
            similarity = similarity / component_count
        else:
            # 如果没有相同组件，使用整体相似度
            similarity = self._string_similarity(addr1.raw_text, addr2.raw_text) * 0.5

        return similarity

    def _string_similarity(self, str1: str, str2: str) -> float:
        """计算字符串相似度"""
        if not str1 or not str2:
            return 0.0

        # 使用编辑距离
        max_len = max(len(str1), len(str2))
        if max_len == 0:
            return 1.0

        # 简化的编辑距离计算
        distance = 0
        for i in range(min(len(str1), len(str2))):
            if str1[i] != str2[i]:
                distance += 1

        # 相似度 = 1 - (编辑距离 / 最大长度)
        similarity = 1.0 - (distance / max_len)
        return max(0.0, similarity)


# 使用示例
if __name__ == "__main__":
    # 创建地址解析器
    parser = AddressParser()

    # 测试地址
    test_addresses = [
        "北京市朝阳区三里屯路19号",
        "上海市浦东新区张江高科技园区",
        "广州市天河区珠江新城花城大道1号",
        "深圳市南山区科技园南路88号",
        "杭州市西湖区文三路90号",
        "南京市鼓楼区汉中路1号",
        "成都市武侯区人民南路1号"
    ]

    # 批量解析
    results = parser.batch_parse_addresses(test_addresses)

    for result in results:
        print(f"原始地址: {result.raw_text}")
        print(f"解析结果: {result.full_address}")
        print(f"置信度: {result.confidence:.2f}")
        print(f"是否完整: {result.is_complete}")
        print("组件信息:")
        for comp_type, comp in result.components.items():
            print(f"  {comp_type}: {comp.value} (置信度: {comp.confidence:.2f})")
        if result.warnings:
            print("警告:")
            for warning in result.warnings:
                print(f"  - {warning}")
        print("-" * 50)