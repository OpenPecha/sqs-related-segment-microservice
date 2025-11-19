#!/usr/bin/env python3
"""
Temporary test script for Dragonfly cache.

This file tests all aspects of the Dragonfly cache implementation.
Run: python test_dragonfly_cache.py

⚠️ DELETE THIS FILE AFTER TESTING ⚠️
"""

import sys
import time
import os
from app.redis_cache import DragonflyCache, get_dragonfly_client
from app.config import get

# ANSI color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text):
    """Print a formatted header."""
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")


def print_test(test_name):
    """Print test name."""
    print(f"{BOLD}Testing: {test_name}{RESET}")


def print_pass(message):
    """Print success message."""
    print(f"  {GREEN}✓ PASS:{RESET} {message}")


def print_fail(message):
    """Print failure message."""
    print(f"  {RED}✗ FAIL:{RESET} {message}")


def print_info(message):
    """Print info message."""
    print(f"  {YELLOW}ℹ INFO:{RESET} {message}")


def test_connection():
    """Test 1: Connection to Dragonfly"""
    print_header("TEST 1: Connection")
    print_test("Dragonfly connection establishment")
    
    try:
        # Check if DRAGONFLY_URL is configured
        dragonfly_url = get("DRAGONFLY_URL")
        if not dragonfly_url:
            print_fail("DRAGONFLY_URL not configured in environment")
            print_info("Add DRAGONFLY_URL to your .env file")
            return False
        
        print_info(f"DRAGONFLY_URL: {dragonfly_url[:30]}...")
        
        # Try to get client
        client = get_dragonfly_client()
        if not client:
            print_fail("Failed to create Dragonfly client")
            return False
        
        print_pass("Dragonfly client created successfully")
        
        # Test ping
        client.ping()
        print_pass("Successfully pinged Dragonfly server")
        
        return True
        
    except Exception as e:
        print_fail(f"Connection failed: {str(e)}")
        return False


def test_basic_operations():
    """Test 2: Basic SET and GET operations"""
    print_header("TEST 2: Basic Operations")
    
    cache = DragonflyCache()
    
    # Test 2.1: SET operation
    print_test("SET operation")
    test_data = {"name": "Test User", "id": 123, "active": True}
    
    try:
        result = cache.set("test_key_basic", test_data)
        if result:
            print_pass("Successfully stored data in cache")
        else:
            print_fail("SET operation returned False")
            return False
    except Exception as e:
        print_fail(f"SET operation failed: {str(e)}")
        return False
    
    # Test 2.2: GET operation (cache HIT)
    print_test("GET operation (cache HIT)")
    try:
        retrieved = cache.get("test_key_basic")
        if retrieved == test_data:
            print_pass("Successfully retrieved data from cache")
            print_info(f"Original: {test_data}")
            print_info(f"Retrieved: {retrieved}")
        else:
            print_fail(f"Data mismatch! Original: {test_data}, Retrieved: {retrieved}")
            return False
    except Exception as e:
        print_fail(f"GET operation failed: {str(e)}")
        return False
    
    # Test 2.3: GET operation (cache MISS)
    print_test("GET operation (cache MISS)")
    try:
        missing = cache.get("non_existent_key_12345")
        if missing is None:
            print_pass("Cache MISS returned None as expected")
        else:
            print_fail(f"Expected None for missing key, got: {missing}")
            return False
    except Exception as e:
        print_fail(f"Cache MISS test failed: {str(e)}")
        return False
    
    return True


def test_ttl():
    """Test 3: TTL (Time-To-Live) functionality"""
    print_header("TEST 3: TTL (Time-To-Live)")
    
    cache = DragonflyCache()
    
    print_test("TTL expiration (5 seconds)")
    print_info("Setting key with 5-second TTL...")
    
    test_data = {"message": "This will expire in 5 seconds"}
    
    try:
        # Set with 5-second TTL
        cache.set("test_key_ttl", test_data, ttl=5)
        print_pass("Key set with TTL=5s")
        
        # Immediately retrieve (should exist)
        immediate = cache.get("test_key_ttl")
        if immediate == test_data:
            print_pass("Key exists immediately after setting")
        else:
            print_fail("Key not found immediately after setting")
            return False
        
        # Wait 6 seconds
        print_info("Waiting 6 seconds for expiration...")
        time.sleep(6)
        
        # Try to retrieve (should be expired)
        expired = cache.get("test_key_ttl")
        if expired is None:
            print_pass("Key expired after TTL as expected")
        else:
            print_fail(f"Key still exists after TTL! Value: {expired}")
            return False
        
        return True
        
    except Exception as e:
        print_fail(f"TTL test failed: {str(e)}")
        return False


