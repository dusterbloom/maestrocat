"""
Authentication and Authorization Framework for MaestroCat

Provides secure authentication for WebSocket and HTTP endpoints with:
- JWT token-based authentication
- API key authentication
- Role-based access control (RBAC)
- Session management
- Multi-factor authentication support
"""

import os
import time
import hmac
import hashlib
import secrets
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import jwt
from cryptography.fernet import Fernet
from loguru import logger

class UserRole(Enum):
    """User roles for authorization"""
    ADMIN = "admin"
    OPERATOR = "operator" 
    VIEWER = "viewer"
    SERVICE = "service"

class AuthMethod(Enum):
    """Authentication methods"""
    JWT = "jwt"
    API_KEY = "api_key"
    SESSION = "session"

@dataclass
class User:
    """User representation"""
    id: str
    username: str
    roles: List[UserRole]
    created_at: datetime
    last_login: Optional[datetime] = None
    enabled: bool = True
    mfa_enabled: bool = False
    api_keys: List[str] = None
    
    def __post_init__(self):
        if self.api_keys is None:
            self.api_keys = []

@dataclass
class AuthContext:
    """Authentication context for requests"""
    user: User
    method: AuthMethod
    token: str
    expires_at: Optional[datetime] = None
    permissions: List[str] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = self._get_role_permissions()
    
    def _get_role_permissions(self) -> List[str]:
        """Get permissions based on user roles"""
        permissions = []
        for role in self.user.roles:
            permissions.extend(ROLE_PERMISSIONS.get(role, []))
        return list(set(permissions))  # Remove duplicates

# Role-based permissions mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        "config:read", "config:write", "config:delete",
        "users:read", "users:write", "users:delete",
        "system:control", "system:debug", "system:monitor",
        "api:access", "websocket:connect",
        "events:read", "events:clear",
        "metrics:read", "audit:read"
    ],
    UserRole.OPERATOR: [
        "config:read", "config:write",
        "system:control", "system:monitor", 
        "api:access", "websocket:connect",
        "events:read", "metrics:read"
    ],
    UserRole.VIEWER: [
        "config:read", "system:monitor",
        "api:access", "websocket:connect",
        "events:read", "metrics:read"
    ],
    UserRole.SERVICE: [
        "api:access", "system:monitor",
        "events:read", "metrics:read"
    ]
}

