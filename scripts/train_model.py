"""
模型训练脚本
"""
import os
import sys
import json
import random
import zlib
from typing import List, Dict, Tuple
from dataclasses import dataclass

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)

from models import InputRecord, ContentData, GeoData
from engine.neural_model import FakeDetectionModel, NeuralConfig
from engine.geo_rules import GeoRuleEngine


@dataclass
class TrainingConfig:
    """训练配置"""
    model_name: str = "hfl/chinese-roberta-wwm-ext"
    max_length: int = 128
    batch_size: int = 16
    # 注意：本模型的文本编码是字符级 embedding + MLP（非预训练 BERT），
    # 需要 SGD 量级的学习率；2e-5 是 BERT 微调值，用在这里模型几乎不收敛。
    learning_rate: float = 1e-3
    num_epochs: int = 30
    hidden_dim: int = 256
    dropout_rate: float = 0.3
    use_cuda: bool = torch.cuda.is_available()
    train_ratio: float = 0.8
    val_ratio: float = 0.1
    test_ratio: float = 0.1
    model_save_path: str = os.path.join('data', 'models', 'fake_detection_model.pt')
    data_path: str = os.path.join('data', 'training_data.json')


class FakeDetectionDataset(Dataset):
    """虚假内容检测数据集

    模型的 forward() 内部会对文本做字符级编码，因此数据集只负责
    提供原始文本和地理特征，避免文本特征被双重编码导致维度错位。
    """

    def __init__(self, records: List[InputRecord], max_length: int = 128):
        self.records = records
        self.max_length = max_length
        self.geo_engine = GeoRuleEngine()

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        record = self.records[idx]
        text = record.content.text
        geo_features = self._extract_geo_features(record)
        label = 1 if record.label == "fake" else 0
        # 返回numpy数组，DataLoader才能正确堆叠为(B, 10)张量
        return text, np.asarray(geo_features, dtype=np.float32), label

    def _extract_geo_features(self, record: InputRecord) -> List[float]:
        """提取地理特征"""
        features = []

        # 基础坐标
        features.append(record.geo.latitude)
        features.append(record.geo.longitude)

        # 坐标范围归一化
        lat_norm = (record.geo.latitude - 35.0) / 20.0  # 中国纬度范围约18-54
        lon_norm = (record.geo.longitude - 104.0) / 30.0  # 中国经度范围约73-135
        features.append(lat_norm)
        features.append(lon_norm)

        # GEO异常检测
        geo_score, geo_anomalies = self.geo_engine.analyze(record)
        features.append(geo_score / 100.0)
        features.append(float(len(geo_anomalies)))

        # 设备ID哈希特征（CRC32保证跨进程稳定，内置hash每次启动随机化）
        device_hash = zlib.crc32(str(record.device_id).encode('utf-8')) % 100 / 100.0
        features.append(device_hash)

        # 时间特征
        hour = record.timestamp % 24
        features.append(hour / 24.0)

        # 补充特征
        features.extend([0.0] * (10 - len(features)))  # 确保特征维度一致

        return features


# ============================================================
# 训练数据生成辅助方法
# ============================================================

# 地点列表
_PLACES = [
    "故宫", "长城", "颐和园", "天坛", "北海公园",
    "王府井", "西单", "国贸", "三里屯", "中关村",
    "北京大学", "清华大学", "圆明园", "奥林匹克公园", "朝阳公园",
    "外滩", "东方明珠", "南京路", "豫园", "田子坊",
    "西湖", "灵隐寺", "千岛湖", "宋城", "河坊街",
    "宽窄巷子", "锦里", "武侯祠", "春熙路", "大熊猫基地",
    "陈家祠", "白云山", "长隆", "上下九", "珠江夜游",
]

