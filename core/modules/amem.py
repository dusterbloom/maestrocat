# core/modules/amem.py
"""
A-Mem: Agentic Memory Module

This module implements an advanced memory system inspired by the A-Mem paper,
which proposes a Zettelkasten-like, agentic approach to memory management.
"""
import logging
import uuid
import time
import json
from typing import Dict, Any, List, Optional

from core.modules.base import MaestroCatModule
from core.storage.chromadb_manager import ChromaDBManager
from core.services.ollama_llm import OLLamaLLMService

logger = logging.getLogger(__name__)


class AMemModule(MaestroCatModule):
    """
    Agentic Memory (A-Mem) module for dynamic, interconnected knowledge.
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        logger.info("Initializing A-Mem Module")
        self.db_path = config.get("chroma_path", "data/memory/amem_db")
        self.collection_name = config.get("collection_name", "a-mem-collection")
        self.amem_llm_config = config.get("amem_llm", {
            "model": "llama3.2:1b",
            "base_url": "http://localhost:11434",
            "temperature": 0.0,
        })

        self.chroma_manager = ChromaDBManager(
            path=self.db_path,
            collection_name=self.collection_name
        )
        self.amem_llm = OLLamaLLMService(**self.amem_llm_config)

    async def initialize(self):
        """Initialize the A-Mem module and its components."""
        logger.info("🚀 A-Mem module ready.")

    async def on_event(self, event_type: str, data: Any):
        """Process events to create and link memories."""
        if event_type == "transcription_final":
            await self.create_memory_note(data.get("text", ""))
        elif event_type == "amem_search":
            await self.search(data.get("query", ""))

    def _format_metadata_for_db(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Converts list values in metadata to comma-separated strings for ChromaDB."""
        formatted = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                formatted[key] = ",".join(map(str, value))
            else:
                formatted[key] = value
        return formatted

    async def create_memory_note(self, text: str):
        """
        Create a new memory note from a piece of text.
        """
        if not text:
            return

        logger.info(f"AMemModule: Creating memory note for: {text[:50]}...")

        metadata_prompt = f"""
        You are a helpful AI assistant that extracts information from text and
        returns it in a structured JSON format.

        Analyze the following text and generate a concise title, a list of
        keywords, and a list of tags.

        Text: "{text}"

        Respond with a single JSON object with the following keys:
        "title": "Your Title",
        "keywords": ["keyword1", "keyword2", ...],
        "tags": ["tag1", "tag2", ...]
        """
        messages = [{"role": "user", "content": metadata_prompt}]
        response = await self.amem_llm.generate(messages)
        metadata = self._parse_llm_response(response)

        if not metadata:
            logger.error("Could not generate metadata. Aborting memory creation.")
            return

        memory_id = str(uuid.uuid4())
        metadata.update({
            "created_at": time.time(),
            "original_text": text,
            "links": []
        })

        db_metadata = self._format_metadata_for_db(metadata)
        await self.chroma_manager.add_memory(memory_id, text, db_metadata)

        related_memories = await self.chroma_manager.search_memories(text, n_results=5)
        links_to_add = []
        for mem in related_memories:
            if mem["id"] != memory_id:
                links_to_add.append(mem["id"])
                await self._add_link_to_memory(mem["id"], memory_id)
                await self._evolve_memory(mem, text)

        if links_to_add:
            metadata["links"] = links_to_add
            db_metadata = self._format_metadata_for_db(metadata)
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
        """
        logger.info(f"AMemModule: Evolving memory {memory['id']} with new info: {new_information[:50]}...")
        prompt = f"""
        You are a highly intelligent agent responsible for maintaining a knowledge graph.
        Your task is to analyze a new piece of information and decide if it should refine an existing, related memory.

        **Existing Memory:**
        - **Title:** "{memory['metadata'].get('title', 'Untitled')}"
        - **Content:** "{memory['content']}"
        - **Keywords:** "{memory['metadata'].get('keywords', '')}"

        **New, Related Information:**
        - "{new_information}"

        **Your Task:**
        1.  Compare the "New, Related Information" with the "Existing Memory".
        2.  Decide if the new information adds nuance, detail, or a new perspective that warrants updating the existing memory's title or keywords.
        3.  If no meaningful update is needed, you MUST indicate this.

        **Output Format:**
        Respond with a single JSON object.

        -   If you decide **not** to make a change, respond with:
            `{{"no_change": true}}`

        -   If you decide to make a change, respond with:
            `{{"title": "A new, more descriptive title", "keywords": ["new", "refined", "keywords"]}}`
            (Only include the fields you are changing).

        **Example:**
        -   **Existing Memory:** Title: "User's Music Preference", Content: "I like jazz", Keywords: "music, jazz"
        -   **New Information:** "Miles Davis is my favorite jazz artist."
        -   **Your Output:** `{{"title": "User's Preference for Jazz, Specifically Miles Davis", "keywords": ["music", "jazz", "miles davis"]}}`

        Now, analyze the provided information and generate your response.
        """
        messages = [{"role": "user", "content": prompt}]
        response = await self.amem_llm.generate(messages)
        updates = self._parse_llm_response(response)

        if updates and not updates.get("no_change"):
            if updates.get("title"):
                memory["metadata"]["title"] = updates["title"]
                logger.info(f"Evolved memory {memory['id']} with new title: {updates['title']}")
            if updates.get("keywords"):
                memory["metadata"]["keywords"] = updates["keywords"]
                logger.info(f"Evolved memory {memory['id']} with new keywords: {updates['keywords']}")
            
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

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM JSON response, handling markdown code blocks."""
        try:
            # Find the start and end of the JSON object
            start_index = response.find('{')
            end_index = response.rfind('}')
            if start_index != -1 and end_index != -1:
                json_str = response[start_index:end_index + 1]
                return json.loads(json_str)
            else:
                logger.error(f"Could not find JSON object in LLM response: {response}")
                return {}
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM JSON response: {response}")
            return {}

    async def get_context(self, query: str) -> Dict[str, Any]:
        """
        Retrieve relevant context for the current interaction.
        """
        logger.debug(f"Getting context for query: {query}")
        semantic_matches = await self.search(query)
        linked_memories = []

        for match in semantic_matches:
            if match.get("metadata", {}).get("links"):
                link_ids = match["metadata"]["links"].split(',')
                for link_id in link_ids:
                    linked_mem = await self.chroma_manager.get_memory(link_id)
                    if linked_mem:
                        linked_memories.append(linked_mem)

        return {
            "semantic_matches": semantic_matches,
            "linked_memories": linked_memories,
        }

    async def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search for memories using semantic search."""
        logger.info(f"AMemModule: Searching for: {query}")
        results = await self.chroma_manager.search_memories(query, n_results=n_results)
        logger.info(f"AMemModule: Found {len(results)} results.")
        return results

    async def cleanup(self):
        """Clean up resources."""
        await self.chroma_manager.cleanup()
        logger.info("🧹 A-Mem module cleaned up.")