def test_complex_data():
    """Test 4: Complex data structures (like alignment pairs)"""
    print_header("TEST 4: Complex Data Structures")
    
    cache = DragonflyCache()
    
    # Simulate alignment pairs data
    print_test("List of dictionaries (alignment pairs)")
    
    alignment_pairs = [
        {
            "manifestation_id": "tibetan_123",
            "alignment_1_id": "align_001",
            "alignment_2_id": "align_002"
        },
        {
            "manifestation_id": "tibetan_123",
            "alignment_1_id": "align_003",
            "alignment_2_id": "align_004"
        },
        {
            "manifestation_id": "tibetan_123",
            "alignment_1_id": "align_005",
            "alignment_2_id": "align_006"
        }
    ]
    
    try:
        # Store complex data
        cache.set("test_alignment_pairs", alignment_pairs)
        print_pass("Stored list of dictionaries")
        
        # Retrieve and verify
        retrieved = cache.get("test_alignment_pairs")
        if retrieved == alignment_pairs:
            print_pass("Retrieved data matches original")
            print_info(f"Stored {len(alignment_pairs)} alignment pairs")
        else:
            print_fail("Data mismatch after retrieval")
            return False
        
        # Verify data structure integrity
        if isinstance(retrieved, list) and isinstance(retrieved[0], dict):
            print_pass("Data structure integrity maintained")
            print_info(f"First item: {retrieved[0]}")
        else:
            print_fail("Data structure corrupted")
            return False
        
    except Exception as e:
        print_fail(f"Complex data test failed: {str(e)}")
        return False
    
    # Test nested structures
    print_test("Nested data structures")
    nested_data = {
        "job_id": "job_123",
        "results": [
            {
                "segment_id": "seg_1",
                "related": [
                    {"id": "rel_1", "score": 0.95},
                    {"id": "rel_2", "score": 0.87}
                ]
            }
        ]
    }
    
    try:
        cache.set("test_nested", nested_data)
        retrieved_nested = cache.get("test_nested")
        
        if retrieved_nested == nested_data:
            print_pass("Nested structure retrieved correctly")
        else:
            print_fail("Nested structure mismatch")
            return False
        
    except Exception as e:
        print_fail(f"Nested structure test failed: {str(e)}")
        return False
    
    return True


def test_integration():
    """Test 5: Integration test (simulated Neo4j caching)"""
    print_header("TEST 5: Integration Test (Simulated)")
    
    cache = DragonflyCache(default_ttl=3600)
    
    print_test("Simulating Neo4j alignment pair caching")
    
    manifestation_id = "test_manifestation_999"
    cache_key = f"alignment_pairs_by_manifestation_{manifestation_id}"
    
    # Simulate Neo4j query data
    neo4j_result = [
        {"manifestation_id": manifestation_id, "alignment_1_id": "a1", "alignment_2_id": "a2"},
        {"manifestation_id": manifestation_id, "alignment_1_id": "a3", "alignment_2_id": "a4"},
    ]
    
    try:
        # First request (cache MISS - would query Neo4j)
        print_info("First request (cache MISS)...")
        start_time = time.time()
        
        cached = cache.get(cache_key)
        if cached is None:
            print_pass("Cache MISS as expected (first request)")
            # Simulate Neo4j query delay
            time.sleep(0.1)  # Simulate 100ms Neo4j query
            cache.set(cache_key, neo4j_result)
            result = neo4j_result
        else:
            print_info("Cache HIT (data already exists)")
            result = cached
        
        first_request_time = (time.time() - start_time) * 1000
        print_info(f"First request took: {first_request_time:.2f}ms")
        
        # Second request (cache HIT - no Neo4j query)
        print_info("Second request (cache HIT)...")
        start_time = time.time()
        
        cached = cache.get(cache_key)
        if cached:
            print_pass("Cache HIT as expected (second request)")
            result = cached
        else:
            print_fail("Expected cache HIT but got MISS")
            return False
        
        second_request_time = (time.time() - start_time) * 1000
        print_info(f"Second request took: {second_request_time:.2f}ms")
        
        # Calculate performance improvement
        if first_request_time > second_request_time:
            improvement = ((first_request_time - second_request_time) / first_request_time) * 100
            print_pass(f"Cache improved performance by {improvement:.1f}%")
        else:
            print_info("Performance similar (Neo4j simulation too fast)")
        
        # Verify data integrity
        if result == neo4j_result:
            print_pass("Data integrity maintained through cache")
        else:
            print_fail("Data corrupted through cache")
            return False
        
        return True
        
    except Exception as e:
        print_fail(f"Integration test failed: {str(e)}")
        return False


def test_error_handling():
    """Test 6: Error handling and graceful degradation"""
    print_header("TEST 6: Error Handling")
    
    print_test("Graceful degradation without Dragonfly")
    
    # Temporarily unset DRAGONFLY_URL
    original_url = os.environ.get('DRAGONFLY_URL')
    
    try:
        # Test with no URL
        os.environ.pop('DRAGONFLY_URL', None)
        
        cache = DragonflyCache()
        
        # Operations should return None/False but not crash
        result = cache.set("test_key", {"data": "test"})
        if result is False:
            print_pass("SET returns False when Dragonfly unavailable")
        else:
            print_info("SET behavior differs (may still work)")
        
        value = cache.get("test_key")
        if value is None:
            print_pass("GET returns None when Dragonfly unavailable")
        else:
            print_info("GET behavior differs (may still work)")
        
        print_pass("Application doesn't crash without Dragonfly")
        
    except Exception as e:
        print_fail(f"Error handling test failed: {str(e)}")
        return False
    finally:
        # Restore original URL
        if original_url:
            os.environ['DRAGONFLY_URL'] = original_url
    
    return True


def main():
    """Run all tests and display summary."""
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}   DRAGONFLY CACHE TEST SUITE{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{YELLOW}⚠️  Remember to delete this file after testing!{RESET}\n")
    
    results = {
        "Connection": test_connection(),
        "Basic Operations": test_basic_operations(),
        "TTL Expiration": test_ttl(),
        "Complex Data": test_complex_data(),
        "Integration": test_integration(),
        "Error Handling": test_error_handling(),
    }
    
    # Print summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"  {test_name:.<40} {status}")
    
    print(f"\n{BOLD}Results: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}{BOLD}🎉 All tests passed! Dragonfly cache is working correctly!{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{BOLD}⚠️  Some tests failed. Check the output above.{RESET}\n")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Test interrupted by user{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Unexpected error: {str(e)}{RESET}")
        sys.exit(1)

