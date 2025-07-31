"""
SQLite Memory Manager for MaestroCat

Provides persistent storage for conversation history using SQLite.
Designed for simplicity, reliability, and performance.
"""

import sqlite3
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class SQLiteMemoryManager:
    """
    Manages SQLite storage for conversation memory with thread-safe operations.
    """
    
    def __init__(self, db_path: str = "data/memory/conversations.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread pool for database operations to avoid blocking
        self._executor = ThreadPoolExecutor(max_workers=1)
        
        # Initialize database
        self._init_database()
        
    def _init_database(self):
        """Initialize database with tables and indexes"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL DEFAULT (strftime('%s', 'now')),
                    metadata TEXT,
                    speaker_id TEXT,
                    confidence REAL,
                    language TEXT
                )
            """)
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    start_time REAL DEFAULT (strftime('%s', 'now')),
                    end_time REAL,
                    message_count INTEGER DEFAULT 0,
                    metadata TEXT
                )
            """)
            
            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON conversations(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON conversations(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_role ON conversations(role)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_speaker_id ON conversations(speaker_id)")
            
            conn.commit()
            
        logger.info(f"✅ SQLite database initialized at: {self.db_path}")
    
    async def store_message(self, 
                          session_id: str,
                          role: str,
                          content: str,
                          metadata: Optional[Dict[str, Any]] = None,
                          speaker_id: Optional[str] = None,
                          confidence: Optional[float] = None,
                          language: Optional[str] = None) -> int:
        """
        Store a conversation message asynchronously.
        
        Returns:
            Message ID from the database
        """
        def _store():
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Insert message
                cursor.execute("""
                    INSERT INTO conversations 
                    (session_id, role, content, metadata, speaker_id, confidence, language)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id, 
                    role, 
                    content,
                    json.dumps(metadata) if metadata else None,
                    speaker_id,
                    confidence,
                    language
                ))
                
                # Update session message count
                cursor.execute("""
                    UPDATE sessions 
                    SET message_count = message_count + 1
                    WHERE id = ?
                """, (session_id,))
                
                # Create session if it doesn't exist
                cursor.execute("""
                    INSERT OR IGNORE INTO sessions (id) VALUES (?)
                """, (session_id,))
                
                conn.commit()
                return cursor.lastrowid
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _store)
    
    async def get_conversation_history(self, 
                                     session_id: str,
                                     limit: int = 50,
                                     offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session.
        
        Returns:
            List of messages in chronological order
        """
        def _get_history():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, role, content, timestamp, metadata, 
                           speaker_id, confidence, language
                    FROM conversations
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, (session_id, limit, offset))
                
                rows = cursor.fetchall()
                
                # Convert to dicts and reverse for chronological order
                messages = []
                for row in reversed(rows):
                    msg = {
                        "id": row["id"],
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "speaker_id": row["speaker_id"],
                        "confidence": row["confidence"],
                        "language": row["language"]
                    }
                    if row["metadata"]:
                        msg["metadata"] = json.loads(row["metadata"])
                    messages.append(msg)
                
                return messages
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _get_history)
    
    async def search_conversations(self, 
                                 query: str,
                                 limit: int = 10,
                                 session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search conversations by content (simple text search).
        
        Returns:
            List of matching messages with context
        """
        def _search():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Build query
                sql = """
                    SELECT id, session_id, role, content, timestamp, 
                           speaker_id, confidence
                    FROM conversations
                    WHERE content LIKE ?
                """
                params = [f"%{query}%"]
                
                if session_id:
                    sql += " AND session_id = ?"
                    params.append(session_id)
                
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        "id": row["id"],
                        "session_id": row["session_id"],
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "speaker_id": row["speaker_id"],
                        "confidence": row["confidence"]
                    })
                
                return results
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _search)
    
    async def get_recent_context(self, 
                               session_id: str,
                               time_window_minutes: int = 5,
                               max_messages: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent conversation context within a time window.
        
        Returns:
            Recent messages within the specified time window
        """
        def _get_recent():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Calculate time threshold
                time_threshold = time.time() - (time_window_minutes * 60)
                
                cursor.execute("""
                    SELECT role, content, timestamp, speaker_id
                    FROM conversations
                    WHERE session_id = ? AND timestamp > ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (session_id, time_threshold, max_messages))
                
                rows = cursor.fetchall()
                
                # Convert and reverse for chronological order
                messages = []
                for row in reversed(rows):
                    messages.append({
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "speaker_id": row["speaker_id"]
                    })
                
                return messages
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _get_recent)
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session"""
        def _get_info():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, user_id, start_time, end_time, 
                           message_count, metadata
                    FROM sessions
                    WHERE id = ?
                """, (session_id,))
                
                row = cursor.fetchone()
                if row:
                    info = {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "message_count": row["message_count"]
                    }
                    if row["metadata"]:
                        info["metadata"] = json.loads(row["metadata"])
                    return info
                return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _get_info)
    
    async def end_session(self, session_id: str):
        """Mark a session as ended"""
        def _end():
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sessions
                    SET end_time = strftime('%s', 'now')
                    WHERE id = ?
                """, (session_id,))
                conn.commit()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, _end)
    
    async def cleanup_old_sessions(self, days_to_keep: int = 30):
        """Clean up old sessions and their messages"""
        def _cleanup():
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Calculate cutoff timestamp
                cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
                
                # Get old sessions
                cursor.execute("""
                    SELECT id FROM sessions
                    WHERE start_time < ?
                """, (cutoff_time,))
                
                old_sessions = [row[0] for row in cursor.fetchall()]
                
                if old_sessions:
                    # Delete old conversations
                    placeholders = ','.join('?' * len(old_sessions))
                    cursor.execute(f"""
                        DELETE FROM conversations
                        WHERE session_id IN ({placeholders})
                    """, old_sessions)
                    
                    # Delete old sessions
                    cursor.execute(f"""
                        DELETE FROM sessions
                        WHERE id IN ({placeholders})
                    """, old_sessions)
                    
                    conn.commit()
                    
                    logger.info(f"🧹 Cleaned up {len(old_sessions)} old sessions")
                
                return len(old_sessions)
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _cleanup)
    
    async def close(self):
        """Clean up resources"""
        self._executor.shutdown(wait=True)