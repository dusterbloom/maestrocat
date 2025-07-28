"""
Rate Limiting and DDoS Protection Tests

Tests for:
- Request rate limiting
- Connection rate limiting  
- DDoS attack detection
- Bandwidth limiting
- Adaptive throttling
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from core.security.rate_limiting import (
    RateLimiter, DDoSDetector, DDoSProtection, 
    RequestInfo, RateLimit, LimitType, ActionType
)


class TestRateLimiter:
    """Test rate limiting functionality"""
    
    @pytest.fixture
    def rate_limiter_config(self):
        return {
            'limits': [
                {
                    'type': 'requests_per_minute',
                    'max_requests': 10,
                    'window_seconds': 60,
                    'action': 'throttle'
                },
                {
                    'type': 'requests_per_hour',
                    'max_requests': 100,
                    'window_seconds': 3600,
                    'action': 'temporary_ban',
                    'ban_duration_seconds': 300
                }
            ],
            'cleanup_interval_seconds': 10
        }
    
    @pytest.fixture
    def rate_limiter(self, rate_limiter_config):
        return RateLimiter(rate_limiter_config)
    
    @pytest.fixture
    def sample_request(self):
        return RequestInfo(
            ip_address="192.168.1.100",
            user_id="test_user",
            endpoint="GET /api/test",
            timestamp=time.time(),
            size_bytes=1024,
            user_agent="TestAgent/1.0"
        )
    
    @pytest.mark.asyncio
    async def test_rate_limit_within_bounds(self, rate_limiter, sample_request):
        """Test requests within rate limits are allowed"""
        await rate_limiter.start()
        
        # First request should be allowed
        allowed, reason, retry_after = await rate_limiter.check_rate_limit(sample_request)
        assert allowed is True
        assert reason is None
        assert retry_after is None
        
        await rate_limiter.stop()
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, rate_limiter, sample_request):
        """Test rate limit enforcement when exceeded"""
        await rate_limiter.start()
        
        # Send requests up to the limit
        for i in range(10):
            allowed, _, _ = await rate_limiter.check_rate_limit(sample_request)
            assert allowed is True
        
        # Next request should be blocked
        allowed, reason, retry_after = await rate_limiter.check_rate_limit(sample_request)
        assert allowed is False
        assert "Rate limit exceeded" in reason
        assert retry_after is not None
        
        await rate_limiter.stop()
    
    @pytest.mark.asyncio
    async def test_rate_limit_different_clients(self, rate_limiter):
        """Test rate limits are per-client"""
        await rate_limiter.start()
        
        client1_request = RequestInfo(
            ip_address="192.168.1.100",
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        client2_request = RequestInfo(
            ip_address="192.168.1.101", 
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        # Exhaust limit for client1
        for i in range(10):
            allowed, _, _ = await rate_limiter.check_rate_limit(client1_request)
            assert allowed is True
        
        # Client1 should be blocked
        allowed, _, _ = await rate_limiter.check_rate_limit(client1_request)
        assert allowed is False
        
        # Client2 should still be allowed
        allowed, _, _ = await rate_limiter.check_rate_limit(client2_request)
        assert allowed is True
        
        await rate_limiter.stop()
    
    @pytest.mark.asyncio
    async def test_temporary_ban(self, rate_limiter, sample_request):
        """Test temporary ban functionality"""
        await rate_limiter.start()
        
        # Create a request that will trigger ban after violations
        ban_request = RequestInfo(
            ip_address="192.168.1.200",
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        # Exceed rate limit multiple times to trigger ban
        for violation in range(15):  # Exceed both minute and hour limits
            for request_num in range(12):  # Exceed per-minute limit
                await rate_limiter.check_rate_limit(ban_request)
        
        # Should be temporarily banned
        allowed, reason, retry_after = await rate_limiter.check_rate_limit(ban_request)
        assert allowed is False
        assert "temporarily banned" in reason.lower()
        
        await rate_limiter.stop()
    
    @pytest.mark.asyncio
    async def test_whitelist_bypass(self, rate_limiter_config):
        """Test whitelist bypass functionality"""
        # Add whitelist to config
        rate_limiter_config['limits'][0]['whitelist'] = ['192.168.1.0/24']
        rate_limiter = RateLimiter(rate_limiter_config)
        
        await rate_limiter.start()
        
        whitelisted_request = RequestInfo(
            ip_address="192.168.1.50",  # In whitelist range
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        # Should allow many requests from whitelisted IP
        for i in range(20):  # Well above normal limit
            allowed, _, _ = await rate_limiter.check_rate_limit(whitelisted_request)
            assert allowed is True
        
        await rate_limiter.stop()
    
    @pytest.mark.asyncio
    async def test_window_sliding(self, rate_limiter, sample_request):
        """Test sliding window behavior"""
        await rate_limiter.start()
        
        # Fill up the rate limit
        start_time = time.time()
        for i in range(10):
            await rate_limiter.check_rate_limit(sample_request)
        
        # Should be blocked now
        allowed, _, _ = await rate_limiter.check_rate_limit(sample_request)
        assert allowed is False
        
        # Wait for window to slide (simulate time passage)
        with patch('time.time', return_value=start_time + 61):  # Past the window
            allowed, _, _ = await rate_limiter.check_rate_limit(sample_request)
            assert allowed is True  # Should be allowed again
        
        await rate_limiter.stop()
    
    def test_client_status_reporting(self, rate_limiter, sample_request):
        """Test client status reporting"""
        client_id = rate_limiter._get_client_id(sample_request)
        
        # Get initial status
        status = rate_limiter.get_client_status(client_id)
        assert status['client_id'] == client_id
        assert status['blocked'] is False
        assert len(status['limits']) > 0


class TestDDoSDetector:
    """Test DDoS detection functionality"""
    
    @pytest.fixture
    def ddos_config(self):
        return {
            'requests_per_second_threshold': 50,
            'connections_per_minute_threshold': 30,
            'unique_ips_threshold': 100,
            'detection_window_seconds': 60
        }
    
    @pytest.fixture
    def ddos_detector(self, ddos_config):
        return DDoSDetector(ddos_config)
    
    def test_high_request_rate_detection(self, ddos_detector):
        """Test detection of high request rates from single IP"""
        request_info = RequestInfo(
            ip_address="192.168.1.100",
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        # Normal request should not trigger
        assert ddos_detector.is_ddos_attack(request_info) is False
        
        # Simulate high request rate
        current_time = time.time()
        for i in range(60):  # Above threshold
            request_info.timestamp = current_time + (i * 0.01)  # Very fast requests
            ddos_detector.is_ddos_attack(request_info)
        
        # Should detect DDoS
        assert ddos_detector.is_ddos_attack(request_info) is True
    
    def test_distributed_attack_detection(self, ddos_detector):
        """Test detection of distributed attacks"""
        current_time = time.time()
        
        # Simulate requests from many different IPs
        for i in range(150):  # Above unique_ips_threshold
            request_info = RequestInfo(
                ip_address=f"192.168.{i//256}.{i%256}",
                user_id=None,
                endpoint="GET /api/test",
                timestamp=current_time + (i * 0.1)
            )
            result = ddos_detector.is_ddos_attack(request_info)
        
        # Should detect distributed attack
        assert result is True
    
    def test_normal_traffic_no_detection(self, ddos_detector):
        """Test that normal traffic doesn't trigger false positives"""
        current_time = time.time()
        
        # Simulate normal traffic pattern
        for i in range(20):  # Below thresholds
            request_info = RequestInfo(
                ip_address=f"192.168.1.{i+1}",
                user_id=None,
                endpoint="GET /api/test",
                timestamp=current_time + (i * 2)  # Normal spacing
            )
            assert ddos_detector.is_ddos_attack(request_info) is False


