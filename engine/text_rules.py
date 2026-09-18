"""
文本规则引擎
"""
from typing import List, Dict, Tuple
from dataclasses import dataclass, field, replace
import re

import sys
sys.path.insert(0, '..')
from config import text_config
from utils.text_utils import (
    detect_keyword_stuffing, calculate_text_features,
    calculate_keyword_density
)
from utils.scoring import combine_severities
from models import InputRecord


@dataclass
class TextAnomaly:
    """文本异常"""
    anomaly_type: str
    description: str
    severity: float  # 0-1
    details: Dict = field(default_factory=dict)


class TextRuleEngine:
    """文本规则引擎"""

    def __init__(self, config=None):
        # 每个引擎实例持有配置副本，而不是绑定全局单例：
        # 否则修改实例配置（如租户关键词）会泄漏到进程内所有其他检测
        if config is None:
            config = replace(text_config)
            if config.suspicious_keywords is not None:
                config.suspicious_keywords = list(config.suspicious_keywords)
        self.config = config
        self.template_patterns = self._build_template_patterns()

    def _build_template_patterns(self) -> List[re.Pattern]:
        """构建模板匹配正则

        注意：必须使用 (?:...) 分组交替而不是 [...] 字符类。
        字符类 [超级|强烈] 只匹配单个汉字（超/级/|/强/烈...），
        会导致"值得一去""味道一般"这类正常文本被误判为模板内容。
        """
        patterns = [
            # 重复感叹词（连续出现两次以上）
            re.compile(r'(?:超级|强烈|非常|特别){2,}'),
            # 重复推荐
            re.compile(r'(?:推荐|安利|必去|必买|必吃){2,}'),
            # 网络流行语堆砌
            re.compile(r'(?:yyds|绝绝子|绝了|宝藏)', re.IGNORECASE),
            # 过多感叹号
            re.compile(r'!{3,}|！{3,}'),
            # 营销模板：程度副词 + 推荐动词
            re.compile(r'(?:超级|强烈|特别|非常)(?:推荐|安利|介绍)'),
            # 营销模板：必X + 地点类名词
            re.compile(r'(?:必去|必买|必吃|必玩)(?:之地|地方|店铺|餐厅|景点|店)'),
            # 营销模板：打卡/网红类词 + 地点类名词
            re.compile(r'(?:打卡|网红|排队|火爆|人气)(?:地点|地方|店铺|餐厅|景点|店|胜地)'),
            # 夸大词汇（避免单字"最/一"等常见字误伤正常表述，
            # "第一"在"第一次"等日常表述中常见，仅匹配营销语境的复合形式）
            re.compile(
                r'(?:最好|最佳|最强|最牛|全网第一|销量第一|行业第一|排名第一|顶级|极致|完美|无敌|No\.?1|number\s*one)',
                re.IGNORECASE,
            ),
        ]
        return patterns

    def analyze(self, record: InputRecord) -> Tuple[float, List[TextAnomaly]]:
        """
        分析单条记录

        Args:
            record: 输入记录

        Returns:
            (异常分数, 异常列表)
        """
        anomalies = []
        text = record.content.text

        # 1. 长度检测
        anomaly = self._check_length(text)
        if anomaly:
            anomalies.append(anomaly)

        # 2. 关键词堆砌检测
        anomaly = self._check_keyword_stuffing(text)
        if anomaly:
            anomalies.append(anomaly)

        # 3. 可疑关键词检测 (先检测，结果传给模板检测)
        marketing_anomaly = self._check_suspicious_keywords(text)
        if marketing_anomaly:
            anomalies.append(marketing_anomaly)

        # 4. 模板化检测 (传入营销词检测结果用于严重度叠加)
        anomaly = self._check_template(text, marketing_anomaly)
        if anomaly:
            anomalies.append(anomaly)

        # 5. 标点符号异常
        anomaly = self._check_punctuation(text)
        if anomaly:
            anomalies.append(anomaly)

        # 计算异常分数：概率并集合并，异常越多分数越高
        if anomalies:
            score = combine_severities([a.severity for a in anomalies])
        else:
            score = 0.0

        return score, anomalies

    def _check_length(self, text: str) -> TextAnomaly:
        """检测文本长度"""
        length = len(text)

        if length < self.config.min_text_length:
            return TextAnomaly(
                anomaly_type="too_short",
                description=f"文本过短: {length}字符",
                severity=0.6,
                details={"length": length, "min_length": self.config.min_text_length}
            )

        if length > self.config.max_text_length:
            return TextAnomaly(
                anomaly_type="too_long",
                description=f"文本过长: {length}字符",
                severity=0.3,
                details={"length": length, "max_length": self.config.max_text_length}
            )

        return None

    def _check_keyword_stuffing(self, text: str) -> TextAnomaly:
        """检测关键词堆砌"""
        result = detect_keyword_stuffing(text, self.config.max_keyword_repeat)

        if result['has_stuffing']:
            return TextAnomaly(
                anomaly_type="keyword_stuffing",
                description=f"检测到关键词堆砌: {', '.join(result['stuffed_keywords'][:3])}",
                severity=0.8,
                details=result
            )

        return None

    def _check_template(self, text: str, marketing_anomaly: TextAnomaly = None) -> TextAnomaly:
        """检测模板化内容 - 支持与营销词检测的严重度叠加"""
        matches = []

        for pattern in self.template_patterns:
            found = pattern.findall(text)
            if found:
                matches.extend(found[:2])

        if matches:
            base_severity = 0.7

            # 如果同时存在营销词异常，叠加严重度
            if marketing_anomaly:
                stacked_severity = min(base_severity + marketing_anomaly.severity * 0.3, 1.0)
            else:
                stacked_severity = base_severity

            return TextAnomaly(
                anomaly_type="template_content",
                description=f"检测到模板化内容" + (" (伴随营销词)" if marketing_anomaly else ""),
                severity=stacked_severity,
                details={"matches": matches[:5], "stacked": marketing_anomaly is not None}
            )

        return None

    # 默认营销词库（租户可在 config.suspicious_keywords 中扩展/覆盖）
    DEFAULT_MARKETING_KEYWORDS = [
        "超级", "强烈推荐", "必去", "必买", "必吃", "绝绝子",
        "yyds", "宝藏", "绝了", "太赞了", "太棒了", "超赞",
        "安利", "打卡", "网红", "排队", "火爆",
        "最好", "最佳", "最强", "最牛", "顶级", "极致", "完美", "无敌", "No.1", "number one",
        "全网第一", "销量第一", "行业第一", "排名第一",
        "人气", "爆款", "新品", "限时", "优惠", "折扣",
        "免费", "赠品", "抽奖", "活动", "促销", "大促",
        "套餐", "团购", "优惠价", "最低价", "特价",
        "网红店", "网红打卡", "网红景点", "打卡胜地", "必打卡",
        "好评", "五星好评", "好评如潮", "口碑推荐",
        "不容错过", "错过后悔", "机不可失", "限时抢购", "手慢无"
    ]

    def _get_marketing_keywords(self) -> List[str]:
        """获取营销词库：租户配置的关键词 + 默认词库（去重合并）"""
        configured = getattr(self.config, 'suspicious_keywords', None) or []
        merged = list(configured)
        for kw in self.DEFAULT_MARKETING_KEYWORDS:
            if kw not in merged:
                merged.append(kw)
        return merged

    def _calculate_marketing_density(self, text: str) -> tuple:
        """
        计算营销词密度

        Returns:
            (density, matched_keywords, matched_count)
        """
        if not text:
            return 0.0, [], 0

        matched_keywords = []
        matched_chars = 0
        for keyword in self._get_marketing_keywords():
            if keyword in text:
                matched_keywords.append(keyword)
                # Count total characters of all occurrences
                matched_chars += text.count(keyword) * len(keyword)

        density = matched_chars / len(text) if len(text) > 0 else 0.0
        return density, matched_keywords, len(matched_keywords)

    def _check_suspicious_keywords(self, text: str) -> TextAnomaly:
        """检测可疑营销词 - 支持密度计算和严重度分级

        高严重度(0.8)要求密度超过5%且命中至少2个不同营销词：
        短文本中单个营销词的字符密度天然虚高（如"锦里打卡完毕。"中
        "打卡"占25%），只凭密度会把正常简短评论推到最高严重度。
        """
        density, found_keywords, count = self._calculate_marketing_density(text)

        if density > 0.05 and count >= 2:
            # 高密度且多营销词
            return TextAnomaly(
                anomaly_type="high_severity_marketing",
                description=f"高密度营销词(密度{density*100:.1f}%): {', '.join(found_keywords[:3])}",
                severity=0.8,
                details={"density": density, "count": count, "keywords": found_keywords[:5]}
            )
        elif density > 0.02:
            # 中等密度（含短文本单营销词的密度虚高场景）
            return TextAnomaly(
                anomaly_type="moderate_marketing",
                description=f"中等密度营销词(密度{density*100:.1f}%): {', '.join(found_keywords[:3])}",
                severity=0.5,
                details={"density": density, "count": count, "keywords": found_keywords[:5]}
            )
        elif count >= 3:
            # 低密度但数量多
            return TextAnomaly(
                anomaly_type="suspicious_keywords",
                description=f"包含{count}个营销词: {', '.join(found_keywords[:3])}",
                severity=min(count / 5, 0.4),
                details={"density": density, "count": count, "keywords": found_keywords[:5]}
            )

        return None

    def _check_punctuation(self, text: str) -> TextAnomaly:
        """检测标点符号异常"""
        features = calculate_text_features(text)

        # 感叹号过多
        if features['exclamation_count'] > 5:
            return TextAnomaly(
                anomaly_type="excessive_exclamation",
                description=f"感叹号过多: {features['exclamation_count']}个",
                severity=0.4,
                details=features
            )

        # 标点符号比例异常
        if features['char_count'] > 0:
            punct_ratio = features['punctuation_count'] / features['char_count']
            if punct_ratio > 0.2:  # 标点超过20%
                return TextAnomaly(
                    anomaly_type="excessive_punctuation",
                    description=f"标点符号比例异常: {punct_ratio*100:.1f}%",
                    severity=0.3,
                    details={"ratio": punct_ratio, **features}
                )

        return None
