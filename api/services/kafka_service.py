"""
Kafka实时流处理服务
"""
import sys
import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import threading

from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError

from api.core.config import settings
from api.models.schemas import DetectionRequest, DetectionResultData
from api.services.detection_service import DetectionService
from api.core.database import SessionLocal


class KafkaService:
    """
    Kafka服务
    - 消息生产者
    - 消息消费者
    - 主题管理
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS or "localhost:9092"
        self.detection_topic = "geo-detection-requests"
        self.result_topic = "geo-detection-results"
        self.admin_client = None
        self.producer = None
        self.consumer = None
        self.consumer_thread = None
        self.running = False
        
        self._init_admin()
        self._create_topics()
        self._init_producer()
    
    def _init_admin(self):
        """初始化管理员客户端"""
        try:
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers,
                client_id="geo-detection-admin"
            )
        except Exception as e:
            print(f"Kafka admin初始化失败: {e}")
    
    def _create_topics(self):
        """创建主题"""
        if not self.admin_client:
            return
        
        topics = [
            NewTopic(name=self.detection_topic, num_partitions=3, replication_factor=1),
            NewTopic(name=self.result_topic, num_partitions=3, replication_factor=1)
        ]
        
        try:
            self.admin_client.create_topics(new_topics=topics)
            print(f"创建Kafka主题成功: {[t.name for t in topics]}")
        except TopicAlreadyExistsError:
            print("Kafka主题已存在")
        except Exception as e:
            print(f"创建Kafka主题失败: {e}")
    
    def _init_producer(self):
        """初始化生产者"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3,
                retry_backoff_ms=1000
            )
            print("Kafka生产者初始化成功")
        except Exception as e:
            print(f"Kafka生产者初始化失败: {e}")
    
    def _init_consumer(self, group_id: str = "geo-detection-group"):
        """初始化消费者"""
        try:
            self.consumer = KafkaConsumer(
                self.detection_topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=group_id,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                auto_commit_interval_ms=1000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            print("Kafka消费者初始化成功")
        except Exception as e:
            print(f"Kafka消费者初始化失败: {e}")
    
    def send_detection_request(self, request: DetectionRequest) -> bool:
        """
        发送检测请求到Kafka
        """
        if not self.producer:
            return False
        
        try:
            message_key = f"req_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{os.urandom(8).hex()}"
            message_value = {
                "request_id": message_key,
                "timestamp": datetime.utcnow().isoformat(),
                "data": request.model_dump()
            }
            
            future = self.producer.send(
                self.detection_topic,
                key=message_key,
                value=message_value
            )
            future.get(timeout=10)
            return True
        except Exception as e:
            print(f"发送消息失败: {e}")
            return False
    
    def send_detection_result(self, result: DetectionResultData, request_id: str) -> bool:
        """
        发送检测结果到Kafka
        """
        if not self.producer:
            return False
        
        try:
            message_key = f"res_{request_id}"
            message_value = {
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": result.model_dump()
            }
            
            future = self.producer.send(
                self.result_topic,
                key=message_key,
                value=message_value
            )
            future.get(timeout=10)
            return True
        except Exception as e:
            print(f"发送结果失败: {e}")
            return False
    
    def start_consumer(self):
        """
        启动消费者线程
        """
        if self.running:
            return
        
        self.running = True
        self._init_consumer()
        
        if not self.consumer:
            self.running = False
            return
        
        self.consumer_thread = threading.Thread(target=self._consume_messages, daemon=True)
        self.consumer_thread.start()
        print("Kafka消费者线程已启动")
    
    def stop_consumer(self):
        """
        停止消费者线程
        """
        self.running = False
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)
        if self.consumer:
            self.consumer.close()
        print("Kafka消费者线程已停止")
    
    def _consume_messages(self):
        """
        消费消息并处理
        """
        if not self.consumer:
            return
        
        print("开始消费Kafka消息...")
        
        while self.running:
            try:
                for message in self.consumer:
                    if not self.running:
                        break
                    
                    try:
                        self._process_message(message.value)
                    except Exception as e:
                        print(f"处理消息失败: {e}")
            except Exception as e:
                print(f"消费者错误: {e}")
                # 重新初始化消费者
                self._init_consumer()
                continue
    
    def _process_message(self, message: Dict[str, Any]):
        """
        处理检测请求消息
        """
        request_id = message.get("request_id")
        request_data = message.get("data")
        
        if not request_id or not request_data:
            return
        
        print(f"处理检测请求: {request_id}")
        
        # 转换为DetectionRequest
        try:
            request = DetectionRequest(**request_data)
        except Exception as e:
            print(f"解析请求数据失败: {e}")
            return
        
        # 执行检测
        db = SessionLocal()
        try:
            # 使用默认租户ID
            detection_service = DetectionService(db, tenant_id=1)
            result = detection_service.detect_single(request)
            
            # 发送结果到Kafka
            self.send_detection_result(result, request_id)
            print(f"检测完成，结果已发送: {result.record_id}")
        except Exception as e:
            print(f"执行检测失败: {e}")
        finally:
            db.close()
    
    def close(self):
        """
        关闭所有连接
        """
        self.stop_consumer()
        if self.producer:
            self.producer.close()
        if self.admin_client:
            self.admin_client.close()
        print("Kafka服务已关闭")


class RealtimeDetectionService:
    """
    实时检测服务
    - 支持Kafka消费
    - 支持WebSocket推送
    - 支持滑动窗口统计
    - 支持实时告警
    """
    
    def __init__(self):
        self.kafka_service = KafkaService.get_instance()
        self.window_size = 60  # 60秒窗口
        self.window_data = {}
        self.window_lock = threading.Lock()
    
    def start(self):
        """
        启动实时检测服务
        """
        self.kafka_service.start_consumer()
        print("实时检测服务已启动")
    
    def stop(self):
        """
        停止实时检测服务
        """
        self.kafka_service.stop_consumer()
        print("实时检测服务已停止")
    
    def process_stream(self, stream_source: str):
        """
        处理流数据
        """
        pass
    
    def detect_with_window(self, records: List[Dict[str, Any]], window_size: int = None):
        """
        窗口检测
        """
        pass
    
    def trigger_alert(self, condition: Dict[str, Any]):
        """
        触发告警
        """
        pass
    
    def get_window_stats(self, window_size: int = 60):
        """
        获取窗口统计
        """
        pass


# 全局实例
kafka_service = KafkaService.get_instance()
realtime_service = RealtimeDetectionService()
