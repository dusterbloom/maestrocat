"""
A-Mem Cache Manager for pre-emptive memory loading and fast retrieval.

This module implements a smart caching system that predicts and pre-loads
memories that are likely to be needed based on conversation context.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from collections import OrderedDict, Counter

logger = logging.getLogger(__name__)


class AMemCache:
    """
    Intelligent memory cache with predictive pre-loading capabilities.
    
    Features:
    - LRU cache with configurable size
    - Access pattern tracking
    - Predictive pre-loading based on context
    - Automatic cache warming
    - Performance metrics
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        """
        Initialize the cache.
        
        Args:
            max_size: Maximum number of entries in cache
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        
        # LRU cache implementation using OrderedDict
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        
        # Access tracking for predictive loading
        self._access_patterns: Counter = Counter()
        self._query_sequences: List[str] = []
        self._sequence_limit = 100
        
        # Performance metrics
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "predictions_made": 0,
            "predictions_hit": 0
        }
        
        # Predictive loading state
        self._prediction_confidence_threshold = 0.3
        self._min_pattern_occurrences = 2
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get an item from cache with LRU update.
        
        Args:
            key: Cache key (usually the query)
            
        Returns:
            Cached data or None if not found/expired
        """
        if key in self._cache:
            # Check TTL
            entry = self._cache[key]
            if time.time() - entry["timestamp"] > self.ttl_seconds:
                # Expired
                del self._cache[key]
                self.metrics["misses"] += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self.metrics["hits"] += 1
            
            # Track access pattern
            self._track_access(key)
            
            return entry["data"]
        
        self.metrics["misses"] += 1
        return None
    
    async def put(self, key: str, data: Dict[str, Any]) -> None:
        """
        Put an item in cache with LRU eviction if needed.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        # Remove if already exists to update position
        if key in self._cache:
            del self._cache[key]
        
        # Add to end
        self._cache[key] = {
            "data": data,
            "timestamp": time.time()
        }
        
        # Evict if over capacity
        while len(self._cache) > self.max_size:
            # Remove oldest (first item)
            self._cache.popitem(last=False)
            self.metrics["evictions"] += 1
        
        # Track for predictions
        self._track_access(key)
    
    def _track_access(self, key: str) -> None:
        """Track access patterns for predictive loading."""
        # Update access frequency
        self._access_patterns[key] += 1
        
        # Track query sequences
        self._query_sequences.append(key)
        if len(self._query_sequences) > self._sequence_limit:
            self._query_sequences.pop(0)
    
    async def predict_next_queries(self, current_query: str, n: int = 3) -> List[str]:
        """
        Predict likely next queries based on access patterns.
        
        Args:
            current_query: The current query
            n: Number of predictions to make
            
        Returns:
            List of predicted queries
        """
        predictions = []
        self.metrics["predictions_made"] += 1
        
        # Method 1: Sequential pattern matching
        # Look for times this query appeared in sequence history
        sequence_predictions = self._predict_from_sequences(current_query)
        predictions.extend(sequence_predictions)
        
        # Method 2: Co-occurrence analysis
        # Find queries that often appear together
        cooccurrence_predictions = self._predict_from_cooccurrence(current_query)
        predictions.extend(cooccurrence_predictions)
        
        # Method 3: Semantic similarity (simplified - just common words)
        semantic_predictions = self._predict_from_semantics(current_query)
        predictions.extend(semantic_predictions)
        
        # Deduplicate and score
        scored_predictions = Counter(predictions)
        
        # Return top N predictions
        top_predictions = [query for query, _ in scored_predictions.most_common(n)]
        
        return top_predictions
    
    def _predict_from_sequences(self, current_query: str) -> List[str]:
        """Predict based on sequential patterns."""
        predictions = []
        
        # Find where current query appears in history
        for i in range(len(self._query_sequences) - 1):
            if self._query_sequences[i] == current_query:
                # Next query is a potential prediction
                next_query = self._query_sequences[i + 1]
                predictions.append(next_query)
        
        return predictions
    
    def _predict_from_cooccurrence(self, current_query: str) -> List[str]:
        """Predict based on queries that often appear together."""
        predictions = []
        
        # Simple sliding window approach
        window_size = 5
        current_in_windows = []
        
        for i in range(len(self._query_sequences) - window_size):
            window = self._query_sequences[i:i + window_size]
            if current_query in window:
                current_in_windows.extend(window)
        
        # Count co-occurrences
        cooccurrences = Counter(current_in_windows)
        if current_query in cooccurrences:
            del cooccurrences[current_query]
        
        # Top co-occurring queries
        for query, count in cooccurrences.most_common(3):
            if count >= self._min_pattern_occurrences:
                predictions.append(query)
        
        return predictions
    
    def _predict_from_semantics(self, current_query: str) -> List[str]:
        """Simple semantic prediction based on shared keywords."""
        predictions = []
        
        # Extract simple keywords (words longer than 3 chars)
        current_keywords = set(word.lower() for word in current_query.split() if len(word) > 3)
        
        if not current_keywords:
            return predictions
        
        # Find queries with overlapping keywords
        keyword_matches = []
        
        for query in self._access_patterns.keys():
            if query == current_query:
                continue
            
            query_keywords = set(word.lower() for word in query.split() if len(word) > 3)
            overlap = len(current_keywords & query_keywords)
            
            if overlap > 0:
                similarity = overlap / len(current_keywords)
                if similarity > self._prediction_confidence_threshold:
                    keyword_matches.append((query, similarity))
        
        # Sort by similarity and return top matches
        keyword_matches.sort(key=lambda x: x[1], reverse=True)
        predictions = [query for query, _ in keyword_matches[:3]]
        
        return predictions
    
    async def warm_cache(self, queries: List[str], fetch_func) -> None:
        """
        Pre-populate cache with a list of queries.
        
        Args:
            queries: List of queries to pre-cache
            fetch_func: Async function to fetch data for a query
        """
        logger.info(f"Warming cache with {len(queries)} queries")
        
        tasks = []
        for query in queries:
            if query not in self._cache:
                tasks.append(self._fetch_and_cache(query, fetch_func))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _fetch_and_cache(self, query: str, fetch_func) -> None:
        """Fetch data and add to cache."""
        try:
            data = await fetch_func(query)
            if data:
                await self.put(query, data)
        except Exception as e:
            logger.error(f"Error warming cache for query '{query}': {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.metrics["hits"] + self.metrics["misses"]
        hit_rate = self.metrics["hits"] / max(1, total_requests)
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
            "evictions": self.metrics["evictions"],
            "predictions_made": self.metrics["predictions_made"],
            "prediction_hit_rate": self.metrics["predictions_hit"] / max(1, self.metrics["predictions_made"]),
            "unique_queries": len(self._access_patterns),
            "most_accessed": self._access_patterns.most_common(5)
        }
    
    def clear(self) -> None:
        """Clear the cache and reset metrics."""
        self._cache.clear()
        self._access_patterns.clear()
        self._query_sequences.clear()
        
        # Reset metrics
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "predictions_made": 0,
            "predictions_hit": 0
        }
        
        logger.info("Cache cleared and metrics reset")