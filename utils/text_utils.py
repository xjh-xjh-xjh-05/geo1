"""
文本处理工具函数
"""
import re
from typing import List, Dict
from collections import Counter


def extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """
    提取文本中的关键词（简化版，实际应用可用jieba TF-IDF）

    Args:
        text: 输入文本
        top_n: 返回前N个关键词

    Returns:
        关键词列表
    """
    # 简单分词：按标点和空格分割
    # 实际应用中应使用jieba
    words = re.findall(r'[\u4e00-\u9fa5]+', text)

    # 过滤停用词（简化版）
    stopwords = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人',
                 '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去'}

    words = [w for w in words if w not in stopwords and len(w) >= 2]

    # 统计词频
    word_freq = Counter(words)

    return [word for word, _ in word_freq.most_common(top_n)]


def calculate_keyword_density(text: str, keyword: str) -> float:
    """
    计算关键词密度

    Args:
        text: 输入文本
        keyword: 关键词

    Returns:
        关键词密度（0-1）
    """
    if not text:
        return 0.0

    count = text.count(keyword)
    total_chars = len(text)

    return count / total_chars if total_chars > 0 else 0.0


def detect_keyword_stuffing(text: str, max_repeat: int = 3) -> Dict:
    """
    检测关键词堆砌

    Args:
        text: 输入文本
        max_repeat: 最大允许重复次数

    Returns:
        检测结果
    """
    result = {
        'has_stuffing': False,
        'stuffed_keywords': [],
        'repeat_counts': {}
    }

    # 检测连续重复的词
    pattern = r'(.)\1{2,}'
    matches = re.finditer(pattern, text)

    for match in matches:
        word = match.group(0)
        if len(word) >= max_repeat:
            result['has_stuffing'] = True
            result['stuffed_keywords'].append(word[:3] + '...')
            result['repeat_counts'][word[:3]] = len(word)

    # 检测词组重复
    word_pattern = r'([\u4e00-\u9fa5]{2,})\1{1,}'
    word_matches = re.finditer(word_pattern, text)

    for match in word_matches:
        word = match.group(1)
        result['has_stuffing'] = True
        if word not in result['stuffed_keywords']:
            result['stuffed_keywords'].append(word)
            result['repeat_counts'][word] = len(match.group(0)) // len(word)

    return result


def normalize_text(text: str) -> str:
    """
    文本标准化

    Args:
        text: 输入文本

    Returns:
        标准化后的文本
    """
    # 去除多余空格
    text = re.sub(r'\s+', '', text)

    # 统一标点
    text = text.replace('，', ',').replace('。', '.')
    text = text.replace('！', '!').replace('？', '?')

    return text.strip()


def calculate_text_features(text: str) -> Dict:
    """
    计算文本特征

    Args:
        text: 输入文本

    Returns:
        特征字典
    """
    return {
        'length': len(text),
        'char_count': len(text),
        'word_count': len(re.findall(r'[\u4e00-\u9fa5]+', text)),
        'punctuation_count': len(re.findall(r'[，。！？、；：""''（）]', text)),
        'digit_count': len(re.findall(r'\d', text)),
        'exclamation_count': text.count('!') + text.count('！'),
    }
