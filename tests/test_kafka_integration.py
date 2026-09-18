"""
Kafka 实时流处理端到端集成测试（Phase 8 验证）

前置条件：docker compose up -d zookeeper kafka，且 API 服务已启动
（KafkaService 在应用启动时自动创建 topic 并开启消费线程）。
Kafka 不可用时自动跳过，不阻塞常规测试流水线。

消息契约（与 api/services/kafka_service.py 保持一致）：
- 请求: {"request_id", "timestamp", "data": <DetectionRequest.model_dump()>}
- 结果: {"request_id", "timestamp", "data": <DetectionResultData.model_dump()>}
"""
import json
import os
import time
import uuid

import pytest

pytest.importorskip("kafka", reason="缺少 kafka-python")

from kafka import KafkaConsumer, KafkaProducer  # noqa: E402
from kafka.admin import KafkaAdminClient  # noqa: E402

BOOTSTRAP = os.getenv("KAFKA_TEST_BOOTSTRAP", "localhost:29092")
REQUEST_TOPIC = "geo-detection-requests"
RESULT_TOPIC = "geo-detection-results"
CONNECT_TIMEOUT = int(os.getenv("KAFKA_TEST_TIMEOUT", "30"))


def _kafka_available() -> bool:
    """轻量 TCP 探测：避免无 Kafka 时每个测试会话多等半分钟"""
    import socket

    host, _, port = BOOTSTRAP.partition(":")
    try:
        with socket.create_connection((host, int(port or 9092)), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _kafka_available(),
    reason=f"Kafka 不可用（{BOOTSTRAP}）。请先: docker compose up -d zookeeper kafka",
)


@pytest.fixture(scope="module")
def producer():
    p = KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    yield p
    p.close()


def _sample_message(request_id: str) -> dict:
    """与 KafkaService.send_detection_request 相同的消息结构"""
    return {
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data": {
            "device_id": "D_KAFKA_TEST",
            "user_id": "U_KAFKA_TEST",
            "timestamp": int(time.time()),
            "geo": {"latitude": 39.9042, "longitude": 116.4074},
            "content": {"text": "这家店超级超级推荐！必去必买！绝绝子！"},
        },
    }


class TestKafkaRealtime:
    def test_topics_exist(self):
        """KafkaService 启动后应自动创建请求/结果两个 topic"""
        admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP, request_timeout_ms=5000)
        topics = admin.list_topics()
        admin.close()
        assert REQUEST_TOPIC in topics, f"缺少 topic {REQUEST_TOPIC}，请先启动 API 服务或手动建 topic"
        assert RESULT_TOPIC in topics, f"缺少 topic {RESULT_TOPIC}"

    def test_end_to_end_detection(self, producer):
        """发送检测请求 → 消费线程执行检测 → 收到带评分的结果消息"""
        request_id = f"kafka-test-{uuid.uuid4().hex[:8]}"

        consumer = KafkaConsumer(
            RESULT_TOPIC,
            bootstrap_servers=BOOTSTRAP,
            group_id=f"test-{uuid.uuid4().hex[:8]}",
            auto_offset_reset="latest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            consumer_timeout_ms=CONNECT_TIMEOUT * 1000,
        )

        producer.send(REQUEST_TOPIC, key=request_id, value=_sample_message(request_id))
        producer.flush()

        received = None
        for message in consumer:
            value = message.value
            if isinstance(value, dict) and value.get("request_id") == request_id:
                received = value
                break
        consumer.close()

        assert received is not None, (
            f"{CONNECT_TIMEOUT}s 内未收到 request_id={request_id} 的结果；"
            "请确认 API 服务已启动且 KafkaService 消费线程在运行"
        )
        result_data = received.get("data") or {}
        # 结果应包含评分核心字段（DetectionResultData 结构）
        assert result_data.get("record_id"), f"结果缺少 record_id: {list(result_data.keys())}"
        assert 0 <= result_data.get("suspicion_score", -1) <= 100
        assert result_data.get("risk_level") in ("low", "medium", "high")
