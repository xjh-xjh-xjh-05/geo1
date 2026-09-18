"""
SimHash文本去重检测
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, replace
from collections import OrderedDict
import threading

try:
    from simhash import Simhash
    SIMHASH_AVAILABLE = True
except ImportError:
    SIMHASH_AVAILABLE = False

import sys
sys.path.insert(0, '..')
from config import text_config
from models import InputRecord


class SharedFingerprintStore:
    """
    跨请求共享的文本指纹库（有界 LRU、线程安全）。

    池化的 Scorer 在请求结束后会清空内部指纹，若只依赖实例内指纹，
    单条检测路径下永远查不到重复。此共享库让线上单条检测也能与
    近期历史内容比对，容量有界防止内存无限增长。
    """

    def __init__(self, max_size: int = 10000):
        self._fingerprints: "OrderedDict[str, int]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def add(self, record_id: str, hash_value: int):
        with self._lock:
            self._fingerprints[record_id] = hash_value
            self._fingerprints.move_to_end(record_id)
            if len(self._fingerprints) > self._max_size:
                self._fingerprints.popitem(last=False)

    def items(self):
        with self._lock:
            return list(self._fingerprints.items())

    def __len__(self):
        with self._lock:
            return len(self._fingerprints)

    def clear(self):
        with self._lock:
            self._fingerprints.clear()


@dataclass
class SimilarityResult:
    """相似度检测结果"""
    is_duplicate: bool
    similarity: float
    similar_records: List[str]  # 相似记录ID列表
    hamming_distance: int


class SimHashDetector:
    """SimHash去重检测器"""

    # 低于该长度（字符数）的文本只做精确匹配查重
    SHORT_TEXT_MIN_LENGTH = 20

    def __init__(self, config=None, threshold: int = None,
                 shared_store: Optional[SharedFingerprintStore] = None):
        # 每个实例持有配置副本，避免污染全局单例
        self.config = config if config is not None else replace(text_config)
        self.threshold = threshold or self.config.simhash_threshold
        self.fingerprints: Dict[str, int] = {}  # 实例内指纹（批次内比对）
        self.shared_store = shared_store  # 共享指纹库（跨批次/跨请求比对）

    def _compute_simhash(self, text: str) -> Optional[int]:
        """计算文本的SimHash值"""
        if not SIMHASH_AVAILABLE:
            # 如果simhash库不可用，使用简单的hash替代
            return self._simple_hash(text)

        try:
            # 分词（简化版）
            features = [text[i:i+2] for i in range(len(text)-1)]
            simhash = Simhash(features)
            return simhash.value
        except Exception:
            return self._simple_hash(text)

    def _simple_hash(self, text: str) -> int:
        """简单hash函数（备用）"""
        result = 0
        for char in text:
            result = (result * 31 + ord(char)) & 0xFFFFFFFF
        return result

    def _hamming_distance(self, hash1: int, hash2: int) -> int:
        """计算汉明距离"""
        xor = hash1 ^ hash2
        distance = 0
        while xor:
            distance += 1
            xor &= xor - 1
        return distance

    def check(self, record: InputRecord) -> SimilarityResult:
        """
        检查单条记录是否与已有记录重复

        Args:
            record: 输入记录

        Returns:
            相似度检测结果
        """
        text = record.content.text
        current_hash = self._compute_simhash(text)

        # SimHash基于字符bigram，文本过短时指纹碰撞严重（任意两短文本
        # 距离都可能≤3），只做精确匹配判断
        exact_match_only = len(text) < self.SHORT_TEXT_MIN_LENGTH

        similar_records = []
        min_distance = float('inf')

        # 与实例内指纹比对（跳过自身，避免重复检测同一记录时自匹配）
        candidates = list(self.fingerprints.items())
        if self.shared_store is not None:
            seen = {rid for rid, _ in candidates}
            for rid, existing_hash in self.shared_store.items():
                if rid not in seen:
                    candidates.append((rid, existing_hash))

        for stored_id, existing_hash in candidates:
            if stored_id == record.record_id:
                continue
            distance = self._hamming_distance(current_hash, existing_hash)

            if exact_match_only:
                if distance == 0:
                    similar_records.append(stored_id)
                    min_distance = min(min_distance, distance)
                continue

            if distance <= self.threshold:
                similar_records.append(stored_id)
                min_distance = min(min_distance, distance)

        # 计算相似度（汉明距离越小，相似度越高）
        if similar_records:
            # 假设64位SimHash，距离0表示完全相同，距离64表示完全不同
            similarity = 1 - (min_distance / 64.0)
        else:
            similarity = 0.0

        # 存储当前记录的指纹（实例内 + 共享库）
        self.fingerprints[record.record_id] = current_hash
        if self.shared_store is not None:
            self.shared_store.add(record.record_id, current_hash)

        return SimilarityResult(
            is_duplicate=len(similar_records) > 0,
            similarity=similarity,
            similar_records=similar_records,
            hamming_distance=int(min_distance) if similar_records else 64
        )

    def batch_check(self, records: List[InputRecord]) -> Dict[str, SimilarityResult]:
        """
        批量检查重复

        Args:
            records: 记录列表

        Returns:
            {record_id: SimilarityResult}
        """
        results = {}

        for record in records:
            results[record.record_id] = self.check(record)

        return results

    def get_duplicate_groups(self, records: List[InputRecord]) -> List[List[str]]:
        """
        获取重复分组

        Args:
            records: 记录列表

        Returns:
            分组列表，每组包含相似的记录ID
        """
        # 先进行批量检查
        self.fingerprints.clear()
        self.batch_check(records)

        # 使用并查集进行分组
        parent = {r.record_id: r.record_id for r in records}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # 对相似的记录进行合并
        hash_values = {r.record_id: self._compute_simhash(r.content.text) for r in records}

        record_ids = list(hash_values.keys())
        for i in range(len(record_ids)):
            for j in range(i + 1, len(record_ids)):
                id1, id2 = record_ids[i], record_ids[j]
                distance = self._hamming_distance(hash_values[id1], hash_values[id2])
                if distance <= self.threshold:
                    union(id1, id2)

        # 收集分组
        groups = {}
        for record_id in record_ids:
            root = find(record_id)
            if root not in groups:
                groups[root] = []
            groups[root].append(record_id)

        # 只返回有重复的分组
        return [group for group in groups.values() if len(group) > 1]

    def clear(self):
        """清空实例内已存储的指纹（共享库需显式调用 clear_shared）"""
        self.fingerprints.clear()

    def clear_shared(self):
        """清空共享指纹库"""
        if self.shared_store is not None:
            self.shared_store.clear()
