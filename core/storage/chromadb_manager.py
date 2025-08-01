# core/storage/chromadb_manager.py
"""
ChromaDB Manager for vector storage and semantic search.
"""
import logging
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


class ChromaDBManager:
    """
    Manages interactions with a ChromaDB collection for storing
    and searching memory vectors.
    """

    def __init__(self, path: str = "data/memory/chroma_db", collection_name: str = "a-mem"):
        logger.info(f"Initializing ChromaDB at: {path}")
        self.client = chromadb.PersistentClient(path=path)
        self.collection_name = collection_name
        self.embedder = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedder
        )

    async def add_memory(self, memory_id: str, content: str, metadata: Dict[str, Any]):
        """Add a memory to the collection."""
        try:
            self.collection.add(
                ids=[memory_id],
                documents=[content],
                metadatas=[metadata]
            )
            logger.debug(f"Added memory {memory_id} to ChromaDB.")
        except Exception as e:
            logger.error(f"Error adding memory to ChromaDB: {e}")

    async def search_memories(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search for similar memories using semantic search."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            # The result of a query is a nested list
            if not results or not results.get("ids") or not results["ids"][0]:
                return []

            formatted = []
            for i, memory_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": memory_id,
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
            return formatted
        except Exception as e:
            logger.error(f"Error searching memories in ChromaDB: {e}")
            return []

    async def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a memory by its ID."""
        try:
            result = self.collection.get(ids=[memory_id])
            if not result or not result.get("ids"):
                return None
            
            return {
                "id": result["ids"][0],
                "content": result["documents"][0],
                "metadata": result["metadatas"][0],
                "distance": None,
            }
        except Exception as e:
            logger.error(f"Error getting memory from ChromaDB: {e}")
            return None

    async def get_all_memories(self) -> List[Dict[str, Any]]:
        """Retrieve all memories from the collection."""
        try:
            results = self.collection.get()
            if not results or not results.get("ids"):
                return []

            formatted = []
            for i, memory_id in enumerate(results["ids"]):
                formatted.append({
                    "id": memory_id,
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i],
                    "distance": None,
                })
            return formatted
        except Exception as e:
            logger.error(f"Error getting all memories from ChromaDB: {e}")
            return []

    async def update_memory(self, memory_id: str, content: str, metadata: Dict[str, Any]):
        """Update an existing memory."""
        try:
            self.collection.update(
                ids=[memory_id],
                documents=[content],
                metadatas=[metadata]
            )
            logger.debug(f"Updated memory {memory_id} in ChromaDB.")
        except Exception as e:
            logger.error(f"Error updating memory in ChromaDB: {e}")

    async def delete_memory(self, memory_id: str):
        """Delete a memory from the collection."""
        try:
            self.collection.delete(ids=[memory_id])
            logger.debug(f"Deleted memory {memory_id} from ChromaDB.")
        except Exception as e:
            logger.error(f"Error deleting memory from ChromaDB: {e}")
            
    async def cleanup(self):
        """Clean up resources."""
        logger.info("ChromaDBManager cleaned up.")