# 正常评论模板（多种风格）
_NORMAL_TEMPLATES = {
    "concise": [
        "今天去了{place}，还不错。",
        "刚从{place}回来，挺好的。",
        "{place}值得一去。",
        "去了{place}，感觉还行。",
        "{place}打卡完毕。",
    ],
    "detailed": [
        "周末和朋友去了{place}，整体体验不错。环境干净整洁，服务人员态度友好，价格也比较合理。推荐大家有空可以去看看。",
        "今天去了{place}，从进门到离开大概待了两个小时。整体感受不错，环境舒适，工作人员也很热情。唯一不足是周末人有点多。",
        "在{place}逛了一下午，景色宜人，设施也比较完善。停车场很大很方便，门票价格适中，适合家庭出游。",
    ],
    "neutral": [
        "在{place}吃了个饭，味道一般，环境还行。",
        "{place}去了，没什么特别的感觉，就那样吧。",
        "路过{place}随便看了看，中规中矩。",
        "{place}的体验一般般，没有网上说的那么好。",
    ],
    "casual": [
        "{place}路过随便逛了逛，没什么特别的。",
        "今天闲着没事去了趟{place}，消磨时间还行。",
        "在{place}转了一圈，就那样吧。",
        "朋友约着去{place}，去了也就那样。",
    ],
    "positive_natural": [
        "{place}的风景确实不错，适合周末放松。",
        "去了{place}，空气很好，心情都变好了。",
        "{place}挺安静的，适合散步，下次还想去。",
        "在{place}待了一天，感觉挺充实的。",
    ],
}

# 营销刷量模板（不同密度）
_MARKETING_TEMPLATES = {
    "light": [
        "推荐{place}，味道不错，值得试试。",
        "{place}还不错，推荐一下。",
        "去了{place}，体验不错，推荐。",
    ],
    "medium": [
        "强烈推荐{place}，味道绝绝子，必去打卡！",
        "{place}真的是宝藏店铺，强烈推荐大家去！",
        "超级推荐{place}！必去打卡！绝了！",
        "{place}yyds！强烈推荐！",
    ],
    "heavy": [
        "超级推荐{place}！真的是宝藏店铺！yyds！必去打卡！绝了！强烈推荐大家去！不去后悔！",
        "{place}绝绝子！yyds！宝藏店铺！必去打卡！超级推荐！强烈推荐！不去后悔一辈子！",
        "强烈推荐{place}！绝了！yyds！宝藏！必去！打卡！超级推荐大家去！不去后悔！太赞了！",
    ],
}

# 边界案例模板
_BOUNDARY_TEMPLATES = {
    "normal_leaning": [
        "去了{place}，味道还不错，推荐一下。",
        "{place}挺好的，大家可以试试。",
        "今天去了{place}，体验不错，值得推荐。",
    ],
    "enthusiastic_genuine": [
        "{place}真的太美了！下次还来！",
        "太喜欢{place}了！简直完美！",
        "{place}太棒了！强烈推荐！下次一定再来！",
    ],
}


def _random_china_coordinate():
    """生成中国境内的随机坐标"""
    latitude = random.uniform(18.0, 54.0)
    longitude = random.uniform(73.0, 135.0)
    return latitude, longitude


def _generate_invalid_coordinate_records(count: int, start_id: int) -> List[InputRecord]:
    """生成无效/超出范围的坐标记录

    坐标均明确位于中国境外且远离边界5度容差带，确保可被范围规则识别。
    """
    records = []
    invalid_coords = [
        (0.0, 0.0),          # 零坐标
        (0.0, 0.0),          # 零坐标（增加权重）
        (-33.9, 151.2),      # 悉尼
        (51.5, -0.1),        # 伦敦
        (40.7, -74.0),       # 纽约
        (35.6, 139.7),       # 东京
        (90.0, 180.0),       # 极端值
        (-90.0, -180.0),     # 极端值
        (1.35, 103.8),       # 新加坡
        (64.0, 21.0),        # 冰岛
    ]

    for i in range(count):
        lat, lon = random.choice(invalid_coords)
        # 添加微小随机偏移（保持远离容差带）
        lat += random.uniform(-0.5, 0.5)
        lon += random.uniform(-0.5, 0.5)

        place = random.choice(_PLACES)
        # 使用正常文本模板
        style = random.choice(list(_NORMAL_TEMPLATES.keys()))
        template = random.choice(_NORMAL_TEMPLATES[style])
        text = template.format(place=place)

        record = InputRecord(
            record_id=f"geo_invalid_{start_id + i}",
            device_id=f"device_{random.randint(1, 100)}",
            user_id=f"user_{random.randint(1, 50)}",
            timestamp=1700000000 + random.randint(0, 86400 * 365),
            content=ContentData(text=text),
            geo=GeoData(latitude=lat, longitude=lon),
            label="fake"
        )
        records.append(record)

    return records


