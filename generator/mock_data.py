"""
模拟数据生成器
"""
import random
import string
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from models import InputRecord, GeoData, ContentData, Metadata


class MockDataGenerator:
    """模拟数据生成器"""

    def __init__(self, seed: Optional[int] = None):
        if seed:
            random.seed(seed)

        # 北京市中心坐标范围（示例区域）
        self.center_lat = 39.9042
        self.center_lon = 116.4074
        self.lat_range = 0.1   # 约11公里范围
        self.lon_range = 0.1

        # 正常评论模板
        self.normal_templates = [
            "今天和朋友来这里，{food}味道不错，环境也很{env}，下次还会再来。",
            "位置很好找，就在{location}附近。{food}很好吃，服务员态度{service}。",
            "周末带家人来的，{food}挺有特色的，价格{price}，整体满意。",
            "朋友推荐的，确实不错。{food}是招牌，环境{env}，值得一试。",
            "第{num}次来了，每次都点{food}，味道稳定，推荐。",
            "偶然发现的店，{food}出乎意料的好吃，性价比{price}。",
            "环境{env}，{food}味道正宗，服务{service}，会推荐给朋友。",
            "排队等了{num}分钟，不过值得。{food}很惊艳。",
        ]

        # 虚假评论模板
        self.fake_templates = [
            "超级超级好吃！强烈推荐！必去！必去！{food}绝绝子！",
            "推荐推荐推荐推荐！{food}太棒了！yyds！",
            "必买！必买！{food}真的是宝藏！绝了！",
            "太赞了太赞了！{food}超级好吃！强烈安利！",
            "{food}yyds！yyds！强烈推荐大家来！",
            "绝绝子绝绝子！{food}太赞了！必去！",
        ]

        # 关键词堆砌模板
        self.stuffing_templates = [
            "好吃好吃好吃好吃{food}好吃好吃好吃好吃",
            "推荐推荐推荐推荐{food}推荐推荐推荐推荐",
            "好吃好吃好吃{food}好吃好吃好吃好吃好吃",
        ]

        # 食物关键词
        self.foods = [
            "红烧肉", "糖醋排骨", "宫保鸡丁", "麻婆豆腐",
            "酸菜鱼", "水煮牛肉", "回锅肉", "鱼香肉丝",
            "小笼包", "炸酱面", "烤鸭", "火锅"
        ]

        # 环境/服务/价格关键词
        self.envs = ["干净", "舒适", "温馨", "有情调", "宽敞"]
        self.services = ["很好", "热情", "周到", "不错"]
        self.prices = ["实惠", "公道", "合理", "适中"]
        self.locations = ["地铁口", "商场", "公园", "学校"]

    def _generate_id(self, prefix: str = "R") -> str:
        """生成随机ID"""
        chars = string.ascii_uppercase + string.digits
        return f"{prefix}{''.join(random.choices(chars, k=8))}"

    def _generate_normal_coordinate(self) -> tuple:
        """生成正常坐标"""
        lat = self.center_lat + random.uniform(-self.lat_range, self.lat_range)
        lon = self.center_lon + random.uniform(-self.lon_range, self.lon_range)
        return lat, lon

    def _generate_fake_coordinate(self, anomaly_type: str = "out_of_range") -> tuple:
        """生成异常坐标"""
        if anomaly_type == "out_of_range":
            # 超出正常范围的坐标
            lat = random.choice([random.uniform(0, 10), random.uniform(60, 70)])
            lon = random.choice([random.uniform(0, 50), random.uniform(150, 180)])
        elif anomaly_type == "same_location":
            # 相同坐标（批量刷量）
            lat = 39.9123
            lon = 116.4567
        else:
            lat, lon = self._generate_normal_coordinate()
        return lat, lon

    def _generate_normal_text(self) -> str:
        """生成正常文本"""
        template = random.choice(self.normal_templates)
        return template.format(
            food=random.choice(self.foods),
            env=random.choice(self.envs),
            service=random.choice(self.services),
            price=random.choice(self.prices),
            location=random.choice(self.locations),
            num=random.randint(10, 60)
        )

    def _generate_fake_text(self, fake_type: str = "template") -> str:
        """生成虚假文本"""
        if fake_type == "template":
            template = random.choice(self.fake_templates)
            return template.format(food=random.choice(self.foods))
        elif fake_type == "stuffing":
            template = random.choice(self.stuffing_templates)
            return template.format(food=random.choice(self.foods))
        else:
            return self._generate_normal_text()

    def generate_normal_record(self) -> InputRecord:
        """生成正常记录"""
        lat, lon = self._generate_normal_coordinate()
        text = self._generate_normal_text()

        return InputRecord(
            record_id=self._generate_id("R"),
            device_id=self._generate_id("D"),
            user_id=self._generate_id("U"),
            timestamp=time.time() + random.uniform(-3600, 3600),
            geo=GeoData(latitude=lat, longitude=lon, accuracy=random.uniform(5, 50)),
            content=ContentData(text=text, content_type="review"),
            metadata=Metadata(ip=f"192.168.{random.randint(1,255)}.{random.randint(1,255)}"),
            label="normal"
        )

    def generate_fake_record(self,
                            geo_anomaly: Optional[str] = None,
                            text_anomaly: Optional[str] = None) -> InputRecord:
        """生成虚假记录"""
        # 坐标异常
        if geo_anomaly:
            lat, lon = self._generate_fake_coordinate(geo_anomaly)
        else:
            lat, lon = self._generate_normal_coordinate()

        # 文本异常
        if text_anomaly:
            text = self._generate_fake_text(text_anomaly)
        else:
            text = self._generate_fake_text("template")

        return InputRecord(
            record_id=self._generate_id("R"),
            device_id=self._generate_id("D"),
            user_id=self._generate_id("U"),
            timestamp=time.time() + random.uniform(-3600, 3600),
            geo=GeoData(latitude=lat, longitude=lon, accuracy=random.uniform(5, 50)),
            content=ContentData(text=text, content_type="review"),
            metadata=Metadata(ip=f"192.168.{random.randint(1,255)}.{random.randint(1,255)}"),
            label="fake"
        )

    def generate_batch(self,
                      normal_count: int = 50,
                      fake_count: int = 50,
                      geo_anomaly_ratio: float = 0.3,
                      text_anomaly_ratio: float = 0.7) -> List[InputRecord]:
        """
        批量生成数据

        Args:
            normal_count: 正常数据数量
            fake_count: 虚假数据数量
            geo_anomaly_ratio: 虚假数据中坐标异常的比例
            text_anomaly_ratio: 虚假数据中文本异常的比例

        Returns:
            记录列表
        """
        records = []

        # 生成正常数据
        for _ in range(normal_count):
            records.append(self.generate_normal_record())

        # 生成虚假数据
        for _ in range(fake_count):
            geo_anomaly = None
            text_anomaly = None

            if random.random() < geo_anomaly_ratio:
                geo_anomaly = random.choice(["out_of_range", "same_location"])

            if random.random() < text_anomaly_ratio:
                text_anomaly = random.choice(["template", "stuffing"])

            records.append(self.generate_fake_record(geo_anomaly, text_anomaly))

        # 打乱顺序
        random.shuffle(records)

        return records

    def generate_teleport_records(self, count: int = 10) -> List[InputRecord]:
        """生成瞬移异常记录（同一设备短时间内跨越长距离）"""
        records = []
        device_id = self._generate_id("D")
        user_id = self._generate_id("U")
        base_time = time.time()

        # 第一个位置：北京
        lat1, lon1 = 39.9042, 116.4074
        # 第二个位置：上海（约1000公里外）
        lat2, lon2 = 31.2304, 121.4737

        for i in range(count):
            # 在两个城市间跳跃（瞬移）
            if i % 2 == 0:
                lat, lon = lat1, lon1
            else:
                lat, lon = lat2, lon2

            record = InputRecord(
                record_id=self._generate_id("R"),
                device_id=device_id,
                user_id=user_id,
                timestamp=base_time + i * 30,  # 每30秒一条
                geo=GeoData(latitude=lat, longitude=lon),
                content=ContentData(text=self._generate_normal_text()),
                metadata=Metadata(),
                label="fake"
            )
            records.append(record)

        return records

    def generate_batch_similar_records(self, count: int = 20) -> List[InputRecord]:
        """生成批量相似内容记录（刷量特征）"""
        records = []
        base_text = "超级好吃！强烈推荐！{food}绝绝子！"

        for i in range(count):
            # 稍微变换一下内容
            food = random.choice(self.foods)
            text = base_text.format(food=food)

            record = InputRecord(
                record_id=self._generate_id("R"),
                device_id=self._generate_id("D"),
                user_id=self._generate_id("U"),
                timestamp=time.time() + i * 10,  # 每10秒一条
                geo=GeoData(latitude=39.9123, longitude=116.4567),  # 相同坐标
                content=ContentData(text=text),
                metadata=Metadata(),
                label="fake"
            )
            records.append(record)

        return records


if __name__ == "__main__":
    # 测试生成器
    generator = MockDataGenerator(seed=42)

    print("=== 生成正常记录 ===")
    normal = generator.generate_normal_record()
    print(normal.to_json())

    print("\n=== 生成虚假记录 ===")
    fake = generator.generate_fake_record(geo_anomaly="out_of_range", text_anomaly="template")
    print(fake.to_json())

    print("\n=== 批量生成统计 ===")
    batch = generator.generate_batch(normal_count=5, fake_count=5)
    normal_count = sum(1 for r in batch if r.label == "normal")
    fake_count = sum(1 for r in batch if r.label == "fake")
    print(f"总数: {len(batch)}, 正常: {normal_count}, 虚假: {fake_count}")
