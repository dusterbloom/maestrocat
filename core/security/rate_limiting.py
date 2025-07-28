"""
Rate Limiting and DDoS Protection Framework

Comprehensive protection against abuse including:
- Request rate limiting per IP/user
- Connection rate limiting for WebSockets
- Resource consumption limits
- DDoS attack detection and mitigation
- Adaptive throttling based on system load
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, deque
import ipaddress
from loguru import logger

class LimitType(Enum):
    """Types of rate limits"""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    REQUESTS_PER_HOUR = "requests_per_hour"
    CONNECTIONS_PER_MINUTE = "connections_per_minute"
    BANDWIDTH_PER_SECOND = "bandwidth_per_second"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"

class ActionType(Enum):
    """Actions to take when limits are exceeded"""
    THROTTLE = "throttle"
    REJECT = "reject"
    CAPTCHA = "captcha"
    TEMPORARY_BAN = "temporary_ban"
    PERMANENT_BAN = "permanent_ban"

@dataclass
class RateLimit:
    """Rate limit configuration"""
    limit_type: LimitType
    max_requests: int
    window_seconds: int
    action: ActionType
    ban_duration_seconds: int = 0
    whitelist: List[str] = None
    
    def __post_init__(self):
        if self.whitelist is None:
            self.whitelist = []

@dataclass
class RequestInfo:
    """Information about a request"""
    ip_address: str
    user_id: Optional[str]
    endpoint: str
    timestamp: float
    size_bytes: int = 0
    user_agent: Optional[str] = None

@dataclass
class LimitStatus:
    """Current status of rate limits for a client"""
    client_id: str
    current_requests: int
    max_requests: int
    window_start: float
    window_end: float
    blocked_until: Optional[float] = None
    violations: int = 0

class RateLimiter:
    """Main rate limiting implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.limits: List[RateLimit] = self._parse_limits_config(config.get('limits', []))
        
        # Storage for rate limit counters
        self.request_counts: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        self.blocked_clients: Dict[str, float] = {}  # client_id -> unblock_time
        self.violation_counts: Dict[str, int] = defaultdict(int)
        
        # DDoS detection
        self.ddos_detector = DDoSDetector(config.get('ddos_config', {}))
        
        # Cleanup task
        self.cleanup_task = None
        self.cleanup_interval = config.get('cleanup_interval_seconds', 300)  # 5 minutes
        
    def _parse_limits_config(self, limits_config: List[Dict[str, Any]]) -> List[RateLimit]:
        """Parse rate limits from configuration"""
        limits = []
        for limit_config in limits_config:
            try:
                limit = RateLimit(
                    limit_type=LimitType(limit_config['type']),
                    max_requests=limit_config['max_requests'],
                    window_seconds=limit_config['window_seconds'],
                    action=ActionType(limit_config['action']),
                    ban_duration_seconds=limit_config.get('ban_duration_seconds', 0),
                    whitelist=limit_config.get('whitelist', [])
                )
                limits.append(limit)
            except (KeyError, ValueError) as e:
                logger.error(f"Invalid rate limit configuration: {e}")
        
        return limits
    
    async def start(self):
        """Start the rate limiter"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Rate limiter started")
    
    async def stop(self):
        """Stop the rate limiter"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None
            logger.info("Rate limiter stopped")
    
    async def check_rate_limit(self, request_info: RequestInfo) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Check if request should be allowed
        
        Returns:
            (allowed, reason, retry_after_seconds)
        """
        client_id = self._get_client_id(request_info)
        current_time = time.time()
        
        # Check if client is currently blocked
        if client_id in self.blocked_clients:
            unblock_time = self.blocked_clients[client_id]
            if current_time < unblock_time:
                retry_after = int(unblock_time - current_time)
                return False, "Client temporarily banned", retry_after
            else:
                # Unblock client
                del self.blocked_clients[client_id]
        
        # Check each rate limit
        for limit in self.limits:
            if self._is_whitelisted(request_info.ip_address, limit.whitelist):
                continue
            
            allowed, reason, retry_after = await self._check_single_limit(
                client_id, request_info, limit, current_time
            )
            
            if not allowed:
                # Handle violation
                await self._handle_violation(client_id, request_info, limit)
                return False, reason, retry_after
        
        # Record the request
        await self._record_request(client_id, request_info, current_time)
        
        # Check for DDoS patterns
        if self.ddos_detector.is_ddos_attack(request_info):
            logger.warning(f"Potential DDoS attack detected from {request_info.ip_address}")
            await self._handle_ddos(request_info)
            return False, "DDoS protection activated", 60
        
        return True, None, None
    
    async def _check_single_limit(self, client_id: str, request_info: RequestInfo, 
                                 limit: RateLimit, current_time: float) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check a single rate limit"""
        limit_key = f"{limit.limit_type.value}_{limit.window_seconds}"
        
        # Get request history for this limit
        requests = self.request_counts[client_id][limit_key]
        
        # Remove old requests outside the window
        window_start = current_time - limit.window_seconds
        while requests and requests[0] < window_start:
            requests.popleft()
        
        # Check if limit is exceeded
        if len(requests) >= limit.max_requests:
            retry_after = int(limit.window_seconds - (current_time - requests[0]))
            reason = f"Rate limit exceeded: {limit.limit_type.value}"
            return False, reason, retry_after
        
        return True, None, None
    
    async def _record_request(self, client_id: str, request_info: RequestInfo, current_time: float):
        """Record a request for rate limiting"""
        for limit in self.limits:
            limit_key = f"{limit.limit_type.value}_{limit.window_seconds}"
            self.request_counts[client_id][limit_key].append(current_time)
    
    async def _handle_violation(self, client_id: str, request_info: RequestInfo, limit: RateLimit):
        """Handle rate limit violation"""
        self.violation_counts[client_id] += 1
        violations = self.violation_counts[client_id]
        
        logger.warning(f"Rate limit violation #{violations} for client {client_id}: {limit.limit_type.value}")
        
        # Apply action based on violation count and configuration
        if limit.action == ActionType.TEMPORARY_BAN and limit.ban_duration_seconds > 0:
            ban_until = time.time() + limit.ban_duration_seconds
            self.blocked_clients[client_id] = ban_until
            logger.info(f"Temporarily banned client {client_id} until {ban_until}")
        
        elif limit.action == ActionType.PERMANENT_BAN and violations >= 5:
            # Implement permanent ban logic (e.g., add to blacklist)
            logger.critical(f"Permanent ban triggered for client {client_id}")
    
    async def _handle_ddos(self, request_info: RequestInfo):
        """Handle detected DDoS attack"""
        # Implement DDoS mitigation
        logger.critical(f"DDoS attack handling for IP {request_info.ip_address}")
        
        # Could implement:
        # - IP blocking at firewall level
        # - Traffic shaping
        # - Challenge-response system
        # - Rate limiting by ASN/network
    
    def _get_client_id(self, request_info: RequestInfo) -> str:
        """Get unique client identifier"""
        if request_info.user_id:
            return f"user_{request_info.user_id}"
        return f"ip_{request_info.ip_address}"
    
    def _is_whitelisted(self, ip_address: str, whitelist: List[str]) -> bool:
        """Check if IP address is whitelisted"""
        if not whitelist:
            return False
        
        try:
            ip = ipaddress.ip_address(ip_address)
            for whitelist_entry in whitelist:
                if '/' in whitelist_entry:
                    # CIDR notation
                    network = ipaddress.ip_network(whitelist_entry, strict=False)
                    if ip in network:
                        return True
                else:
                    # Single IP
                    if ip == ipaddress.ip_address(whitelist_entry):
                        return True
        except ValueError:
            logger.warning(f"Invalid IP address format: {ip_address}")
        
        return False
    
    async def _cleanup_loop(self):
        """Periodic cleanup of old data"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_old_data(self):
        """Clean up old rate limiting data"""
        current_time = time.time()
        
        # Clean up old request counts
        for client_id in list(self.request_counts.keys()):
            client_data = self.request_counts[client_id]
            for limit_key in list(client_data.keys()):
                requests = client_data[limit_key]
                # Keep only recent requests (max window size)
                max_window = max(limit.window_seconds for limit in self.limits)
                cutoff = current_time - max_window
                
                while requests and requests[0] < cutoff:
                    requests.popleft()
                
                # Remove empty deques
                if not requests:
                    del client_data[limit_key]
            
            # Remove empty client data
            if not client_data:
                del self.request_counts[client_id]
        
        # Clean up expired bans
        expired_bans = [
            client_id for client_id, unblock_time in self.blocked_clients.items()
            if current_time >= unblock_time
        ]
        for client_id in expired_bans:
            del self.blocked_clients[client_id]
        
        logger.debug(f"Cleaned up rate limiting data. Active clients: {len(self.request_counts)}")
    
    def get_client_status(self, client_id: str) -> Dict[str, Any]:
        """Get current rate limit status for a client"""
        current_time = time.time()
        status = {
            'client_id': client_id,
            'blocked': client_id in self.blocked_clients,
            'blocked_until': self.blocked_clients.get(client_id),
            'violations': self.violation_counts.get(client_id, 0),
            'limits': []
        }
        
        client_data = self.request_counts.get(client_id, {})
        for limit in self.limits:
            limit_key = f"{limit.limit_type.value}_{limit.window_seconds}"
            requests = client_data.get(limit_key, deque())
            
            # Clean old requests
            window_start = current_time - limit.window_seconds
            recent_requests = [r for r in requests if r >= window_start]
            
            status['limits'].append({
                'type': limit.limit_type.value,
                'current_requests': len(recent_requests),
                'max_requests': limit.max_requests,
                'window_seconds': limit.window_seconds,
                'percentage_used': (len(recent_requests) / limit.max_requests) * 100
            })
        
        return status

class DDoSDetector:
    """Detects DDoS attack patterns"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.request_history: Dict[str, deque] = defaultdict(deque)
        self.connection_history: Dict[str, deque] = defaultdict(deque)
        
        # Thresholds
        self.requests_per_second_threshold = config.get('requests_per_second_threshold', 100)
        self.connections_per_minute_threshold = config.get('connections_per_minute_threshold', 50)
        self.unique_ips_threshold = config.get('unique_ips_threshold', 1000)
        
        # Time windows
        self.detection_window_seconds = config.get('detection_window_seconds', 60)
    
    def is_ddos_attack(self, request_info: RequestInfo) -> bool:
        """Detect if current traffic patterns indicate DDoS attack"""
        current_time = time.time()
        ip = request_info.ip_address
        
        # Record current request
        self.request_history[ip].append(current_time)
        
        # Clean old data
        self._cleanup_old_data(current_time)
        
        # Check various DDoS indicators
        return (
            self._check_request_rate(ip, current_time) or
            self._check_total_traffic(current_time) or
            self._check_distributed_attack(current_time)
        )
    
    def _check_request_rate(self, ip: str, current_time: float) -> bool:
        """Check if single IP is sending too many requests"""
        requests = self.request_history[ip]
        recent_requests = [r for r in requests if r >= current_time - 1]  # Last second
        
        if len(recent_requests) > self.requests_per_second_threshold:
            logger.warning(f"High request rate detected from {ip}: {len(recent_requests)}/sec")
            return True
        
        return False
    
    def _check_total_traffic(self, current_time: float) -> bool:
        """Check total traffic across all IPs"""
        total_requests = 0
        for requests in self.request_history.values():
            total_requests += len([r for r in requests if r >= current_time - 1])
        
        if total_requests > self.requests_per_second_threshold * 10:  # 10x normal
            logger.warning(f"Abnormally high total traffic: {total_requests}/sec")
            return True
        
        return False
    
    def _check_distributed_attack(self, current_time: float) -> bool:
        """Check for distributed attack patterns"""
        # Count unique IPs in detection window
        unique_ips = set()
        for ip, requests in self.request_history.items():
            if any(r >= current_time - self.detection_window_seconds for r in requests):
                unique_ips.add(ip)
        
        if len(unique_ips) > self.unique_ips_threshold:
            logger.warning(f"Distributed attack pattern detected: {len(unique_ips)} unique IPs")
            return True
        
        return False
    
    def _cleanup_old_data(self, current_time: float):
        """Clean up old request history"""
        cutoff = current_time - self.detection_window_seconds
        
        for ip in list(self.request_history.keys()):
            requests = self.request_history[ip]
            while requests and requests[0] < cutoff:
                requests.popleft()
            
            if not requests:
                del self.request_history[ip]