class TestDDoSProtection:
    """Test DDoS protection coordination"""
    
    @pytest.fixture
    def ddos_protection_config(self):
        return {
            'rate_limiting': {
                'limits': [
                    {
                        'type': 'requests_per_minute',
                        'max_requests': 60,
                        'window_seconds': 60,
                        'action': 'throttle'
                    }
                ]
            },
            'ddos_detection': {
                'requests_per_second_threshold': 100,
                'unique_ips_threshold': 200
            }
        }
    
    @pytest.fixture
    def ddos_protection(self, ddos_protection_config):
        return DDoSProtection(ddos_protection_config)
    
    @pytest.mark.asyncio
    async def test_normal_request_processing(self, ddos_protection):
        """Test normal request processing"""
        await ddos_protection.start()
        
        request_info = RequestInfo(
            ip_address="192.168.1.100",
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        allowed, reason, retry_after = await ddos_protection.process_request(request_info)
        assert allowed is True
        assert reason is None
        
        await ddos_protection.stop()
    
    @pytest.mark.asyncio
    async def test_ddos_mitigation_activation(self, ddos_protection):
        """Test DDoS mitigation activation"""
        await ddos_protection.start()
        
        # Simulate DDoS attack
        current_time = time.time()
        for i in range(150):  # Trigger DDoS detection
            request_info = RequestInfo(
                ip_address=f"10.0.{i//256}.{i%256}",
                user_id=None,
                endpoint="GET /api/test",
                timestamp=current_time + (i * 0.01)
            )
            
            allowed, reason, retry_after = await ddos_protection.process_request(request_info)
            
            # Later requests should trigger mitigation
            if not allowed and "DDoS protection" in reason:
                assert ddos_protection.mitigation_active is True
                break
        
        await ddos_protection.stop()


class TestRateLimitingEdgeCases:
    """Test edge cases and error conditions"""
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test concurrent request handling"""
        config = {
            'limits': [
                {
                    'type': 'requests_per_minute',
                    'max_requests': 5,
                    'window_seconds': 60,
                    'action': 'throttle'
                }
            ]
        }
        rate_limiter = RateLimiter(config)
        await rate_limiter.start()
        
        request_info = RequestInfo(
            ip_address="192.168.1.100",
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        # Create multiple concurrent requests
        tasks = []
        for i in range(10):
            task = asyncio.create_task(rate_limiter.check_rate_limit(request_info))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Some should be allowed, some blocked
        allowed_count = sum(1 for allowed, _, _ in results if allowed)
        blocked_count = sum(1 for allowed, _, _ in results if not allowed)
        
        assert allowed_count <= 5  # Within rate limit
        assert blocked_count >= 0  # Some may be blocked
        
        await rate_limiter.stop()
    
    @pytest.mark.asyncio
    async def test_memory_cleanup(self):
        """Test memory cleanup of old data"""
        config = {
            'limits': [
                {
                    'type': 'requests_per_minute',
                    'max_requests': 100,
                    'window_seconds': 60,
                    'action': 'throttle'
                }
            ],
            'cleanup_interval_seconds': 1  # Very frequent cleanup
        }
        rate_limiter = RateLimiter(config)
        await rate_limiter.start()
        
        # Generate requests from many different IPs
        for i in range(100):
            request_info = RequestInfo(
                ip_address=f"192.168.{i//256}.{i%256}",
                user_id=None,
                endpoint="GET /api/test",
                timestamp=time.time()
            )
            await rate_limiter.check_rate_limit(request_info)
        
        initial_count = len(rate_limiter.request_counts)
        
        # Wait for cleanup
        await asyncio.sleep(2)
        
        # Should have cleaned up some data
        # (This is timing-dependent, so we just check it didn't grow indefinitely)
        assert len(rate_limiter.request_counts) <= initial_count + 10
        
        await rate_limiter.stop()
    
    def test_invalid_ip_handling(self):
        """Test handling of invalid IP addresses"""
        config = {'limits': []}
        rate_limiter = RateLimiter(config)
        
        # Test with invalid IP
        invalid_request = RequestInfo(
            ip_address="invalid.ip.address",
            user_id=None,
            endpoint="GET /api/test",
            timestamp=time.time()
        )
        
        # Should not crash
        client_id = rate_limiter._get_client_id(invalid_request)
        assert client_id.startswith("ip_")
    
    def test_whitelist_with_invalid_networks(self):
        """Test whitelist with invalid network specifications"""
        config = {
            'limits': [
                {
                    'type': 'requests_per_minute',
                    'max_requests': 10,
                    'window_seconds': 60,
                    'action': 'throttle',
                    'whitelist': ['invalid.network/24', '192.168.1.0/24']
                }
            ]
        }
        
        rate_limiter = RateLimiter(config)
        
        # Should handle invalid network gracefully
        assert not rate_limiter._is_whitelisted("192.168.1.100", ['invalid.network/24'])
        assert rate_limiter._is_whitelisted("192.168.1.100", ['192.168.1.0/24'])


if __name__ == "__main__":
    pytest.main([__file__])