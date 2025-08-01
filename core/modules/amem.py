# core/modules/amem.py
"""
A-Mem: Agentic Memory Module

This module implements an advanced memory system inspired by the A-Mem paper,
which proposes a Zettelkasten-like, agentic approach to memory management.
"""
import asyncio
import logging
import uuid
import time
import json
import re
from typing import Dict, Any, List, Optional
from collections import deque

from core.modules.base import MaestroCatModule
from core.storage.chromadb_manager import ChromaDBManager
from core.storage.sqlite_manager import SQLiteMemoryManager
from core.services.ollama_llm import OLLamaLLMService

logger = logging.getLogger(__name__)


class AMemModule(MaestroCatModule):
    """
    Agentic Memory (A-Mem) module for dynamic, interconnected knowledge.
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        logger.info("Initializing A-Mem Module with Tiered Memory System")
        self.db_path = config.get("chroma_path", "data/memory/amem_db")
        self.sqlite_path = config.get("sqlite_path", "data/memory/amem_conversations.db")
        self.collection_name = config.get("collection_name", "a-mem-collection")
        self.amem_llm_config = config.get("amem_llm", {
            "model": "gemma3:1b",  # Better at structured outputs than tinyllama
            "base_url": "http://localhost:11434",
            "temperature": 0.0,  # Deterministic for consistent extraction
        })
        
        # Performance settings
        self.tier1_enabled = config.get("tier1_enabled", True)
        self.tier2_enabled = config.get("tier2_enabled", True)
        self.tier3_enabled = config.get("tier3_enabled", True)
        self.cache_size = config.get("cache_size", 100)
        
        # Initialize storage managers
        self.chroma_manager = ChromaDBManager(
            path=self.db_path,
            collection_name=self.collection_name
        )
        self.sqlite_manager = SQLiteMemoryManager(db_path=self.sqlite_path)
        self.amem_llm = OLLamaLLMService(**self.amem_llm_config)
        
        # Memory cache for Tier 3
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_queue: deque = deque(maxlen=self.cache_size)
        
        # Performance metrics
        self.metrics = {
            "tier1_searches": 0,
            "tier1_hits": 0,
            "tier2_searches": 0,
            "tier2_hits": 0,
            "cache_hits": 0,
            "avg_tier1_latency": 0.0,
            "avg_tier2_latency": 0.0
        }

    async def initialize(self):
        """Initialize the A-Mem module and its components."""
        logger.info("🚀 A-Mem module with tiered memory system ready.")
        
        # Start background cache warming if tier 3 is enabled
        if self.tier3_enabled:
            asyncio.create_task(self._background_cache_warmer())

    async def on_event(self, event_type: str, data: Any):
        """Process events to create and link memories."""
        if event_type == "transcription_final":
            text = data.get("text", "")
            # Filter out non-informative utterances
            if self._is_meaningful_utterance(text):
                # Non-blocking memory creation
                asyncio.create_task(self.create_memory_note(text, data.get("session_id")))
        elif event_type == "amem_search":
            await self.search(data.get("query", ""))
        elif event_type == "llm_response_complete":
            # Store assistant responses too
            asyncio.create_task(self._store_assistant_response(data))

    def _format_metadata_for_db(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Converts list values in metadata to comma-separated strings for ChromaDB."""
        formatted = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                formatted[key] = ",".join(map(str, value))
            else:
                formatted[key] = value
        return formatted

    def _is_meaningful_utterance(self, text: str) -> bool:
        """
        Determine if an utterance contains meaningful information worth storing.
        Filters out acknowledgments, short responses, and non-informative utterances.
        """
        if not text or len(text.strip()) < 10:
            return False
            
        # List of non-informative phrases to filter out
        non_informative = [
            "yes", "no", "yeah", "nope", "ok", "okay", "sure", "thanks",
            "thank you", "hi", "hello", "hey", "bye", "goodbye",
            "you're totally off", "you're wrong", "that's wrong", "incorrect",
            "try again", "nope", "not really", "i don't know", "i dunno",
            "what about you", "how about you", "and you",
            "uh", "um", "hmm", "ah", "oh", "i see", "got it", "understood"
        ]
        
        text_lower = text.lower().strip()
        
        # Check if it's just a non-informative phrase
        if text_lower in non_informative:
            return False
            
        # Check if it starts with common non-informative patterns
        for phrase in non_informative:
            if text_lower.startswith(phrase + ",") or text_lower.startswith(phrase + "."):
                # But allow if there's substantial content after
                if len(text_lower) < len(phrase) + 15:
                    return False
        
        # Look for informative content indicators
        informative_indicators = [
            "favorite", "like", "love", "prefer", "enjoy", "listen",
            "artist", "music", "song", "band", "genre", "album",
            "jazz", "rock", "pop", "classical", "electronic", "hip hop",
            "work", "live", "from", "born", "study", "job", "hobby",
            "want", "need", "think", "believe", "feel", "remember"
        ]
        
        # If it contains informative indicators, it's likely meaningful
        for indicator in informative_indicators:
            if indicator in text_lower:
                return True
        
        # If it's a question with substance, it's meaningful
        if "?" in text and len(text) > 15:
            return True
            
        # If it's a longer utterance, it's likely meaningful
        if len(text) > 30:
            return True
            
        # Default to not storing short, non-informative utterances
        return False

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for fast SQLite search."""
        # Simple keyword extraction - can be enhanced with NLP
        # Remove common stop words and extract significant terms
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                     "of", "with", "by", "from", "up", "about", "into", "through", "during",
                     "before", "after", "above", "below", "between", "under", "again",
                     "further", "then", "once", "is", "are", "was", "were", "been", "be",
                     "have", "has", "had", "do", "does", "did", "will", "would", "could",
                     "should", "may", "might", "must", "can", "this", "that", "these",
                     "those", "i", "you", "he", "she", "it", "we", "they", "them", "their"}
        
        # Extract words
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter stop words and short words
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Get unique keywords
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords[:10]  # Limit to top 10 keywords

    async def create_memory_note(self, text: str, session_id: Optional[str] = None):
        """
        Create a new memory note from a piece of text.
        Non-blocking implementation with dual storage.
        """
        if not text:
            return

        logger.info(f"AMemModule: Creating memory note for: {text[:50]}...")
        
        # Extract keywords for SQLite storage
        keywords = self._extract_keywords(text)

        # Generate metadata with LLM following A-Mem pattern
        metadata_prompt = """Generate a structured analysis of the following content by:
            1. Identifying the most salient keywords (focus on nouns, verbs, and key concepts)
            2. Extracting core themes and contextual elements
            3. Creating relevant categorical tags

            Return ONLY a valid JSON object with this EXACT structure:
            {
                "keywords": ["keyword1", "keyword2", "keyword3"],
                "context": "A single sentence describing the main topic and key points",
                "tags": ["tag1", "tag2", "tag3"]
            }
            
            RULES:
            - keywords: array of 3-5 simple string keywords
            - context: a single string sentence (NOT a dict or object)
            - tags: array of 3-5 simple string tags
            - ALL values must be strings or arrays of strings
            - NO nested objects or dictionaries allowed

            Content for analysis:
            """ + text
        messages = [{"role": "user", "content": metadata_prompt}]
        
        # Use structured JSON response format following A-Mem pattern
        response_format = {
            "type": "json_object"
        }
        
        response = await self.amem_llm.generate(messages, response_format=response_format)
        metadata = self._parse_llm_response(response)
        
        # Add title based on context if available
        if metadata and metadata.get("context"):
            # Generate a title from context
            context_str = str(metadata["context"])  # Ensure it's a string
            metadata["title"] = context_str[:50] + "..." if len(context_str) > 50 else context_str
        else:
            metadata["title"] = "Untitled"
            
        # Validate and fix metadata to ensure no dict values
        metadata = self._sanitize_metadata(metadata)
        
        # Merge extracted keywords with LLM keywords
        if metadata and "keywords" in metadata:
            llm_keywords = metadata["keywords"]
            if isinstance(llm_keywords, list):
                # Combine and deduplicate
                all_keywords = list(set(keywords + llm_keywords))
                metadata["keywords"] = all_keywords[:15]  # Limit total

        if not metadata:
            logger.error("Could not generate metadata. Aborting memory creation.")
            return

        memory_id = str(uuid.uuid4())
        timestamp = time.time()
        metadata.update({
            "created_at": timestamp,
            "original_text": text,
            "links": [],
            "session_id": session_id or "default"
        })

        # Store in SQLite for fast keyword search (Tier 1)
        if self.tier1_enabled:
            await self.sqlite_manager.store_message(
                session_id=session_id or "amem_memories",
                role="memory",
                content=text,
                metadata={
                    "memory_id": memory_id,
                    "title": metadata.get("title", ""),
                    "keywords": keywords,  # Store extracted keywords
                    "tags": metadata.get("tags", [])
                }
            )
        
        # Store in ChromaDB for semantic search (Tier 2)
        if self.tier2_enabled:
            # Sanitize metadata before storing
            sanitized_metadata = self._sanitize_metadata(metadata)
            db_metadata = self._format_metadata_for_db(sanitized_metadata)
            await self.chroma_manager.add_memory(memory_id, text, db_metadata)

        related_memories = await self.chroma_manager.search_memories(text, n_results=5)
        links_to_add = []
        
        # Process related memories asynchronously for better performance
        # Following A-Mem's non-blocking pattern
        for mem in related_memories:
            if mem["id"] != memory_id:
                links_to_add.append(mem["id"])
                # Add link asynchronously to avoid blocking
                asyncio.create_task(self._add_link_to_memory(mem["id"], memory_id))
                # Queue evolution for async processing without waiting
                asyncio.create_task(self._evolve_memory(mem, text))

        if links_to_add:
            metadata["links"] = links_to_add
            # Sanitize metadata before updating
            sanitized_metadata = self._sanitize_metadata(metadata)
            db_metadata = self._format_metadata_for_db(sanitized_metadata)
            await self.chroma_manager.update_memory(memory_id, text, db_metadata)
        
        logger.info(f"🧠 Created and linked memory {memory_id} with title: {metadata.get('title')}")

        if self.event_emitter:
            await self.event_emitter.emit("amem_updated", {
                "id": memory_id,
                "content": text,
                "metadata": metadata
            })

    async def _evolve_memory(self, memory: Dict[str, Any], new_information: str):
        """
        Evolve an existing memory with new information.
        Only evolves if there's meaningful new information.
        """
        # Quick check: Skip evolution if texts are too similar
        if len(new_information) < 10 or new_information.lower() in memory['content'].lower():
            logger.debug(f"Skipping evolution for memory {memory['id']} - insufficient new information")
            return
            
        logger.info(f"AMemModule: Evolving memory {memory['id']} with new info: {new_information[:50]}...")
        
        # Following A-Mem evolution pattern with structured decision making
        evolution_prompt = f'''You are an AI memory evolution agent responsible for managing and evolving a knowledge base.
                                Analyze the the new memory note according to keywords and context, also with their several nearest neighbors memory.
                                Make decisions about its evolution.  

                                The existing memory:
                                - context: {memory['metadata'].get('context', 'General')}
                                - content: {memory['content'][:200]}...
                                - keywords: {memory['metadata'].get('keywords', [])}
                                - tags: {memory['metadata'].get('tags', [])}

                                New Information: "{new_information[:200]}..."

                                Based on this information, determine:
                                1. Should this memory be evolved? Consider its relationships with the new information.
                                2. What specific updates should be made?

                                Return ONLY a valid JSON object:
                                {{
                                    "should_evolve": true or false,
                                    "context": "a single string describing the updated context",
                                    "keywords": ["string1", "string2", "string3"],
                                    "tags": ["tag1", "tag2", "tag3"]
                                }}
                                
                                IMPORTANT:
                                - context MUST be a single string, NOT an object or dict
                                - keywords MUST be an array of strings
                                - tags MUST be an array of strings
                                - NO nested objects allowed
                                '''
        messages = [{"role": "user", "content": evolution_prompt}]
        
        # Use structured JSON response format
        response_format = {
            "type": "json_object"
        }
        
        response = await self.amem_llm.generate(messages, response_format=response_format)
        updates = self._parse_llm_response(response)

        if updates and updates.get("should_evolve"):
            if updates.get("context"):
                # Ensure context is always a string
                context_value = updates["context"]
                if isinstance(context_value, dict):
                    context_value = json.dumps(context_value)
                elif not isinstance(context_value, str):
                    context_value = str(context_value)
                memory["metadata"]["context"] = context_value
                logger.info(f"Evolved memory {memory['id']} with new context: {context_value}")
            if updates.get("keywords"):
                # Ensure keywords is a list of strings
                keywords = updates["keywords"]
                if isinstance(keywords, list):
                    memory["metadata"]["keywords"] = [str(k) for k in keywords]
                else:
                    memory["metadata"]["keywords"] = [str(keywords)]
                logger.info(f"Evolved memory {memory['id']} with new keywords: {memory['metadata']['keywords']}")
            if updates.get("tags"):
                # Ensure tags is a list of strings
                tags = updates["tags"]
                if isinstance(tags, list):
                    memory["metadata"]["tags"] = [str(t) for t in tags]
                else:
                    memory["metadata"]["tags"] = [str(tags)]
                logger.info(f"Evolved memory {memory['id']} with new tags: {memory['metadata']['tags']}")
            
            db_metadata = self._format_metadata_for_db(memory["metadata"])
            await self.chroma_manager.update_memory(memory["id"], memory["content"], db_metadata)
            
            if self.event_emitter:
                await self.event_emitter.emit("amem_updated", memory)
        else:
            logger.info(f"No evolution needed for memory {memory['id']}.")

    async def _add_link_to_memory(self, memory_id: str, link_to_add: str):
        """Add a link to an existing memory."""
        memory = await self.chroma_manager.get_memory(memory_id)
        if memory and memory.get("metadata"):
            links = memory["metadata"].get("links", "").split(',') if memory["metadata"].get("links") else []
            if link_to_add not in links:
                links.append(link_to_add)
                memory["metadata"]["links"] = ",".join(links)
                await self.chroma_manager.update_memory(memory_id, memory["content"], memory["metadata"])
                logger.debug(f"Added link from {memory_id} to {link_to_add}")

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize metadata to ensure all values are ChromaDB-compatible.
        ChromaDB only accepts str, int, float, bool, or None as metadata values.
        """
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, dict):
                # Convert dict to string
                sanitized[key] = json.dumps(value)
            elif isinstance(value, list):
                # Keep lists as they are - ChromaDB handles them
                sanitized[key] = value
            elif value is None or isinstance(value, (str, int, float, bool)):
                # These types are fine
                sanitized[key] = value
            else:
                # Convert everything else to string
                sanitized[key] = str(value)
        return sanitized
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM JSON response, handling various formats."""
        try:
            # First try direct JSON parsing
            response = response.strip()
            if response.startswith('{') and response.endswith('}'):
                return json.loads(response)
            
            # Handle markdown code blocks
            if '```json' in response:
                start = response.find('```json') + 7
                end = response.find('```', start)
                if end != -1:
                    json_str = response[start:end].strip()
                    return json.loads(json_str)
            
            # Try to extract JSON from anywhere in the response
            import re
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, response)
            
            for match in matches:
                try:
                    return json.loads(match)
                except:
                    continue
            
            # If all else fails, log and return empty
            logger.warning(f"Could not extract JSON from response: {response[:200]}...")
            return {}
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return {}

    async def get_context(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve relevant context using tiered search approach.
        Returns results from the fastest available tier.
        """
        logger.info(f"AMemModule.get_context: Starting tiered search for query: '{query}'")
        logger.debug(f"  Tier 1 enabled: {self.tier1_enabled}")
        logger.debug(f"  Tier 2 enabled: {self.tier2_enabled}")
        logger.debug(f"  Tier 3 enabled: {self.tier3_enabled}")
        start_time = time.time()
        
        # Check cache first (Tier 3)
        if self.tier3_enabled and query in self.memory_cache:
            self.metrics["cache_hits"] += 1
            logger.info(f"Cache hit for query: {query}")
            return self.memory_cache[query]
        
        results = {
            "tier1_matches": [],
            "semantic_matches": [],
            "linked_memories": [],
            "search_latency": 0.0,
            "tier_used": None
        }
        
        # Tier 1: SQLite keyword search (fastest)
        if self.tier1_enabled:
            tier1_start = time.time()
            keywords = self._extract_keywords(query)
            
            # Search for any keyword match
            tier1_results = []
            for keyword in keywords[:3]:  # Limit to top 3 keywords
                keyword_results = await self.sqlite_manager.search_conversations(
                    query=keyword,
                    limit=5,
                    session_id=None  # Search across all memories
                )
                tier1_results.extend(keyword_results)
            
            # Deduplicate and format results
            seen_ids = set()
            for result in tier1_results:
                if result["id"] not in seen_ids and result["role"] == "memory":
                    seen_ids.add(result["id"])
                    results["tier1_matches"].append({
                        "content": result["content"],
                        "metadata": result.get("metadata", {}),
                        "relevance": "keyword_match"
                    })
            
            tier1_latency = (time.time() - tier1_start) * 1000  # ms
            self.metrics["tier1_searches"] += 1
            self.metrics["avg_tier1_latency"] = (
                (self.metrics["avg_tier1_latency"] * (self.metrics["tier1_searches"] - 1) + tier1_latency) 
                / self.metrics["tier1_searches"]
            )
            
            if results["tier1_matches"]:
                self.metrics["tier1_hits"] += 1
                results["tier_used"] = "tier1_sqlite"
                results["search_latency"] = tier1_latency
                logger.info(f"Tier 1 search completed in {tier1_latency:.2f}ms with {len(results['tier1_matches'])} results")
                
                # Cache the result
                if self.tier3_enabled:
                    await self._update_cache(query, results)
                    
                return results
        
        # Tier 2: ChromaDB semantic search (slower but more accurate)
        if self.tier2_enabled:
            tier2_start = time.time()
            semantic_matches = await self.search(query)
            results["semantic_matches"] = semantic_matches
            
            # Get linked memories
            for match in semantic_matches:
                if match.get("metadata", {}).get("links"):
                    link_ids = match["metadata"]["links"].split(',')
                    for link_id in link_ids:
                        linked_mem = await self.chroma_manager.get_memory(link_id)
                        if linked_mem:
                            results["linked_memories"].append(linked_mem)
            
            tier2_latency = (time.time() - tier2_start) * 1000  # ms
            self.metrics["tier2_searches"] += 1
            self.metrics["avg_tier2_latency"] = (
                (self.metrics["avg_tier2_latency"] * (self.metrics["tier2_searches"] - 1) + tier2_latency) 
                / self.metrics["tier2_searches"]
            )
            
            if semantic_matches:
                self.metrics["tier2_hits"] += 1
                results["tier_used"] = "tier2_chromadb"
                results["search_latency"] = tier2_latency
                logger.info(f"Tier 2 search completed in {tier2_latency:.2f}ms with {len(semantic_matches)} results")
            
            # Cache the result
            if self.tier3_enabled:
                await self._update_cache(query, results)
        
        total_latency = (time.time() - start_time) * 1000
        results["total_latency"] = total_latency
        
        return results

    async def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search for memories using semantic search."""
        logger.info(f"AMemModule: Searching for: {query}")
        results = await self.chroma_manager.search_memories(query, n_results=n_results)
        logger.info(f"AMemModule: Found {len(results)} results.")
        return results

    async def _store_assistant_response(self, data: Dict[str, Any]):
        """Store assistant responses for future reference."""
        if not data.get("text"):
            return
            
        # Store in SQLite only for fast retrieval
        if self.tier1_enabled:
            await self.sqlite_manager.store_message(
                session_id=data.get("session_id", "amem_memories"),
                role="assistant",
                content=data["text"],
                metadata={"type": "response"}
            )
    
    async def _update_cache(self, query: str, results: Dict[str, Any]):
        """Update the memory cache with new results."""
        # Simple LRU cache implementation
        if query in self.memory_cache:
            # Move to end (most recently used)
            self.cache_queue.remove(query)
            self.cache_queue.append(query)
        else:
            # Add new entry
            if len(self.cache_queue) >= self.cache_size:
                # Remove oldest
                oldest = self.cache_queue[0]
                del self.memory_cache[oldest]
            
            self.cache_queue.append(query)
            self.memory_cache[query] = results
    
    async def _background_cache_warmer(self):
        """Background task to pre-emptively cache likely queries."""
        while True:
            try:
                await asyncio.sleep(30)  # Run every 30 seconds
                
                # Get recent conversation context
                recent_messages = await self.sqlite_manager.get_recent_context(
                    session_id="amem_memories",
                    time_window_minutes=5,
                    max_messages=10
                )
                
                if not recent_messages:
                    continue
                
                # Use LLM to predict likely queries following A-Mem pattern
                context = "\n".join([msg["content"] for msg in recent_messages[-5:]])
                prediction_prompt = f"""Analyze the recent conversation context and predict what memories might be relevant next.
                
                Recent conversation:
                {context[:300]}...
                
                Generate 2-3 predictive search queries that would help retrieve relevant memories for potential follow-up questions.
                
                Return a JSON array of query strings:
                ["predictive query 1", "predictive query 2", "predictive query 3"]
                """
                
                messages = [{"role": "user", "content": prediction_prompt}]
                
                # Use structured JSON response format
                response_format = {
                    "type": "json_object"
                }
                
                response = await self.amem_llm.generate(messages, response_format=response_format)
                predictions = self._parse_llm_response(response)
                
                if isinstance(predictions, list):
                    for predicted_query in predictions[:3]:
                        if predicted_query and isinstance(predicted_query, str):
                            # Pre-warm cache with predicted queries
                            await self.get_context(predicted_query)
                            logger.debug(f"Pre-cached query: {predicted_query}")
                            
            except Exception as e:
                logger.error(f"Error in background cache warmer: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the tiered memory system."""
        total_searches = self.metrics["tier1_searches"] + self.metrics["tier2_searches"]
        
        return {
            "tier1_hit_rate": self.metrics["tier1_hits"] / max(1, self.metrics["tier1_searches"]),
            "tier2_hit_rate": self.metrics["tier2_hits"] / max(1, self.metrics["tier2_searches"]),
            "cache_hit_rate": self.metrics["cache_hits"] / max(1, total_searches),
            "avg_tier1_latency_ms": self.metrics["avg_tier1_latency"],
            "avg_tier2_latency_ms": self.metrics["avg_tier2_latency"],
            "total_searches": total_searches,
            "cache_size": len(self.memory_cache)
        }
    
    async def cleanup(self):
        """Clean up resources."""
        await self.chroma_manager.cleanup()
        await self.sqlite_manager.close()
        logger.info("🧹 A-Mem module with tiered memory cleaned up.")