class DDoSProtection:
    """High-level DDoS protection coordination"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rate_limiter = RateLimiter(config.get('rate_limiting', {}))
        self.ddos_detector = DDoSDetector(config.get('ddos_detection', {}))
        
        # Mitigation strategies
        self.mitigation_active = False
        self.blocked_networks: List[str] = []
        
    async def start(self):
        """Start DDoS protection"""
        await self.rate_limiter.start()
        logger.info("DDoS protection activated")
    
    async def stop(self):
        """Stop DDoS protection"""
        await self.rate_limiter.stop()
        logger.info("DDoS protection deactivated")
    
    async def process_request(self, request_info: RequestInfo) -> Tuple[bool, Optional[str], Optional[int]]:
        """Process incoming request through DDoS protection"""
        # First check rate limits
        allowed, reason, retry_after = await self.rate_limiter.check_rate_limit(request_info)
        
        if not allowed:
            return False, reason, retry_after
        
        # Check for DDoS patterns
        if self.ddos_detector.is_ddos_attack(request_info):
            await self._activate_mitigation(request_info)
            return False, "DDoS protection active", 60
        
        return True, None, None
    
    async def _activate_mitigation(self, request_info: RequestInfo):
        """Activate DDoS mitigation measures"""
        if not self.mitigation_active:
            self.mitigation_active = True
            logger.critical("DDoS mitigation activated")
            
            # Implement mitigation strategies:
            # - Increase rate limiting
            # - Enable CAPTCHA challenges
            # - Block suspicious networks
            # - Contact upstream providers
            
            # Example: Block entire /24 network of attacking IP
            try:
                ip = ipaddress.ip_address(request_info.ip_address)
                if ip.version == 4:
                    network = f"{ip.exploded.rsplit('.', 1)[0]}.0/24"
                    if network not in self.blocked_networks:
                        self.blocked_networks.append(network)
                        logger.warning(f"Blocked network: {network}")
            except ValueError:
                pass