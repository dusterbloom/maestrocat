"""
Security Audit Logging and Monitoring Framework

Comprehensive audit logging system providing:
- Security event logging with structured data
- Access logging for all requests
- Real-time security monitoring and alerting
- Log aggregation and analysis
- Compliance reporting capabilities
- Threat detection based on log patterns
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging
from pathlib import Path
import gzip
import hashlib
from loguru import logger
import asyncio

class LogLevel(Enum):
    """Log severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class EventCategory(Enum):
    """Security event categories"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ACCESS = "access"
    CONFIGURATION = "configuration"
    SYSTEM = "system"
    ATTACK = "attack"
    DATA = "data"

@dataclass
class SecurityEvent:
    """Structured security event"""
    timestamp: float
    event_type: str
    category: EventCategory
    level: LogLevel
    ip_address: str
    user_id: Optional[str]
    endpoint: str
    message: str
    details: Dict[str, Any]
    session_id: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'event_type': self.event_type,
            'category': self.category.value,
            'level': self.level.value,
            'ip_address': self.ip_address,
            'user_id': self.user_id,
            'endpoint': self.endpoint,
            'message': self.message,
            'details': self.details,
            'session_id': self.session_id,
            'user_agent': self.user_agent,
            'request_id': self.request_id
        }

@dataclass
class AccessLogEntry:
    """Access log entry for HTTP requests"""
    timestamp: float
    ip_address: str
    user_id: Optional[str]
    method: str
    endpoint: str
    status_code: int
    processing_time_ms: float
    bytes_sent: int = 0
    bytes_received: int = 0
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'ip_address': self.ip_address,
            'user_id': self.user_id,
            'method': self.method,
            'endpoint': self.endpoint,
            'status_code': self.status_code,
            'processing_time_ms': self.processing_time_ms,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'user_agent': self.user_agent,
            'referer': self.referer,
            'session_id': self.session_id,
            'request_id': self.request_id
        }

class ThreatPattern:
    """Threat detection pattern"""
    
    def __init__(self, name: str, description: str, 
                 detector: Callable[[List[SecurityEvent]], bool]):
        self.name = name
        self.description = description
        self.detector = detector
        self.last_triggered = None
        self.trigger_count = 0

class SecurityAuditLogger:
    """Main security audit logging system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.log_dir = Path(config.get('log_directory', 'logs/security'))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Logging configuration
        self.log_level = LogLevel(config.get('log_level', 'info'))
        self.max_log_size_mb = config.get('max_log_size_mb', 100)
        self.log_retention_days = config.get('log_retention_days', 90)
        self.compression_enabled = config.get('compression_enabled', True)
        
        # Real-time monitoring
        self.monitoring_enabled = config.get('monitoring_enabled', True)
        self.alert_thresholds = config.get('alert_thresholds', {})
        self.event_buffer_size = config.get('event_buffer_size', 1000)
        
        # Event storage
        self.security_events: List[SecurityEvent] = []
        self.access_logs: List[AccessLogEntry] = []
        self.event_lock = asyncio.Lock()
        
        # File handles for different log types
        self.security_log_file = None
        self.access_log_file = None
        
        # Background tasks
        self.flush_task = None
        self.monitoring_task = None
        self.cleanup_task = None
        
        # Threat detection
        self.threat_patterns = self._initialize_threat_patterns()
        
        # Event counters for monitoring
        self.event_counters = {
            'authentication_failures': 0,
            'authorization_failures': 0,
            'rate_limit_violations': 0,
            'validation_failures': 0,
            'suspicious_activity': 0
        }
        
        # Configure structured logging
        self._configure_structured_logging()
    
    def _configure_structured_logging(self):
        """Configure structured JSON logging"""
        # Create custom formatter for security logs
        def security_formatter(record):
            return json.dumps({
                'timestamp': record['time'].timestamp(),
                'level': record['level'].name,
                'module': record['name'],
                'message': record['message'],
                'extra': record.get('extra', {})
            }) + '\n'
        
        # Add file handler for security events
        security_log_path = self.log_dir / f"security_{datetime.now().strftime('%Y%m%d')}.log"
        logger.add(
            security_log_path,
            format=security_formatter,
            level=self.log_level.value.upper(),
            rotation=f"{self.max_log_size_mb} MB",
            retention=f"{self.log_retention_days} days",
            compression="gz" if self.compression_enabled else None,
            filter=lambda record: record.get('extra', {}).get('security_event', False)
        )
        
        # Add file handler for access logs
        access_log_path = self.log_dir / f"access_{datetime.now().strftime('%Y%m%d')}.log"
        logger.add(
            access_log_path,
            format=security_formatter,
            level="INFO",
            rotation=f"{self.max_log_size_mb} MB",
            retention=f"{self.log_retention_days} days",
            compression="gz" if self.compression_enabled else None,
            filter=lambda record: record.get('extra', {}).get('access_log', False)
        )
    
    def _initialize_threat_patterns(self) -> List[ThreatPattern]:
        """Initialize threat detection patterns"""
        patterns = []
        
        # Brute force attack detection
        def detect_brute_force(events: List[SecurityEvent]) -> bool:
            """Detect brute force authentication attempts"""
            recent_events = [e for e in events if e.timestamp > time.time() - 300]  # Last 5 minutes
            auth_failures = [e for e in recent_events if e.event_type == "authentication_failed"]
            
            # Group by IP address
            ip_failures = {}
            for event in auth_failures:
                ip_failures[event.ip_address] = ip_failures.get(event.ip_address, 0) + 1
            
            # Check for excessive failures from single IP
            return any(count >= 10 for count in ip_failures.values())
        
        patterns.append(ThreatPattern(
            name="brute_force_attack",
            description="Multiple authentication failures from single IP",
            detector=detect_brute_force
        ))
        
        # SQL injection attempt detection
        def detect_sql_injection(events: List[SecurityEvent]) -> bool:
            """Detect potential SQL injection attempts"""
            recent_events = [e for e in events if e.timestamp > time.time() - 60]  # Last minute
            validation_failures = [e for e in recent_events if e.event_type == "input_validation_failed"]
            
            sql_keywords = ['union', 'select', 'insert', 'update', 'delete', 'drop', 'exec']
            
            for event in validation_failures:
                errors = event.details.get('errors', [])
                for error in errors:
                    if any(keyword in error.lower() for keyword in sql_keywords):
                        return True
            
            return False
        
        patterns.append(ThreatPattern(
            name="sql_injection_attempt",
            description="Potential SQL injection patterns detected",
            detector=detect_sql_injection
        ))
        
        # Distributed attack detection
        def detect_distributed_attack(events: List[SecurityEvent]) -> bool:
            """Detect distributed attacks from multiple IPs"""
            recent_events = [e for e in events if e.timestamp > time.time() - 60]  # Last minute
            unique_ips = set(e.ip_address for e in recent_events)
            
            # High number of unique IPs with errors indicates distributed attack
            error_events = [e for e in recent_events if e.level in [LogLevel.ERROR, LogLevel.CRITICAL]]
            
            return len(unique_ips) > 50 and len(error_events) > 100
        
        patterns.append(ThreatPattern(
            name="distributed_attack",
            description="High volume of errors from many different IPs",
            detector=detect_distributed_attack
        ))
        
        # Privilege escalation detection
        def detect_privilege_escalation(events: List[SecurityEvent]) -> bool:
            """Detect potential privilege escalation attempts"""
            recent_events = [e for e in events if e.timestamp > time.time() - 300]  # Last 5 minutes
            authz_failures = [e for e in recent_events if e.event_type == "authorization_failed"]
            
            # Group by user
            user_failures = {}
            for event in authz_failures:
                if event.user_id:
                    user_failures[event.user_id] = user_failures.get(event.user_id, 0) + 1
            
            # Check for excessive authorization failures from single user
            return any(count >= 5 for count in user_failures.values())
        
        patterns.append(ThreatPattern(
            name="privilege_escalation_attempt",
            description="Multiple authorization failures from single user",
            detector=detect_privilege_escalation
        ))
        
        return patterns
    
    async def start(self):
        """Start audit logging system"""
        # Start background tasks
        if self.flush_task is None:
            self.flush_task = asyncio.create_task(self._flush_loop())
        
        if self.monitoring_enabled and self.monitoring_task is None:
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Security audit logging system started")
    
    async def stop(self):
        """Stop audit logging system"""
        # Cancel background tasks
        for task in [self.flush_task, self.monitoring_task, self.cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Flush remaining events
        await self._flush_events()
        
        logger.info("Security audit logging system stopped")
    
    async def log_security_event(self, event_type: str, ip_address: str, 
                                user_id: Optional[str], endpoint: str,
                                timestamp: float, extra_data: Dict[str, Any] = None,
                                level: LogLevel = LogLevel.INFO,
                                category: EventCategory = EventCategory.SYSTEM,
                                message: str = None):
        """Log a security event"""
        if message is None:
            message = f"Security event: {event_type}"
        
        event = SecurityEvent(
            timestamp=timestamp,
            event_type=event_type,
            category=category,
            level=level,
            ip_address=ip_address,
            user_id=user_id,
            endpoint=endpoint,
            message=message,
            details=extra_data or {}
        )
        
        async with self.event_lock:
            self.security_events.append(event)
            
            # Update event counters
            if event_type in self.event_counters:
                self.event_counters[event_type] += 1
            
            # Trigger immediate logging for critical events
            if level == LogLevel.CRITICAL:
                await self._log_event_immediately(event)
            
            # Limit buffer size
            if len(self.security_events) > self.event_buffer_size:
                await self._flush_events()
        
        # Log to structured logger
        logger.bind(security_event=True).log(
            level.value.upper(),
            message,
            extra={
                'event_type': event_type,
                'ip_address': ip_address,
                'user_id': user_id,
                'endpoint': endpoint,
                'details': extra_data or {}
            }
        )
    
    async def log_access(self, ip_address: str, user_id: Optional[str],
                        endpoint: str, method: str, status_code: int,
                        processing_time_ms: float, timestamp: float,
                        user_agent: Optional[str] = None,
                        bytes_sent: int = 0, bytes_received: int = 0):
        """Log access request"""
        entry = AccessLogEntry(
            timestamp=timestamp,
            ip_address=ip_address,
            user_id=user_id,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            processing_time_ms=processing_time_ms,
            bytes_sent=bytes_sent,
            bytes_received=bytes_received,
            user_agent=user_agent
        )
        
        async with self.event_lock:
            self.access_logs.append(entry)
            
            # Limit buffer size
            if len(self.access_logs) > self.event_buffer_size:
                await self._flush_events()
        
        # Log to structured logger
        logger.bind(access_log=True).info(
            f"{method} {endpoint} {status_code} {processing_time_ms:.1f}ms",
            extra={
                'ip_address': ip_address,
                'user_id': user_id,
                'method': method,
                'endpoint': endpoint,
                'status_code': status_code,
                'processing_time_ms': processing_time_ms,
                'user_agent': user_agent
            }
        )
    
    async def _log_event_immediately(self, event: SecurityEvent):
        """Immediately log critical events"""
        # Write directly to file for critical events
        critical_log_path = self.log_dir / f"critical_{datetime.now().strftime('%Y%m%d')}.log"
        
        try:
            with open(critical_log_path, 'a') as f:
                f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write critical event: {e}")
    
    async def _flush_loop(self):
        """Background task to flush events periodically"""
        while True:
            try:
                await asyncio.sleep(30)  # Flush every 30 seconds
                await self._flush_events()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush loop: {e}")
    
    async def _flush_events(self):
        """Flush buffered events to disk"""
        async with self.event_lock:
            if self.security_events:
                await self._write_security_events(self.security_events.copy())
                self.security_events.clear()
            
            if self.access_logs:
                await self._write_access_logs(self.access_logs.copy())
                self.access_logs.clear()
    
    async def _write_security_events(self, events: List[SecurityEvent]):
        """Write security events to file"""
        security_log_path = self.log_dir / f"security_events_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        try:
            with open(security_log_path, 'a') as f:
                for event in events:
                    f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write security events: {e}")
    
    async def _write_access_logs(self, logs: List[AccessLogEntry]):
        """Write access logs to file"""
        access_log_path = self.log_dir / f"access_logs_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        try:
            with open(access_log_path, 'a') as f:
                for log_entry in logs:
                    f.write(json.dumps(log_entry.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write access logs: {e}")
    
    async def _monitoring_loop(self):
        """Background task for real-time threat monitoring"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._check_threat_patterns()
                await self._check_alert_thresholds()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
    
    async def _check_threat_patterns(self):
        """Check for threat patterns in recent events"""
        async with self.event_lock:
            recent_events = [e for e in self.security_events 
                           if e.timestamp > time.time() - 600]  # Last 10 minutes
        
        for pattern in self.threat_patterns:
            try:
                if pattern.detector(recent_events):
                    pattern.trigger_count += 1
                    pattern.last_triggered = time.time()
                    
                    await self.log_security_event(
                        event_type="threat_detected",
                        ip_address="system",
                        user_id=None,
                        endpoint="monitoring",
                        timestamp=time.time(),
                        level=LogLevel.CRITICAL,
                        category=EventCategory.ATTACK,
                        message=f"Threat pattern detected: {pattern.name}",
                        extra_data={
                            'pattern_name': pattern.name,
                            'pattern_description': pattern.description,
                            'trigger_count': pattern.trigger_count
                        }
                    )
                    
                    logger.critical(f"THREAT DETECTED: {pattern.name} - {pattern.description}")
                    
            except Exception as e:
                logger.error(f"Error checking threat pattern {pattern.name}: {e}")
    
    async def _check_alert_thresholds(self):
        """Check if alert thresholds are exceeded"""
        for event_type, threshold in self.alert_thresholds.items():
            current_count = self.event_counters.get(event_type, 0)
            
            if current_count >= threshold:
                await self.log_security_event(
                    event_type="alert_threshold_exceeded",
                    ip_address="system",
                    user_id=None,
                    endpoint="monitoring",
                    timestamp=time.time(),
                    level=LogLevel.ERROR,
                    category=EventCategory.SYSTEM,
                    message=f"Alert threshold exceeded for {event_type}",
                    extra_data={
                        'event_type': event_type,
                        'current_count': current_count,
                        'threshold': threshold
                    }
                )
                
                # Reset counter after alert
                self.event_counters[event_type] = 0
    
    async def _cleanup_loop(self):
        """Background task to clean up old log files"""
        while True:
            try:
                await asyncio.sleep(86400)  # Check daily
                await self._cleanup_old_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_old_logs(self):
        """Clean up old log files beyond retention period"""
        cutoff_date = datetime.now() - timedelta(days=self.log_retention_days)
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    logger.info(f"Deleted old log file: {log_file}")
            except Exception as e:
                logger.error(f"Error deleting old log file {log_file}: {e}")
    
    def get_security_metrics(self) -> Dict[str, Any]:
        """Get current security metrics"""
        return {
            'event_counters': self.event_counters.copy(),
            'threat_patterns': {
                pattern.name: {
                    'trigger_count': pattern.trigger_count,
                    'last_triggered': pattern.last_triggered,
                    'description': pattern.description
                }
                for pattern in self.threat_patterns
            },
            'buffer_status': {
                'security_events': len(self.security_events),
                'access_logs': len(self.access_logs),
                'buffer_size_limit': self.event_buffer_size
            }
        }
    
    async def search_events(self, event_type: Optional[str] = None,
                          ip_address: Optional[str] = None,
                          user_id: Optional[str] = None,
                          start_time: Optional[float] = None,
                          end_time: Optional[float] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """Search security events with filters"""
        async with self.event_lock:
            events = self.security_events.copy()
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if ip_address:
            events = [e for e in events if e.ip_address == ip_address]
        
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        
        # Sort by timestamp (newest first) and limit
        events.sort(key=lambda e: e.timestamp, reverse=True)
        events = events[:limit]
        
        return [event.to_dict() for event in events]