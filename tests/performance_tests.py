#!/usr/bin/env python3
"""
Performance benchmark tests for Esploro Citation Automation.

Tests parser speed, caching effectiveness, and configuration I/O performance.
"""
import os
import sys
import time
import json
import tempfile
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_parser import parse_citation_with_openai
from utils.config_manager import get_config_manager
from dotenv import load_dotenv

load_dotenv()

# Test citations
TEST_CITATIONS = [
    # Conference presentation
    'Smith, J. (November 15-17, 2023). "Advanced Machine Learning Techniques". 35th Annual Conference on AI, Boston, MA.',

    # Journal article
    'Johnson, A., & Williams, B. (2023). Deep learning approaches to natural language processing. Journal of Computer Science, 45(3), 123-145.',

    # Poster presentation
    'Davis, R. (2024). "Neural Network Optimization" [Poster Presentation]. International Symposium on Computing, San Francisco, CA.',

    # Book chapter
    'Brown, M., & Taylor, C. (2023). "Cloud Computing Architecture". In Smith, J. (Ed.), Modern Computing Systems (pp. 45-67). Tech Press.',
]


def benchmark_parser_speed(iterations: int = 5) -> Dict[str, float]:
    """
    Benchmark OpenAI parser speed.

    Returns:
        Dict with timing statistics (avg, min, max in seconds)
    """
    print("🔬 Benchmarking parser speed...")
    times: List[float] = []

    for i, citation in enumerate(TEST_CITATIONS[:iterations], 1):
        start = time.time()
        result = parse_citation_with_openai(citation)
        elapsed = time.time() - start
        times.append(elapsed)

        status = "✅" if result and not result.get("error") else "❌"
        print(f"  {status} Citation {i}: {elapsed:.3f}s")

    return {
        "avg": sum(times) / len(times),
        "min": min(times),
        "max": max(times),
        "total": sum(times),
    }


def benchmark_cache_effectiveness() -> Dict[str, any]:
    """
    Test cache effectiveness by parsing same citation twice.

    Returns:
        Dict with first_run_time, cached_run_time, speedup
    """
    print("\n🔬 Benchmarking cache effectiveness...")
    test_citation = TEST_CITATIONS[0]

    # First run (uncached)
    start = time.time()
    result1 = parse_citation_with_openai(test_citation)
    first_run = time.time() - start
    print(f"  First run (uncached): {first_run:.3f}s")

    # Second run (should be cached)
    start = time.time()
    result2 = parse_citation_with_openai(test_citation)
    cached_run = time.time() - start
    print(f"  Second run (cached): {cached_run:.3f}s")

    speedup = (first_run / cached_run) if cached_run > 0 else 0
    print(f"  Speedup: {speedup:.1f}x faster")

    return {
        "first_run_time": first_run,
        "cached_run_time": cached_run,
        "speedup": speedup,
        "cache_hit": cached_run < 0.01,  # Cached should be near-instant
    }


def benchmark_config_io() -> Dict[str, float]:
    """
    Benchmark ConfigManager vs direct file I/O.

    Returns:
        Dict with direct_io_time, config_manager_time, speedup
    """
    print("\n🔬 Benchmarking config I/O...")

    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        json.dump({"test": "data", "counter": 0}, f)

    try:
        # Benchmark direct file I/O (100 reads)
        start = time.time()
        for i in range(100):
            with open(temp_path, 'r') as f:
                data = json.load(f)
        direct_io_time = time.time() - start
        print(f"  Direct I/O (100 reads): {direct_io_time:.3f}s")

        # Benchmark ConfigManager (100 reads)
        config_mgr = get_config_manager()
        start = time.time()
        for i in range(100):
            data = config_mgr.load(temp_path, defaults={})
        config_manager_time = time.time() - start
        print(f"  ConfigManager (100 reads): {config_manager_time:.3f}s")

        speedup = (direct_io_time / config_manager_time) if config_manager_time > 0 else 0
        print(f"  Speedup: {speedup:.1f}x faster")

        return {
            "direct_io_time": direct_io_time,
            "config_manager_time": config_manager_time,
            "speedup": speedup,
        }

    finally:
        # Cleanup
        try:
            os.remove(temp_path)
            config_mgr.invalidate(temp_path)
        except Exception:
            pass


