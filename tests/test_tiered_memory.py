#!/usr/bin/env python3
"""
Test script for the tiered memory system.

This script tests the performance and functionality of the tiered
memory search implementation.
"""

import asyncio
import time
import json
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.modules.amem import AMemModule
from core.processors.amem_context_injector import AMemContextInjector
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext


async def test_tiered_memory():
    """Test the tiered memory system performance."""
    print("🧪 Testing Tiered Memory System\n")
    
    # Configuration
    config = {
        "chroma_path": "data/test_memory/chroma_db",
        "sqlite_path": "data/test_memory/test_amem.db",
        "collection_name": "test-amem",
        "tier1_enabled": True,
        "tier2_enabled": True,
        "tier3_enabled": True,
        "cache_size": 50,
        "amem_llm": {
            "model": "llama3.2:1b",
            "base_url": "http://localhost:11434",
            "temperature": 0.0,
        }
    }
    
    # Initialize module
    amem = AMemModule("test_amem", config)
    await amem.initialize()
    
    # Create test memories
    print("📝 Creating test memories...")
    test_memories = [
        "My cat is named Whiskers and she loves to play with yarn",
        "I work as a software engineer at TechCorp in San Francisco",
        "My favorite programming language is Python because it's versatile",
        "Whiskers the cat is 5 years old and has orange fur",
        "I learned Python in 2015 and have been using it ever since",
        "The weather in San Francisco is often foggy in the morning",
        "I enjoy hiking in the mountains on weekends",
        "My colleague John also has a cat named Mittens",
        "Python is great for data science and machine learning",
        "Whiskers likes to sleep on my keyboard while I code"
    ]
    
    # Store memories
    for i, memory in enumerate(test_memories):
        await amem.create_memory_note(memory, f"test_session_{i}")
        print(f"  ✓ Stored: {memory[:50]}...")
        await asyncio.sleep(0.1)  # Small delay to avoid overwhelming
    
    print("\n⏱️  Testing search performance...")
    
    # Test queries
    test_queries = [
        ("Whiskers", "Simple keyword search - should use Tier 1"),
        ("my cat Whiskers", "Multi-keyword search - should use Tier 1"),
        ("programming cat", "Mixed keywords - should use Tier 1"),
        ("What pets do I have?", "Semantic query - might use Tier 2"),
        ("Tell me about my work", "Complex query - might use Tier 2"),
        ("Whiskers", "Repeated query - should hit cache"),
        ("my cat Whiskers", "Repeated query - should hit cache")
    ]
    
    results = []
    
    for query, description in test_queries:
        print(f"\n🔍 Query: '{query}'")
        print(f"   Type: {description}")
        
        start_time = time.time()
        context = await amem.get_context(query)
        latency = (time.time() - start_time) * 1000
        
        tier_used = context.get("tier_used", "none")
        search_latency = context.get("search_latency", 0)
        num_results = len(context.get("tier1_matches", [])) + len(context.get("semantic_matches", []))
        
        print(f"   ✓ Tier used: {tier_used}")
        print(f"   ✓ Search latency: {search_latency:.2f}ms")
        print(f"   ✓ Total latency: {latency:.2f}ms")
        print(f"   ✓ Results found: {num_results}")
        
        results.append({
            "query": query,
            "tier": tier_used,
            "latency": search_latency,
            "total_latency": latency,
            "results": num_results
        })
        
        # Show first result if any
        if context.get("tier1_matches"):
            first_match = context["tier1_matches"][0]
            print(f"   📄 First match: {first_match['content'][:60]}...")
        elif context.get("semantic_matches"):
            first_match = context["semantic_matches"][0]
            print(f"   📄 First match: {first_match['content'][:60]}...")
    
    # Performance summary
    print("\n📊 Performance Summary:")
    print("-" * 60)
    
    tier1_queries = [r for r in results if "tier1" in r["tier"]]
    tier2_queries = [r for r in results if "tier2" in r["tier"]]
    cache_queries = [r for r in results if r["tier"] is None or "cache" in r["tier"].lower()]
    
    if tier1_queries:
        avg_tier1 = sum(r["latency"] for r in tier1_queries) / len(tier1_queries)
        print(f"Tier 1 (SQLite): {len(tier1_queries)} queries, avg {avg_tier1:.2f}ms")
    
    if tier2_queries:
        avg_tier2 = sum(r["latency"] for r in tier2_queries) / len(tier2_queries)
        print(f"Tier 2 (ChromaDB): {len(tier2_queries)} queries, avg {avg_tier2:.2f}ms")
    
    if cache_queries:
        print(f"Cache hits: {len(cache_queries)} queries")
    
    # Get module metrics
    metrics = amem.get_metrics()
    print(f"\nTier 1 hit rate: {metrics['tier1_hit_rate']:.2%}")
    print(f"Tier 2 hit rate: {metrics['tier2_hit_rate']:.2%}")
    print(f"Cache hit rate: {metrics['cache_hit_rate']:.2%}")
    print(f"Average Tier 1 latency: {metrics['avg_tier1_latency_ms']:.2f}ms")
    print(f"Average Tier 2 latency: {metrics['avg_tier2_latency_ms']:.2f}ms")
    
    # Test context injection
    print("\n🔧 Testing Context Injection...")
    
    # Create a mock context
    llm_context = OpenAILLMContext(
        messages=[{"role": "user", "content": "Tell me about Whiskers"}]
    )
    
    # Create injector
    injector = AMemContextInjector(llm_context, amem)
    
    # Get injected context
    from pipecat.frames.frames import TranscriptionFrame
    frame = TranscriptionFrame(text="Tell me about Whiskers", user_id="test_user")
    
    # Process frame
    await injector.process_frame(frame, None)
    
    # Check if context was injected
    if llm_context.messages[-1]["role"] == "user":
        injected_content = llm_context.messages[-1]["content"]
        if "[Recalled Memory Context]" in injected_content:
            print("✓ Context successfully injected into LLM prompt")
            print(f"  Injected content preview: {injected_content[:200]}...")
        else:
            print("✗ Context injection failed")
    
    # Cleanup
    await amem.cleanup()
    print("\n✅ Test completed!")


if __name__ == "__main__":
    # Check if Ollama is running
    import httpx
    
    try:
        response = httpx.get("http://localhost:11434/api/version", timeout=2.0)
        if response.status_code == 200:
            print("✓ Ollama is running")
        else:
            print("⚠️  Ollama is not responding properly")
            print("Please ensure Ollama is running: ollama serve")
            sys.exit(1)
    except Exception as e:
        print("⚠️  Cannot connect to Ollama")
        print("Please start Ollama with: ollama serve")
        sys.exit(1)
    
    # Run test
    asyncio.run(test_tiered_memory())