def _generate_teleport_records(count: int, start_id: int) -> List[InputRecord]:
    """生成瞬移行为记录（同一设备，时间接近但坐标距离很远）

    两种模式：
    - 秒级跳跃（2-60秒内跨城）：命中瞬移检测
    - 分钟级跳跃（5-30分钟跨城）：隐含速度远超高铁，命中超速检测
    """
    records = []
    # 远距离城市对（公里数 > 500）
    city_pairs = [
        ((39.9, 116.4), (31.2, 121.5)),   # 北京 -> 上海
        ((39.9, 116.4), (23.1, 113.3)),   # 北京 -> 广州
        ((31.2, 121.5), (30.6, 104.1)),   # 上海 -> 成都
        ((23.1, 113.3), (30.6, 104.1)),   # 广州 -> 成都
        ((39.9, 116.4), (45.8, 126.5)),   # 北京 -> 哈尔滨
        ((30.6, 104.1), (43.8, 87.6)),    # 成都 -> 乌鲁木齐
        ((31.2, 121.5), (22.5, 114.1)),   # 上海 -> 深圳
        ((39.9, 116.4), (34.3, 108.9)),   # 北京 -> 西安
    ]

    for i in range(count):
        device_id = f"device_teleport_{random.randint(1, 50)}"
        user_id = f"user_{random.randint(1, 50)}"
        base_time = 1700000000 + random.randint(0, 86400 * 365)
        # 一半秒级跳跃，一半分钟级跳跃
        if random.random() < 0.5:
            time_gap = random.randint(2, 60)          # 秒级：瞬移
        else:
            time_gap = random.randint(5, 30) * 60     # 分钟级：超速

        coord_a, coord_b = random.choice(city_pairs)
        place_a = random.choice(_PLACES)
        place_b = random.choice(_PLACES)

        style = random.choice(list(_NORMAL_TEMPLATES.keys()))
        template_a = random.choice(_NORMAL_TEMPLATES[style])
        template_b = random.choice(_NORMAL_TEMPLATES[style])

        # 第一条记录
        record_a = InputRecord(
            record_id=f"geo_teleport_{start_id + i}_a",
            device_id=device_id,
            user_id=user_id,
            timestamp=base_time,
            content=ContentData(text=template_a.format(place=place_a)),
            geo=GeoData(
                latitude=coord_a[0] + random.uniform(-0.01, 0.01),
                longitude=coord_a[1] + random.uniform(-0.01, 0.01)
            ),
            label="fake"
        )

        # 第二条记录（瞬移后）
        record_b = InputRecord(
            record_id=f"geo_teleport_{start_id + i}_b",
            device_id=device_id,
            user_id=user_id,
            timestamp=base_time + time_gap,
            content=ContentData(text=template_b.format(place=place_b)),
            geo=GeoData(
                latitude=coord_b[0] + random.uniform(-0.01, 0.01),
                longitude=coord_b[1] + random.uniform(-0.01, 0.01)
            ),
            label="fake"
        )

        records.append(record_a)
        records.append(record_b)

    return records


def _generate_high_frequency_records(count: int, start_id: int) -> List[InputRecord]:
    """生成高频上报记录（同一设备短时间内大量上报）

    count 为目标记录总数：按设备分组生成，每台设备在一小时内上报
    120-260次（远超默认每小时100次阈值），模拟机器批量刷单。
    """
    records = []
    generated = 0

    while generated < count:
        device_id = f"device_hf_{start_id}_{generated}"
        user_id = f"user_hf_{generated}"
        base_time = 1700000000 + random.randint(0, 86400 * 365)
        lat, lon = _random_china_coordinate()

        # 同一设备1小时内上报120-260次
        num_records = min(random.randint(120, 260), count - generated)
        place = random.choice(_PLACES)

        for j in range(num_records):
            # 每条记录间隔5-15秒
            ts = base_time + j * random.randint(5, 15)
            # 坐标微小偏移
            r_lat = lat + random.uniform(-0.001, 0.001)
            r_lon = lon + random.uniform(-0.001, 0.001)

            style = random.choice(list(_NORMAL_TEMPLATES.keys()))
            template = random.choice(_NORMAL_TEMPLATES[style])
            text = template.format(place=place)

            record = InputRecord(
                record_id=f"geo_hf_{start_id}_{generated + j}",
                device_id=device_id,
                user_id=user_id,
                timestamp=ts,
                content=ContentData(text=text),
                geo=GeoData(latitude=r_lat, longitude=r_lon),
                label="fake"
            )
            records.append(record)

        generated += num_records

    return records