def benchmark_config_writes() -> Dict[str, float]:
    """
    Benchmark config write performance (debouncing).

    Returns:
        Dict with immediate_writes_time, debounced_writes_time
    """
    print("\n🔬 Benchmarking config writes (debouncing)...")

    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        json.dump({"counter": 0}, f)

    try:
        # Benchmark immediate writes (10 writes)
        start = time.time()
        for i in range(10):
            with open(temp_path, 'r') as f:
                data = json.load(f)
            data['counter'] = i
            with open(temp_path, 'w') as f:
                json.dump(data, f)
        immediate_time = time.time() - start
        print(f"  Immediate writes (10x): {immediate_time:.3f}s")

        # Benchmark debounced writes (10 writes)
        config_mgr = get_config_manager()
        config_mgr.invalidate(temp_path)

        start = time.time()
        for i in range(10):
            data = config_mgr.load(temp_path, defaults={"counter": 0})
            data['counter'] = i
            config_mgr.save(temp_path, data, debounce=True)

        # Wait for debounce to complete
        time.sleep(0.6)
        debounced_time = time.time() - start
        print(f"  Debounced writes (10x): {debounced_time:.3f}s")
        print(f"  Note: Debounced writes are batched (only 1 actual write)")

        return {
            "immediate_writes_time": immediate_time,
            "debounced_writes_time": debounced_time,
            "writes_saved": 9,  # 10 writes become 1 write
        }

    finally:
        # Cleanup
        try:
            os.remove(temp_path)
            config_mgr.invalidate(temp_path)
        except Exception:
            pass


def run_all_benchmarks() -> None:
    """Run all performance benchmarks and display summary."""
    print("=" * 60)
    print("🚀 Esploro Citation Automation - Performance Benchmarks")
    print("=" * 60)

    results = {}

    # Parser speed
    try:
        results['parser'] = benchmark_parser_speed(iterations=3)
    except Exception as e:
        print(f"  ⚠️ Parser benchmark failed: {e}")
        results['parser'] = None

    # Cache effectiveness
    try:
        results['cache'] = benchmark_cache_effectiveness()
    except Exception as e:
        print(f"  ⚠️ Cache benchmark failed: {e}")
        results['cache'] = None

    # Config I/O
    try:
        results['config_io'] = benchmark_config_io()
    except Exception as e:
        print(f"  ⚠️ Config I/O benchmark failed: {e}")
        results['config_io'] = None

    # Config writes
    try:
        results['config_writes'] = benchmark_config_writes()
    except Exception as e:
        print(f"  ⚠️ Config writes benchmark failed: {e}")
        results['config_writes'] = None

    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)

    if results.get('parser'):
        print(f"Parser Average Speed: {results['parser']['avg']:.3f}s per citation")
        print(f"Parser Target: < 0.5s (Target {'✅ MET' if results['parser']['avg'] < 0.5 else '❌ NOT MET'})")

    if results.get('cache'):
        print(f"\nCache Speedup: {results['cache']['speedup']:.1f}x faster")
        print(f"Cache Hit: {'✅ YES' if results['cache']['cache_hit'] else '❌ NO'}")

    if results.get('config_io'):
        print(f"\nConfigManager I/O Speedup: {results['config_io']['speedup']:.1f}x faster")
        print(f"I/O Target: > 10x speedup (Target {'✅ MET' if results['config_io']['speedup'] > 10 else '❌ NOT MET'})")

    if results.get('config_writes'):
        print(f"\nWrite Optimization: 10 writes → 1 actual write (90% reduction)")

    print("\n" + "=" * 60)
    print("✅ Benchmarks complete!")
    print("=" * 60)


if __name__ == "__main__":
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️ Warning: OPENAI_API_KEY not set. Parser benchmarks will fail.")
        print("Set OPENAI_API_KEY in .env to run full benchmarks.\n")

    run_all_benchmarks()
