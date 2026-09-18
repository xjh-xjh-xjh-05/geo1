"""
语义向量聚类异常检测
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, replace
from collections import OrderedDict
import threading

import numpy as np

import sys
sys.path.insert(0, '..')
from config import text_config
from models import InputRecord


class SharedEmbeddingStore:
    """
    跨请求共享的文本向量库（有界 LRU、线程安全）。

    池化的 Scorer 在请求结束后会清空内部向量，若只依赖实例内向量，
    单条检测路径下永远无法与历史内容聚类比对。此共享库让线上单条
    检测也能发现与近期内容高度相似的批量刷量行为。
    """

    def __init__(self, max_size: int = 5000):
        self._embeddings: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def add(self, record_id: str, embedding: np.ndarray):
        vec = np.asarray(embedding, dtype=np.float32)
        with self._lock:
            self._embeddings[record_id] = vec
            self._embeddings.move_to_end(record_id)
            if len(self._embeddings) > self._max_size:
                self._embeddings.popitem(last=False)

    def get(self, record_id: str) -> Optional[np.ndarray]:
        with self._lock:
            return self._embeddings.get(record_id)

    def items(self):
        with self._lock:
            return list(self._embeddings.items())

    def __len__(self):
        with self._lock:
            return len(self._embeddings)

    def clear(self):
        with self._lock:
            self._embeddings.clear()


@dataclass
class ClusterResult:
    """聚类结果"""
    cluster_id: int
    is_anomaly: bool
    anomaly_score: float
    cluster_size: int
    similar_records: List[str]


class SemanticCluster:
    """语义向量聚类检测器"""

    def __init__(self, config=None, similarity_threshold: float = None,
                 shared_store: Optional[SharedEmbeddingStore] = None):
        # 每个实例持有配置副本，避免污染全局单例
        self.config = config if config is not None else replace(text_config)
        self.similarity_threshold = similarity_threshold or self.config.semantic_similarity_threshold
        self.encoder = None
        self.embeddings: Dict[str, np.ndarray] = {}  # 实例内向量（批次内比对）
        self.shared_store = shared_store  # 共享向量库（跨批次/跨请求比对）

        # 如果不启用在线模型，直接使用简化模式
        if not getattr(self.config, 'use_online_model', False):
            self.encoder = "simple"

    def _load_encoder(self):
        """延迟加载编码器"""
        if self.encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                # 使用中文模型 - 设置本地缓存和超时
                self.encoder = SentenceTransformer(
                    'paraphrase-multilingual-MiniLM-L12-v2',
                    cache_folder="./models/cache",
                    device='cpu'
                )
            except ImportError:
                print("警告：sentence-transformers 未安装，使用简化模式")
                self.encoder = "simple"
            except Exception as e:
                print(f"警告：模型加载失败 ({str(e)})，使用简化模式")
                self.encoder = "simple"

    def _encode(self, text: str) -> np.ndarray:
        """编码文本为向量"""
        self._load_encoder()

        if self.encoder == "simple":
            # 简化模式：使用字符频率作为特征
            return self._simple_encode(text)

        try:
            embedding = self.encoder.encode([text])[0]
            return embedding
        except Exception:
            return self._simple_encode(text)

    def _encode_many(self, texts: List[str]) -> np.ndarray:
        """批量编码文本，在线模型失败时整批回退到简化向量。"""
        self._load_encoder()
        if self.encoder == "simple":
            return np.asarray([self._simple_encode(text) for text in texts])
        try:
            return np.asarray(
                self.encoder.encode(texts, batch_size=32, show_progress_bar=False),
                dtype=np.float32,
            )
        except Exception:
            return np.asarray([self._simple_encode(text) for text in texts])

    def _simple_encode(self, text: str) -> np.ndarray:
        """简化的文本编码（备用方案）"""
        # 使用字符频率作为特征向量
        feature_size = 256
        features = np.zeros(feature_size)

        for char in text:
            idx = ord(char) % feature_size
            features[idx] += 1

        # 归一化
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm

        return features

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    def fit_predict(self, records: List[InputRecord]) -> Dict[str, ClusterResult]:
        """
        对记录进行聚类分析

        Args:
            records: 记录列表

        Returns:
            {record_id: ClusterResult}
        """
        if len(records) == 0:
            return {}

        # 编码所有文本
        texts = [r.content.text for r in records]
        embeddings = self._encode_many(texts)

        # 存储embeddings（实例内 + 共享库）
        for i, record in enumerate(records):
            self.embeddings[record.record_id] = embeddings[i]
            if self.shared_store is not None:
                self.shared_store.add(record.record_id, embeddings[i])

        # 使用DBSCAN聚类
        results = self._dbscan_clustering(records, embeddings)

        return results

    def _dbscan_clustering(self, records: List[InputRecord],
                          embeddings: np.ndarray) -> Dict[str, ClusterResult]:
        """DBSCAN 聚类"""
        try:
            from sklearn.cluster import DBSCAN
            from sklearn.metrics.pairwise import cosine_similarity

            # 计算相似度矩阵
            similarity_matrix = cosine_similarity(embeddings)

            # 转换为距离矩阵，并确保非负
            distance_matrix = 1 - similarity_matrix
            distance_matrix = np.clip(distance_matrix, 0, 2)  # 限制在 [0, 2] 范围内，避免负值
            
            # 确保对角线为 0
            np.fill_diagonal(distance_matrix, 0)

            # DBSCAN 聚类
            clustering = DBSCAN(
                eps=1 - self.similarity_threshold,  # 距离阈值
                min_samples=2,
                metric='precomputed'
            )
            labels = clustering.fit_predict(distance_matrix)

        except ImportError:
            # sklearn 不可用时的简化聚类
            labels = self._simple_clustering(embeddings)
        except Exception as e:
            # 其他错误时使用简化聚类
            print(f"DBSCAN 聚类失败：{str(e)}，使用简化聚类")
            labels = self._simple_clustering(embeddings)

        # 分析聚类结果
        results = {}
        cluster_counts = {}

        for i, record in enumerate(records):
            cluster_id = int(labels[i])
            if cluster_id not in cluster_counts:
                cluster_counts[cluster_id] = 0
            cluster_counts[cluster_id] += 1

        # 标记异常
        for i, record in enumerate(records):
            cluster_id = int(labels[i])
            cluster_size = cluster_counts[cluster_id]

            # 噪声点（cluster_id = -1）或大簇可能是刷量
            is_anomaly = False
            anomaly_score = 0.0

            if cluster_id == -1:
                # 噪声点，可能是独特内容
                is_anomaly = False
                anomaly_score = 0.0
            elif cluster_size > 5:
                # 大簇，可能是批量刷量
                is_anomaly = True
                anomaly_score = min(cluster_size / 20.0, 1.0)  # 最多1.0

            # 找相似记录
            similar_records = []
            for j, other in enumerate(records):
                if i != j and labels[i] == labels[j]:
                    similar_records.append(other.record_id)

            results[record.record_id] = ClusterResult(
                cluster_id=cluster_id,
                is_anomaly=is_anomaly,
                anomaly_score=anomaly_score,
                cluster_size=cluster_size,
                similar_records=similar_records[:10]  # 最多返回10个
            )

        return results

    def _simple_clustering(self, embeddings: np.ndarray) -> np.ndarray:
        """简化聚类（备用方案）"""
        n = len(embeddings)
        labels = np.arange(n)  # 每个点一个簇

        # 简单的相似度聚类
        threshold = self.similarity_threshold
        current_label = 0

        for i in range(n):
            if labels[i] == i:  # 未被分配
                for j in range(i + 1, n):
                    if labels[j] == j:  # 未被分配
                        sim = self._cosine_similarity(embeddings[i], embeddings[j])
                        if sim >= threshold:
                            labels[j] = current_label
                labels[i] = current_label
                current_label += 1

        return labels

    def check(self, record: InputRecord,
              existing_records: List[InputRecord] = None) -> ClusterResult:
        """
        检查单条记录

        Args:
            record: 输入记录
            existing_records: 已有记录（用于比较）

        Returns:
            聚类结果
        """
        # 没有历史数据且无共享向量库时无法聚类
        has_shared = self.shared_store is not None and len(self.shared_store) > 0
        if (existing_records is None or len(existing_records) == 0) and not has_shared:
            return ClusterResult(
                cluster_id=-1,
                is_anomaly=False,
                anomaly_score=0.0,
                cluster_size=1,
                similar_records=[]
            )

        # 编码当前文本
        current_embedding = self._encode(record.content.text)

        # 找相似的记录：实例内向量和共享库合并（跳过自身，避免自匹配）
        candidates = list(self.embeddings.items())
        if self.shared_store is not None:
            seen = {rid for rid, _ in candidates}
            for rid, emb in self.shared_store.items():
                if rid not in seen:
                    candidates.append((rid, emb))

        similar_records = []
        for existing_id, existing_embedding in candidates:
            if existing_id == record.record_id:
                continue
            sim = self._cosine_similarity(current_embedding, existing_embedding)

            if sim >= self.similarity_threshold:
                similar_records.append((existing_id, sim))

        # 按相似度排序
        similar_records.sort(key=lambda x: x[1], reverse=True)
        similar_ids = [r[0] for r in similar_records[:10]]

        # 判断是否异常
        cluster_size = len(similar_records) + 1
        is_anomaly = cluster_size > 5
        anomaly_score = min(cluster_size / 20.0, 1.0) if is_anomaly else 0.0

        # 存储当前embedding（实例内 + 共享库）
        self.embeddings[record.record_id] = current_embedding
        if self.shared_store is not None:
            self.shared_store.add(record.record_id, current_embedding)

        return ClusterResult(
            cluster_id=-1,  # 单条检查无法确定簇ID
            is_anomaly=is_anomaly,
            anomaly_score=anomaly_score,
            cluster_size=cluster_size,
            similar_records=similar_ids
        )

    @property
    def backend_name(self) -> str:
        if self.encoder == "simple":
            return "character-frequency-fallback"
        if self.encoder is not None:
            return "sentence-transformer"
        return (
            "sentence-transformer-pending"
            if getattr(self.config, "use_online_model", False)
            else "character-frequency-fallback"
        )

    def clear(self):
        """清空实例内已存储的向量（共享库需显式调用 clear_shared）"""
        self.embeddings.clear()

    def clear_shared(self):
        """清空共享向量库"""
        if self.shared_store is not None:
            self.shared_store.clear()