def create_training_data(sample_size: int = 5000) -> List[InputRecord]:
    """创建训练数据（5类：正常、营销刷量、地理异常、混合型、边界案例）"""
    records = []
    record_counter = 0

    # ---- 1. 正常评论 (约60%，~3000条) ----
    normal_count = int(sample_size * 0.6)
    style_weights = {
        "concise": 0.25,
        "detailed": 0.2,
        "neutral": 0.2,
        "casual": 0.2,
        "positive_natural": 0.15,
    }

    for i in range(normal_count):
        # 按权重选择风格
        style = random.choices(
            list(style_weights.keys()),
            weights=list(style_weights.values()),
            k=1
        )[0]
        template = random.choice(_NORMAL_TEMPLATES[style])
        place = random.choice(_PLACES)
        text = template.format(place=place)

        lat, lon = _random_china_coordinate()

        record = InputRecord(
            record_id=f"normal_{record_counter}",
            device_id=f"device_{random.randint(1, 200)}",
            user_id=f"user_{random.randint(1, 100)}",
            timestamp=1700000000 + random.randint(0, 86400 * 365),
            content=ContentData(text=text),
            geo=GeoData(latitude=lat, longitude=lon),
            label="normal"
        )
        records.append(record)
        record_counter += 1

    # ---- 2. 营销刷量 (约16%，~800条) ----
    marketing_count = int(sample_size * 0.16)
    density_weights = {"light": 0.3, "medium": 0.4, "heavy": 0.3}

    for i in range(marketing_count):
        density = random.choices(
            list(density_weights.keys()),
            weights=list(density_weights.values()),
            k=1
        )[0]
        template = random.choice(_MARKETING_TEMPLATES[density])
        place = random.choice(_PLACES)
        text = template.format(place=place)

        lat, lon = _random_china_coordinate()

        record = InputRecord(
            record_id=f"marketing_{record_counter}",
            device_id=f"device_{random.randint(1, 200)}",
            user_id=f"user_{random.randint(1, 100)}",
            timestamp=1700000000 + random.randint(0, 86400 * 365),
            content=ContentData(text=text),
            geo=GeoData(latitude=lat, longitude=lon),
            label="fake"
        )
        records.append(record)
        record_counter += 1

    # ---- 3. 地理异常 (约8%，~400条) ----
    geo_anomaly_count = int(sample_size * 0.08)
    # 分配给三种子类型
    invalid_count = geo_anomaly_count // 3
    teleport_count = geo_anomaly_count // 3
    hf_count = geo_anomaly_count - invalid_count - teleport_count

    invalid_records = _generate_invalid_coordinate_records(invalid_count, record_counter)
    record_counter += len(invalid_records)
    records.extend(invalid_records)

    teleport_records = _generate_teleport_records(teleport_count, record_counter)
    record_counter += len(teleport_records)
    records.extend(teleport_records)

    hf_records = _generate_high_frequency_records(hf_count, record_counter)
    record_counter += len(hf_records)
    records.extend(hf_records)

    # ---- 4. 混合型 (约8%，~400条) ----
    mixed_count = int(sample_size * 0.08)
    for i in range(mixed_count):
        mixed_type = random.choice(["marketing_geo_invalid", "template_teleport"])

        if mixed_type == "marketing_geo_invalid":
            # 营销文本 + 超出范围坐标
            density = random.choice(list(_MARKETING_TEMPLATES.keys()))
            template = random.choice(_MARKETING_TEMPLATES[density])
            place = random.choice(_PLACES)
            text = template.format(place=place)
            # 明确超出中国范围且远离容差带的坐标
            lat = random.choice([0.0, -33.9, 62.0, 40.7]) + random.uniform(-0.5, 0.5)
            lon = random.choice([0.0, 151.2, 30.0, -74.0]) + random.uniform(-0.5, 0.5)

            record = InputRecord(
                record_id=f"mixed_{record_counter}",
                device_id=f"device_{random.randint(1, 200)}",
                user_id=f"user_{random.randint(1, 100)}",
                timestamp=1700000000 + random.randint(0, 86400 * 365),
                content=ContentData(text=text),
                geo=GeoData(latitude=lat, longitude=lon),
                label="fake"
            )
            records.append(record)
            record_counter += 1
        else:
            # 模板文本 + 真实瞬移对：同一设备短时间跨城，两条记录都标注为fake
            device_id = f"device_mixed_tp_{i}"
            base_time = 1700000000 + random.randint(0, 86400 * 365)
            time_gap = random.randint(2, 60) if random.random() < 0.5 \
                else random.randint(5, 30) * 60
            city_pairs = [
                ((39.9, 116.4), (31.2, 121.5)),
                ((39.9, 116.4), (23.1, 113.3)),
                ((31.2, 121.5), (30.6, 104.1)),
            ]
            coord_a, coord_b = random.choice(city_pairs)

            for suffix, coord, ts in (
                ("a", coord_a, base_time),
                ("b", coord_b, base_time + time_gap),
            ):
                style = random.choice(list(_NORMAL_TEMPLATES.keys()))
                template = random.choice(_NORMAL_TEMPLATES[style])
                place = random.choice(_PLACES)
                text = template.format(place=place)

                record = InputRecord(
                    record_id=f"mixed_{record_counter}_{suffix}",
                    device_id=device_id,
                    user_id=f"user_{random.randint(1, 100)}",
                    timestamp=ts,
                    content=ContentData(text=text),
                    geo=GeoData(
                        latitude=coord[0] + random.uniform(-0.01, 0.01),
                        longitude=coord[1] + random.uniform(-0.01, 0.01)
                    ),
                    label="fake"
                )
                records.append(record)
                record_counter += 1

    # ---- 5. 边界案例 (约8%，~400条) ----
    boundary_count = int(sample_size * 0.08)
    normal_leaning_count = boundary_count // 2
    fake_leaning_count = boundary_count - normal_leaning_count

    # 5a. 正常倾向的边界案例 (~200条)
    for i in range(normal_leaning_count):
        template_type = random.choice(["normal_leaning", "enthusiastic_genuine"])
        template = random.choice(_BOUNDARY_TEMPLATES[template_type])
        place = random.choice(_PLACES)
        text = template.format(place=place)

        lat, lon = _random_china_coordinate()

        record = InputRecord(
            record_id=f"boundary_normal_{record_counter}",
            device_id=f"device_{random.randint(1, 200)}",
            user_id=f"user_{random.randint(1, 100)}",
            timestamp=1700000000 + random.randint(0, 86400 * 365),
            content=ContentData(text=text),
            geo=GeoData(latitude=lat, longitude=lon),
            label="normal"
        )
        records.append(record)
        record_counter += 1

    # 5b. 虚假倾向的边界案例 (~200条)
    for i in range(fake_leaning_count):
        boundary_type = random.choice(["border_coords", "enthusiastic_suspicious"])

        if boundary_type == "border_coords":
            # 正常文本但坐标在中国边境区域
            style = random.choice(list(_NORMAL_TEMPLATES.keys()))
            template = random.choice(_NORMAL_TEMPLATES[style])
            place = random.choice(_PLACES)
            text = template.format(place=place)
            # 中国边境坐标
            border_coords = [
                (18.5, 110.0),   # 海南南端
                (53.5, 120.0),   # 黑龙江北端
                (40.0, 73.5),    # 新疆西端
                (48.0, 135.0),   # 黑龙江东端
                (22.0, 108.0),   # 广西南端
            ]
            lat, lon = random.choice(border_coords)
            lat += random.uniform(-1.0, 1.0)
            lon += random.uniform(-1.0, 1.0)
        else:
            # 过度热情但可能真实的文本
            template = random.choice(_BOUNDARY_TEMPLATES["enthusiastic_genuine"])
            place = random.choice(_PLACES)
            text = template.format(place=place)
            lat, lon = _random_china_coordinate()

        record = InputRecord(
            record_id=f"boundary_fake_{record_counter}",
            device_id=f"device_{random.randint(1, 200)}",
            user_id=f"user_{random.randint(1, 100)}",
            timestamp=1700000000 + random.randint(0, 86400 * 365),
            content=ContentData(text=text),
            geo=GeoData(latitude=lat, longitude=lon),
            label="fake"
        )
        records.append(record)
        record_counter += 1

    # 打乱顺序
    random.shuffle(records)

    return records