class AuthenticationManager:
    """Manages authentication for MaestroCat services"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.jwt_secret = config.get('jwt_secret') or self._generate_jwt_secret()
        self.jwt_algorithm = config.get('jwt_algorithm', 'HS256')
        self.jwt_expiry = config.get('jwt_expiry_hours', 24)
        self.api_key_length = config.get('api_key_length', 32)
        
        # User storage (in production, use database)
        self.users: Dict[str, User] = {}
        self.api_keys: Dict[str, str] = {}  # api_key -> user_id
        self.sessions: Dict[str, AuthContext] = {}
        
        # Initialize encryption for sensitive data
        self.fernet = Fernet(self._get_encryption_key())
        
        # Create default admin user if configured
        self._create_default_users()
        
    def _generate_jwt_secret(self) -> str:
        """Generate a secure JWT secret"""
        secret = secrets.token_urlsafe(64)
        logger.warning("Generated new JWT secret. Set MAESTROCAT_JWT_SECRET environment variable in production!")
        return secret
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key for sensitive data"""
        key = os.getenv('MAESTROCAT_ENCRYPTION_KEY')
        if not key:
            key = Fernet.generate_key()
            logger.warning("Generated new encryption key. Set MAESTROCAT_ENCRYPTION_KEY environment variable in production!")
        return key if isinstance(key, bytes) else key.encode()
    
    def _create_default_users(self):
        """Create default users from configuration"""
        default_users = self.config.get('default_users', [])
        for user_config in default_users:
            user = User(
                id=user_config['id'],
                username=user_config['username'],
                roles=[UserRole(role) for role in user_config.get('roles', ['viewer'])],
                created_at=datetime.utcnow(),
                enabled=user_config.get('enabled', True)
            )
            self.users[user.id] = user
            
            # Generate API key if requested
            if user_config.get('generate_api_key', False):
                api_key = self.generate_api_key(user.id)
                logger.info(f"Generated API key for user {user.username}: {api_key}")
    
    def authenticate_jwt(self, token: str) -> Optional[AuthContext]:
        """Authenticate using JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            user_id = payload.get('user_id')
            
            if not user_id or user_id not in self.users:
                return None
            
            user = self.users[user_id]
            if not user.enabled:
                return None
            
            expires_at = datetime.fromtimestamp(payload.get('exp', 0))
            if expires_at < datetime.utcnow():
                return None
            
            return AuthContext(
                user=user,
                method=AuthMethod.JWT,
                token=token,
                expires_at=expires_at
            )
            
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
    
    def authenticate_api_key(self, api_key: str) -> Optional[AuthContext]:
        """Authenticate using API key"""
        if api_key not in self.api_keys:
            return None
        
        user_id = self.api_keys[api_key]
        if user_id not in self.users:
            return None
        
        user = self.users[user_id]
        if not user.enabled:
            return None
        
        return AuthContext(
            user=user,
            method=AuthMethod.API_KEY,
            token=api_key
        )
    
    def authenticate_session(self, session_id: str) -> Optional[AuthContext]:
        """Authenticate using session ID"""
        if session_id not in self.sessions:
            return None
        
        context = self.sessions[session_id]
        if context.expires_at and context.expires_at < datetime.utcnow():
            del self.sessions[session_id]
            return None
        
        return context
    
    def create_jwt_token(self, user_id: str) -> Optional[str]:
        """Create JWT token for user"""
        if user_id not in self.users:
            return None
        
        user = self.users[user_id]
        if not user.enabled:
            return None
        
        expires_at = datetime.utcnow() + timedelta(hours=self.jwt_expiry)
        payload = {
            'user_id': user_id,
            'username': user.username,
            'roles': [role.value for role in user.roles],
            'iat': datetime.utcnow().timestamp(),
            'exp': expires_at.timestamp()
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        user.last_login = datetime.utcnow()
        
        logger.info(f"Created JWT token for user {user.username}")
        return token
    
    def generate_api_key(self, user_id: str) -> Optional[str]:
        """Generate API key for user"""
        if user_id not in self.users:
            return None
        
        api_key = secrets.token_urlsafe(self.api_key_length)
        self.api_keys[api_key] = user_id
        self.users[user_id].api_keys.append(api_key)
        
        logger.info(f"Generated API key for user {self.users[user_id].username}")
        return api_key
    
    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke API key"""
        if api_key not in self.api_keys:
            return False
        
        user_id = self.api_keys[api_key]
        del self.api_keys[api_key]
        
        if user_id in self.users and api_key in self.users[user_id].api_keys:
            self.users[user_id].api_keys.remove(api_key)
        
        logger.info(f"Revoked API key for user {user_id}")
        return True
    
    def create_session(self, user_id: str, duration_hours: int = 24) -> Optional[str]:
        """Create session for user"""
        if user_id not in self.users:
            return None
        
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
        
        context = AuthContext(
            user=self.users[user_id],
            method=AuthMethod.SESSION,
            token=session_id,
            expires_at=expires_at
        )
        
        self.sessions[session_id] = context
        logger.info(f"Created session for user {self.users[user_id].username}")
        return session_id
    
    def validate_password(self, user_id: str, password: str) -> bool:
        """Validate user password (implement secure password hashing)"""
        # This is a placeholder - implement secure password verification
        # Use bcrypt, scrypt, or Argon2 in production
        logger.warning("Password validation not implemented - using placeholder")
        return True

class AuthorizationManager:
    """Manages authorization and permissions"""
    
    def __init__(self):
        self.permission_cache: Dict[str, List[str]] = {}
    
    def check_permission(self, auth_context: AuthContext, permission: str) -> bool:
        """Check if user has specific permission"""
        if not auth_context or not auth_context.user.enabled:
            return False
        
        return permission in auth_context.permissions
    
    def check_role(self, auth_context: AuthContext, role: UserRole) -> bool:
        """Check if user has specific role"""
        if not auth_context or not auth_context.user.enabled:
            return False
        
        return role in auth_context.user.roles
    
    def require_permission(self, permission: str):
        """Decorator to require specific permission"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Extract auth context from request
                auth_context = kwargs.get('auth_context')
                if not auth_context or not self.check_permission(auth_context, permission):
                    raise PermissionError(f"Permission '{permission}' required")
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def require_role(self, role: UserRole):
        """Decorator to require specific role"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                auth_context = kwargs.get('auth_context')
                if not auth_context or not self.check_role(auth_context, role):
                    raise PermissionError(f"Role '{role.value}' required")
                return await func(*args, **kwargs)
            return wrapper
        return decorator

class SecurityError(Exception):
    """Base exception for security-related errors"""
    pass

class AuthenticationError(SecurityError):
    """Authentication failed"""
    pass

class AuthorizationError(SecurityError):
    """Authorization failed"""
    pass