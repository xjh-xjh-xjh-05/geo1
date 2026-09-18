"""
评分合并工具
"""
from typing import Iterable


def combine_severities(severities: Iterable[float]) -> float:
    """
    将多个异常严重度合并为 0-100 的分数。

    使用概率并集 1 - Π(1 - s_i)，保证合并结果随异常数量和单条严重度
    单调递增且有上界100，避免"取平均"时异常越多分数反而越低的问题：
      - 单条 0.6           -> 60
      - 0.6 + 0.3          -> 72（平均只有 45）
      - 0.3 x 3            -> 65.7（平均只有 30）
    """
    combined = 0.0
    for s in severities:
        try:
            s = float(s)
        except (TypeError, ValueError):
            continue
        s = min(max(s, 0.0), 1.0)
        combined = combined + s - combined * s
    return round(combined * 100, 2)