def save_training_data(records: List[InputRecord], path: str):
    """保存训练数据"""
    data = []
    for record in records:
        data.append({
            "record_id": record.record_id,
            "device_id": record.device_id,
            "user_id": record.user_id,
            "timestamp": record.timestamp,
            "content": {
                "text": record.content.text
            },
            "geo": {
                "latitude": record.geo.latitude,
                "longitude": record.geo.longitude
            },
            "label": record.label
        })

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_training_data(path: str) -> List[InputRecord]:
    """加载训练数据"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    records = []
    for item in data:
        record = InputRecord(
            record_id=item["record_id"],
            device_id=item["device_id"],
            user_id=item.get("user_id", f"user_{random.randint(1, 50)}"),
            timestamp=item["timestamp"],
            content=ContentData(text=item["content"]["text"]),
            geo=GeoData(
                latitude=item["geo"]["latitude"],
                longitude=item["geo"]["longitude"]
            ),
            label=item["label"]
        )
        records.append(record)

    return records


def _evaluate_predictions(y_true: List[int], y_pred: List[int]) -> Dict:
    """计算完整评估指标：精确率、召回率、F1、混淆矩阵"""
    metrics = {}
    try:
        metrics["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
        metrics["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
        metrics["f1"] = float(f1_score(y_true, y_pred, zero_division=0))
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        metrics["confusion_matrix"] = {
            "labels": ["normal", "fake"],
            "matrix": cm.tolist(),
        }
        metrics["classification_report"] = classification_report(
            y_true, y_pred, target_names=["normal", "fake"],
            output_dict=True, zero_division=0
        )
    except Exception as e:
        print(f"[WARNING] sklearn 指标计算失败: {e}")
        # 手动计算基础指标
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
        tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
        metrics["precision"] = tp / (tp + fp) if tp + fp else 0.0
        metrics["recall"] = tp / (tp + fn) if tp + fn else 0.0
        metrics["f1"] = (
            2 * metrics["precision"] * metrics["recall"] /
            (metrics["precision"] + metrics["recall"])
            if metrics["precision"] + metrics["recall"] else 0.0
        )
        metrics["confusion_matrix"] = {
            "labels": ["normal", "fake"],
            "matrix": [[tn, fp], [fn, tp]],
        }
    return metrics


def train_model():
    """训练模型"""
    config = TrainingConfig()

    # 创建或加载训练数据
    if not os.path.exists(config.data_path):
        print("创建训练数据...")
        records = create_training_data(sample_size=5000)
        save_training_data(records, config.data_path)
        print(f"训练数据已保存到: {config.data_path}")
    else:
        print("加载训练数据...")
        records = load_training_data(config.data_path)
        print(f"加载了 {len(records)} 条训练数据")

    # 划分数据集
    random.shuffle(records)
    total = len(records)
    train_size = int(total * config.train_ratio)
    val_size = int(total * config.val_ratio)
    test_size = total - train_size - val_size

    train_records = records[:train_size]
    val_records = records[train_size:train_size+val_size]
    test_records = records[train_size+val_size:]

    print(f"数据集划分: 训练{train_size}, 验证{val_size}, 测试{test_size}")

    # 初始化模型（文本特征由模型内部编码，无需外部tokenizer）
    model = FakeDetectionModel(NeuralConfig(
        model_name=config.model_name,
        max_length=config.max_length,
        hidden_dim=config.hidden_dim,
        dropout_rate=config.dropout_rate
    ))

    # 创建数据集和数据加载器
    train_dataset = FakeDetectionDataset(train_records, config.max_length)
    val_dataset = FakeDetectionDataset(val_records, config.max_length)
    test_dataset = FakeDetectionDataset(test_records, config.max_length)

    train_loader = DataLoader(train_dataset, batch_size=config.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=config.batch_size)
    test_loader = DataLoader(test_dataset, batch_size=config.batch_size)

    # 定义优化器和损失函数
    optimizer = optim.Adam(model.parameters(), lr=config.learning_rate)
    criterion = nn.CrossEntropyLoss()

    def _run_epoch(loader, training: bool):
        """执行一轮前向计算，返回 (平均损失, 准确率, 真实标签, 预测标签)"""
        model.train() if training else model.eval()
        total_loss, correct, count = 0.0, 0, 0
        all_true, all_pred = [], []

        context = torch.enable_grad() if training else torch.no_grad()
        with context:
            for texts, geo_features, labels in loader:
                geo_features = torch.as_tensor(geo_features, dtype=torch.float32).to(model.device)
                labels = torch.as_tensor(labels, dtype=torch.long).to(model.device)

                # forward() 内部编码文本特征，这里只传入地理特征
                logits = model(list(texts), geo_features)
                loss = criterion(logits, labels)

                if training:
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                _, predicted = torch.max(logits, 1)
                correct += (predicted == labels).sum().item()
                count += labels.size(0)
                total_loss += loss.item() * labels.size(0)
                all_true.extend(labels.cpu().tolist())
                all_pred.extend(predicted.cpu().tolist())

        avg_loss = total_loss / count if count else 0.0
        acc = correct / count if count else 0.0
        return avg_loss, acc, all_true, all_pred

    # 训练循环
    best_val_loss = float('inf')

    print("开始训练...")
    for epoch in range(config.num_epochs):
        train_loss, train_acc, _, _ = _run_epoch(train_loader, training=True)
        val_loss, val_acc, _, _ = _run_epoch(val_loader, training=False)

        print(f"Epoch {epoch+1}/{config.num_epochs}: "
              f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f}, "
              f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.4f}")

        # 保存最佳模型
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            os.makedirs(os.path.dirname(config.model_save_path), exist_ok=True)
            torch.save(model.state_dict(), config.model_save_path)
            print(f"保存最佳模型到: {config.model_save_path}")

    # 测试
    print("测试模型...")
    model.load_state_dict(torch.load(config.model_save_path, map_location=model.device))

    test_loss, test_acc, y_true, y_pred = _run_epoch(test_loader, training=False)

    print(f"测试结果: Loss: {test_loss:.4f}, Acc: {test_acc:.4f}")

    # 输出完整评估指标
    metrics = _evaluate_predictions(y_true, y_pred)
    print(f"精确率(Precision): {metrics['precision']:.4f}")
    print(f"召回率(Recall): {metrics['recall']:.4f}")
    print(f"F1分数: {metrics['f1']:.4f}")
    cm = metrics["confusion_matrix"]
    print(f"混淆矩阵 (行=真实, 列=预测, 标签={cm['labels']}):")
    for row in cm["matrix"]:
        print(f"  {row}")

    # 保存评估指标
    metrics_path = config.model_save_path.replace('.pt', '_metrics.json')
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_accuracy": test_acc,
            "test_loss": test_loss,
            **metrics
        }, f, ensure_ascii=False, indent=2)
    print(f"评估指标已保存到: {metrics_path}")

    # 测试几个样例
    print("\n测试样例:")
    test_samples = test_records[:5]
    for sample in test_samples:
        geo_features = train_dataset._extract_geo_features(sample)
        geo_tensor = torch.tensor([geo_features], dtype=torch.float32)
        predictions, scores = model.predict([sample.content.text], geo_tensor)

        print(f"文本: {sample.content.text}")
        print(f"真实标签: {sample.label}")
        print(f"预测结果: {'虚假' if predictions[0] == 1 else '正常'}")
        print(f"置信度: {scores[0]:.4f}")
        print("---")


if __name__ == "__main__":
    train_model()
