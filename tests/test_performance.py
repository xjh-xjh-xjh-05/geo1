"""
性能测试脚本 - 验证优化效果
"""
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.core.cache import cache, DetectionCache, MemoryCache


def test_memory_cache():
    """测试内存缓存性能"""
    print("=" * 50)
    print("内存缓存性能测试")
    print("=" * 50)
    
    mem_cache = MemoryCache(max_size=1000)
    
    # 写入测试
    start = time.time()
    for i in range(10000):
        mem_cache.set(f"key_{i}", {"data": f"value_{i}"})
    write_time = time.time() - start
    print(f"写入 10000 条数据: {write_time:.3f}s ({10000/max(write_time, 1e-9):.0f} ops/s)")
    
    # 读取测试
    start = time.time()
    hits = 0
    for i in range(10000):
        if mem_cache.get(f"key_{i}"):
            hits += 1
    read_time = time.time() - start
    print(f"读取 10000 条数据: {read_time:.3f}s ({10000/max(read_time, 1e-9):.0f} ops/s)")
    print(f"命中率: {hits/10000*100:.1f}%")
    
    # 统计信息
    stats = mem_cache.get_stats()
    print(f"缓存大小: {stats['size']}")
    print(f"命中率: {stats['hit_rate']*100:.1f}%")
    
    return write_time, read_time


def test_detection_cache():
    """测试检测结果缓存"""
    print("\n" + "=" * 50)
    print("检测结果缓存测试")
    print("=" * 50)
    
    test_poi = {
        "name": "测试餐厅",
        "address": "北京市朝阳区测试路123号",
        "latitude": 39.9042,
        "longitude": 116.4074
    }
    
    test_result = {
        "suspicion_score": 25.5,
        "risk_level": "low",
        "is_fake": False,
        "confidence": 0.85,
        "reasons": ["测试原因"]
    }
    
    # 写入
    start = time.time()
    for _ in range(1000):
        DetectionCache.set_result(test_poi, test_result)
    set_time = time.time() - start
    print(f"缓存检测结果 1000 次: {set_time:.3f}s")
    
    # 读取
    start = time.time()
    for _ in range(1000):
        result = DetectionCache.get_result(test_poi)
    get_time = time.time() - start
    print(f"读取检测结果 1000 次: {get_time:.3f}s")
    
    # 验证
    cached = DetectionCache.get_result(test_poi)
    print(f"缓存命中: {cached is not None}")
    if cached:
        print(f"缓存数据正确: {cached.get('suspicion_score') == test_result['suspicion_score']}")


def test_hybrid_cache():
    """测试混合缓存"""
    print("\n" + "=" * 50)
    print("混合缓存测试")
    print("=" * 50)
    
    stats = cache.get_stats()
    print(f"Redis 可用: {stats['redis_enabled']}")
    print(f"内存缓存大小: {stats['memory_cache_stats']['size']}")
    
    # 基本操作测试
    test_key = "test_performance_key"
    test_value = {"data": "test_value", "number": 12345}
    
    # 写入
    start = time.time()
    for i in range(1000):
        cache.set(f"{test_key}_{i}", test_value)
    set_time = time.time() - start
    print(f"写入 1000 条: {set_time:.3f}s")
    
    # 读取
    start = time.time()
    hits = 0
    for i in range(1000):
        if cache.get(f"{test_key}_{i}"):
            hits += 1
    get_time = time.time() - start
    print(f"读取 1000 条: {get_time:.3f}s, 命中: {hits}")


def test_preprocessing_performance():
    """测试预处理性能"""
    print("\n" + "=" * 50)
    print("数据预处理性能测试")
    print("=" * 50)
    
    from modules.preprocessing import DataPreprocessor
    
    preprocessor = DataPreprocessor()
    
    test_data = {
        "name": "测试POI名称-全网第一最好的餐厅",
        "address": "北京市朝阳区测试路123号",
        "latitude": 39.9042,
        "longitude": 116.4074,
        "phone": "13800138000",
        "business_hours": "09:00-22:00"
    }
    
    # 单次处理
    start = time.time()
    result = preprocessor.preprocess(test_data)
    single_time = time.time() - start
    print(f"单次预处理: {single_time*1000:.2f}ms")
    print(f"预处理结果: 有效={result.is_valid}, 警告={len(result.warnings)}")
    
    # 批量处理
    test_list = [test_data.copy() for _ in range(100)]
    start = time.time()
    results = preprocessor.batch_preprocess(test_list)
    batch_time = time.time() - start
    print(f"批量预处理 100 条: {batch_time:.3f}s ({100/max(batch_time, 1e-9):.0f} 条/秒)")


def test_feature_matching():
    """测试特征匹配性能"""
    print("\n" + "=" * 50)
    print("特征匹配性能测试")
    print("=" * 50)
    
    from modules.data_management import FeatureLibrary
    
    feature_lib = FeatureLibrary()
    
    test_text = "这是全网第一最好的餐厅，绝对是最优惠的，限时特价促销活动"
    
    start = time.time()
    for _ in range(100):
        matches = feature_lib.match_patterns(test_text)
    match_time = time.time() - start
    
    print(f"特征匹配 100 次: {match_time*1000:.2f}ms")
    print(f"匹配结果数量: {len(matches)}")
    
    # 特征库统计
    features = feature_lib.get_all_features()
    print(f"特征库大小: {len(features)} 条")


def run_all_tests():
    """运行所有性能测试"""
    print("\n" + "=" * 60)
    print("GEO虚假内容检测平台 - 性能测试报告")
    print("=" * 60)
    
    try:
        test_memory_cache()
    except Exception as e:
        print(f"内存缓存测试失败: {e}")
    
    try:
        test_detection_cache()
    except Exception as e:
        print(f"检测结果缓存测试失败: {e}")
    
    try:
        test_hybrid_cache()
    except Exception as e:
        print(f"混合缓存测试失败: {e}")
    
    try:
        test_preprocessing_performance()
    except Exception as e:
        print(f"预处理性能测试失败: {e}")
    
    try:
        test_feature_matching()
    except Exception as e:
        print(f"特征匹配测试失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
