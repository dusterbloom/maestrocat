#!/usr/bin/env python3
# integration_tests/run_tests.py
"""Runner script for MaestroCat integration tests"""

import argparse
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from integration_tests.latency_test import main as run_latency_test
from integration_tests.stress_test import main as run_stress_test


async def main():
    parser = argparse.ArgumentParser(description="Run MaestroCat integration tests")
    parser.add_argument(
        "test_type",
        choices=["latency", "stress", "all"],
        help="Type of test to run"
    )
    
    args = parser.parse_args()
    
    if args.test_type == "latency":
        print("Running latency tests...")
        await run_latency_test()
    elif args.test_type == "stress":
        print("Running stress tests...")
        await run_stress_test()
    elif args.test_type == "all":
        print("Running all tests...")
        print("\n--- LATENCY TESTS ---")
        await run_latency_test()
        print("\n--- STRESS TESTS ---")
        await run_stress_test()
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(main())