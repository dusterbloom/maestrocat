"""
Security Middleware for MaestroCat

Comprehensive middleware framework providing:
- Authentication enforcement for WebSocket and HTTP endpoints
- Authorization checks based on permissions
- Input validation and sanitization
- Rate limiting integration
- Security headers injection
- Request/response logging for audit
"""

import asyncio
import time
import json
from typing import Dict, Any, Optional, Callable, List, Tuple
from dataclasses import dataclass
from fastapi import Request, Response, HTTPException, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import ipaddress
from loguru import logger

from .auth import AuthenticationManager, AuthorizationManager, AuthContext, UserRole
from .validation import InputValidator, ValidationResult
from .rate_limiting import RateLimiter, RequestInfo
from .audit import SecurityAuditLogger

@dataclass
class SecurityConfig:
    """Security middleware configuration"""
    authentication_enabled: bool = True
    authorization_enabled: bool = True
    rate_limiting_enabled: bool = True
    input_validation_enabled: bool = True
    audit_logging_enabled: bool = True
    cors_enabled: bool = True
    security_headers_enabled: bool = True
    
    # Authentication settings
    jwt_header_name: str = "Authorization"
    api_key_header_name: str = "X-API-Key"
    session_cookie_name: str = "maestrocat_session"
    
    # Rate limiting settings
    default_rate_limit: int = 60  # requests per minute
    
    # CORS settings
    allowed_origins: List[str] = None
    allowed_methods: List[str] = None
    allowed_headers: List[str] = None
    
    # Security headers
    security_headers: Dict[str, str] = None
    
    def __post_init__(self):
        if self.allowed_origins is None:
            self.allowed_origins = ["http://localhost:8080", "https://localhost:8080"]
        if self.allowed_methods is None:
            self.allowed_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        if self.allowed_headers is None:
            self.allowed_headers = ["Content-Type", "Authorization", "X-API-Key"]
        if self.security_headers is None:
            self.security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';",
                "Referrer-Policy": "strict-origin-when-cross-origin"
            }

class SecurityMiddleware(BaseHTTPMiddleware):
    """Main security middleware for HTTP requests"""
    
    def __init__(self, app, config: SecurityConfig, 
                 auth_manager: AuthenticationManager,
                 authz_manager: AuthorizationManager,
                 rate_limiter: RateLimiter,
                 input_validator: InputValidator,
                 audit_logger: SecurityAuditLogger):
        super().__init__(app)
        self.config = config
        self.auth_manager = auth_manager
        self.authz_manager = authz_manager
        self.rate_limiter = rate_limiter
        self.input_validator = input_validator
        self.audit_logger = audit_logger
        
        # HTTP Bearer token handler
        self.bearer_scheme = HTTPBearer(auto_error=False)
        
        # Public endpoints that don't require authentication
        self.public_endpoints = {
            "/health", "/metrics", "/docs", "/openapi.json", "/favicon.ico"
        }
        
        # Endpoints requiring specific permissions
        self.protected_endpoints = {
            "/api/config": ["config:read"],
            "/api/config/{component}": ["config:write"],
            "/api/command": ["system:control"],
            "/api/events": ["events:read"],
            "/ws": ["websocket:connect"]
        }
    
    async def dispatch(self, request: Request, call_next):
        """Main middleware dispatch logic"""
        start_time = time.time()
        
        # Create request info for logging and rate limiting
        request_info = await self._create_request_info(request)
        
        try:
            # 1. Rate limiting check
            if self.config.rate_limiting_enabled:
                allowed, reason, retry_after = await self.rate_limiter.check_rate_limit(request_info)
                if not allowed:
                    await self._log_security_event("rate_limit_exceeded", request_info, {"reason": reason})
                    return self._create_error_response(429, f"Rate limit exceeded: {reason}", 
                                                     headers={"Retry-After": str(retry_after)})
            
            # 2. Authentication check
            auth_context = None
            if self.config.authentication_enabled and not self._is_public_endpoint(request.url.path):
                auth_context = await self._authenticate_request(request)
                if not auth_context:
                    await self._log_security_event("authentication_failed", request_info)
                    return self._create_error_response(401, "Authentication required")
            
            # 3. Authorization check
            if self.config.authorization_enabled and auth_context:
                if not await self._authorize_request(request, auth_context):
                    await self._log_security_event("authorization_failed", request_info, 
                                                 {"user_id": auth_context.user.id})
                    return self._create_error_response(403, "Insufficient permissions")
            
            # 4. Input validation
            if self.config.input_validation_enabled:
                validation_result = await self._validate_request(request)
                if not validation_result.is_valid:
                    await self._log_security_event("input_validation_failed", request_info, 
                                                 {"errors": validation_result.errors})
                    return self._create_error_response(400, f"Invalid input: {'; '.join(validation_result.errors)}")
            
            # Store auth context in request state for downstream use
            if auth_context:
                request.state.auth_context = auth_context
            
            # Process request
            response = await call_next(request)
            
            # 5. Add security headers
            if self.config.security_headers_enabled:
                self._add_security_headers(response)
            
            # 6. Audit logging
            if self.config.audit_logging_enabled:
                processing_time = time.time() - start_time
                await self._log_request_response(request_info, response, auth_context, processing_time)
            
            return response
            
        except Exception as e:
            # Log security-related errors
            await self._log_security_event("middleware_error", request_info, 
                                         {"error": str(e), "type": type(e).__name__})
            logger.error(f"Security middleware error: {e}")
            return self._create_error_response(500, "Internal server error")
    
    async def _create_request_info(self, request: Request) -> RequestInfo:
        """Create RequestInfo object from HTTP request"""
        # Get client IP (handle proxy headers)
        client_ip = request.client.host
        if "X-Forwarded-For" in request.headers:
            forwarded_ips = request.headers["X-Forwarded-For"].split(",")
            client_ip = forwarded_ips[0].strip()
        elif "X-Real-IP" in request.headers:
            client_ip = request.headers["X-Real-IP"]
        
        # Get request size
        content_length = int(request.headers.get("Content-Length", "0"))
        
        return RequestInfo(
            ip_address=client_ip,
            user_id=None,  # Will be set after authentication
            endpoint=f"{request.method} {request.url.path}",
            timestamp=time.time(),
            size_bytes=content_length,
            user_agent=request.headers.get("User-Agent")
        )
    
    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public (doesn't require authentication)"""
        return any(path.startswith(public_path) for public_path in self.public_endpoints)
    
    async def _authenticate_request(self, request: Request) -> Optional[AuthContext]:
        """Authenticate HTTP request using various methods"""
        # Try JWT Bearer token
        auth_header = request.headers.get(self.config.jwt_header_name)
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            auth_context = self.auth_manager.authenticate_jwt(token)
            if auth_context:
                return auth_context
        
        # Try API key
        api_key = request.headers.get(self.config.api_key_header_name)
        if api_key:
            auth_context = self.auth_manager.authenticate_api_key(api_key)
            if auth_context:
                return auth_context
        
        # Try session cookie
        session_id = request.cookies.get(self.config.session_cookie_name)
        if session_id:
            auth_context = self.auth_manager.authenticate_session(session_id)
            if auth_context:
                return auth_context
        
        return None
    
    async def _authorize_request(self, request: Request, auth_context: AuthContext) -> bool:
        """Check if user is authorized for the requested endpoint"""
        path = request.url.path
        method = request.method
        
        # Check endpoint-specific permissions
        for endpoint_pattern, required_permissions in self.protected_endpoints.items():
            if self._match_endpoint_pattern(path, endpoint_pattern):
                for permission in required_permissions:
                    if not self.authz_manager.check_permission(auth_context, permission):
                        return False
                return True
        
        # Default: allow if authenticated
        return True
    
    def _match_endpoint_pattern(self, path: str, pattern: str) -> bool:
        """Match endpoint path against pattern (supports simple wildcards)"""
        if "{" in pattern:
            # Simple template matching for patterns like "/api/config/{component}"
            pattern_parts = pattern.split("/")
            path_parts = path.split("/")
            
            if len(pattern_parts) != len(path_parts):
                return False
            
            for pattern_part, path_part in zip(pattern_parts, path_parts):
                if pattern_part.startswith("{") and pattern_part.endswith("}"):
                    continue  # Wildcard match
                elif pattern_part != path_part:
                    return False
            
            return True
        else:
            return path == pattern
    
    async def _validate_request(self, request: Request) -> ValidationResult:
        """Validate request input"""
        errors = []
        warnings = []
        
        # Validate URL parameters
        for param_name, param_value in request.query_params.items():
            if len(param_value) > 1000:  # Basic length check
                errors.append(f"Query parameter '{param_name}' too long")
        
        # Validate request body if present
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Read body without consuming it
                body = await request.body()
                if body:
                    content_type = request.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        try:
                            json_data = json.loads(body)
                            # Validate JSON structure
                            validation_result = self.input_validator.validate_object(
                                json_data, allow_extra_fields=True
                            )
                            if not validation_result.is_valid:
                                errors.extend(validation_result.errors)
                        except json.JSONDecodeError:
                            errors.append("Invalid JSON format")
            except Exception as e:
                logger.warning(f"Could not validate request body: {e}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _add_security_headers(self, response: Response):
        """Add security headers to response"""
        for header_name, header_value in self.config.security_headers.items():
            response.headers[header_name] = header_value
    
    def _create_error_response(self, status_code: int, message: str, 
                             headers: Optional[Dict[str, str]] = None) -> JSONResponse:
        """Create standardized error response"""
        content = {
            "error": {
                "code": status_code,
                "message": message,
                "timestamp": time.time()
            }
        }
        
        response = JSONResponse(content=content, status_code=status_code)
        
        if headers:
            for header_name, header_value in headers.items():
                response.headers[header_name] = header_value
        
        return response
    
    async def _log_security_event(self, event_type: str, request_info: RequestInfo, 
                                 extra_data: Dict[str, Any] = None):
        """Log security-related events"""
        if self.config.audit_logging_enabled:
            await self.audit_logger.log_security_event(
                event_type=event_type,
                ip_address=request_info.ip_address,
                user_id=request_info.user_id,
                endpoint=request_info.endpoint,
                timestamp=request_info.timestamp,
                extra_data=extra_data or {}
            )
    
    async def _log_request_response(self, request_info: RequestInfo, response: Response,
                                  auth_context: Optional[AuthContext], processing_time: float):
        """Log request and response for audit trail"""
        if self.config.audit_logging_enabled:
            await self.audit_logger.log_access(
                ip_address=request_info.ip_address,
                user_id=auth_context.user.id if auth_context else None,
                endpoint=request_info.endpoint,
                method=request_info.endpoint.split()[0],
                status_code=response.status_code,
                processing_time_ms=processing_time * 1000,
                timestamp=request_info.timestamp,
                user_agent=request_info.user_agent
            )

class WebSocketSecurityManager:
    """Security manager for WebSocket connections"""
    
    def __init__(self, config: SecurityConfig,
                 auth_manager: AuthenticationManager,
                 authz_manager: AuthorizationManager,
                 rate_limiter: RateLimiter,
                 input_validator: InputValidator,
                 audit_logger: SecurityAuditLogger):
        self.config = config
        self.auth_manager = auth_manager
        self.authz_manager = authz_manager
        self.rate_limiter = rate_limiter
        self.input_validator = input_validator
        self.audit_logger = audit_logger
        
        # Active WebSocket connections with their auth contexts
        self.active_connections: Dict[str, Tuple[WebSocket, AuthContext]] = {}
    
    async def authenticate_websocket(self, websocket: WebSocket) -> Optional[AuthContext]:
        """Authenticate WebSocket connection"""
        # Check query parameters for token
        query_params = dict(websocket.query_params)
        
        # Try JWT token from query parameter
        token = query_params.get("token")
        if token:
            auth_context = self.auth_manager.authenticate_jwt(token)
            if auth_context:
                return auth_context
        
        # Try API key from query parameter
        api_key = query_params.get("api_key")
        if api_key:
            auth_context = self.auth_manager.authenticate_api_key(api_key)
            if auth_context:
                return auth_context
        
        # Try session from cookie (if available in WebSocket headers)
        cookies = websocket.headers.get("Cookie", "")
        if self.config.session_cookie_name in cookies:
            # Parse cookies to extract session ID
            for cookie in cookies.split(";"):
                name, _, value = cookie.partition("=")
                if name.strip() == self.config.session_cookie_name:
                    auth_context = self.auth_manager.authenticate_session(value.strip())
                    if auth_context:
                        return auth_context
        
        return None
    
    async def authorize_websocket(self, websocket: WebSocket, auth_context: AuthContext) -> bool:
        """Authorize WebSocket connection"""
        # Check WebSocket-specific permissions
        if not self.authz_manager.check_permission(auth_context, "websocket:connect"):
            return False
        
        return True
    
    async def validate_websocket_message(self, message: Dict[str, Any]) -> ValidationResult:
        """Validate WebSocket message"""
        return self.input_validator.validate_websocket_message(message)
    
    async def handle_websocket_connection(self, websocket: WebSocket) -> bool:
        """Handle new WebSocket connection with security checks"""
        client_ip = websocket.client.host
        
        try:
            # 1. Rate limiting check
            request_info = RequestInfo(
                ip_address=client_ip,
                user_id=None,
                endpoint="WebSocket /ws",
                timestamp=time.time()
            )
            
            if self.config.rate_limiting_enabled:
                allowed, reason, _ = await self.rate_limiter.check_rate_limit(request_info)
                if not allowed:
                    await self._log_websocket_event("rate_limit_exceeded", client_ip, None, {"reason": reason})
                    await websocket.close(code=1008, reason=f"Rate limit exceeded: {reason}")
                    return False
            
            # 2. Authentication
            auth_context = None
            if self.config.authentication_enabled:
                auth_context = await self.authenticate_websocket(websocket)
                if not auth_context:
                    await self._log_websocket_event("authentication_failed", client_ip, None)
                    await websocket.close(code=1008, reason="Authentication required")
                    return False
            
            # 3. Authorization
            if self.config.authorization_enabled and auth_context:
                if not await self.authorize_websocket(websocket, auth_context):
                    await self._log_websocket_event("authorization_failed", client_ip, auth_context.user.id)
                    await websocket.close(code=1008, reason="Insufficient permissions")
                    return False
            
            # Accept connection
            await websocket.accept()
            
            # Store connection info
            connection_id = f"{client_ip}_{time.time()}"
            if auth_context:
                self.active_connections[connection_id] = (websocket, auth_context)
            
            # Log successful connection
            await self._log_websocket_event("connection_established", client_ip, 
                                          auth_context.user.id if auth_context else None)
            
            return True
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            await self._log_websocket_event("connection_error", client_ip, None, {"error": str(e)})
            try:
                await websocket.close(code=1011, reason="Server error")
            except:
                pass
            return False
    
    async def handle_websocket_message(self, websocket: WebSocket, message: Dict[str, Any], 
                                     auth_context: Optional[AuthContext]) -> bool:
        """Handle WebSocket message with security validation"""
        client_ip = websocket.client.host
        
        try:
            # 1. Input validation
            if self.config.input_validation_enabled:
                validation_result = await self.validate_websocket_message(message)
                if not validation_result.is_valid:
                    await self._log_websocket_event("message_validation_failed", client_ip,
                                                  auth_context.user.id if auth_context else None,
                                                  {"errors": validation_result.errors})
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Invalid message: {'; '.join(validation_result.errors)}"
                    })
                    return False
            
            # 2. Message-specific authorization
            message_type = message.get("type")
            if message_type == "config_update":
                if not auth_context or not self.authz_manager.check_permission(auth_context, "config:write"):
                    await websocket.send_json({
                        "type": "error", 
                        "message": "Insufficient permissions for config updates"
                    })
                    return False
            
            elif message_type == "command":
                if not auth_context or not self.authz_manager.check_permission(auth_context, "system:control"):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Insufficient permissions for system commands"
                    })
                    return False
            
            # Log message if it's a sensitive operation
            if message_type in ["config_update", "command", "clear_events"]:
                await self._log_websocket_event("sensitive_message", client_ip,
                                              auth_context.user.id if auth_context else None,
                                              {"message_type": message_type})
            
            return True
            
        except Exception as e:
            logger.error(f"WebSocket message handling error: {e}")
            return False
    
    async def _log_websocket_event(self, event_type: str, ip_address: str, 
                                  user_id: Optional[str], extra_data: Dict[str, Any] = None):
        """Log WebSocket security events"""
        if self.config.audit_logging_enabled:
            await self.audit_logger.log_security_event(
                event_type=f"websocket_{event_type}",
                ip_address=ip_address,
                user_id=user_id,
                endpoint="WebSocket /ws",
                timestamp=time.time(),
                extra_data=extra_data or {}
            )

def create_security_middleware(config: Dict[str, Any]) -> Tuple[SecurityMiddleware, WebSocketSecurityManager]:
    """Factory function to create security middleware components"""
    # Parse configuration
    security_config = SecurityConfig(**config.get('middleware', {}))
    
    # Create security components
    auth_manager = AuthenticationManager(config.get('authentication', {}))
    authz_manager = AuthorizationManager()
    rate_limiter = RateLimiter(config.get('rate_limiting', {}))
    input_validator = InputValidator(config.get('input_validation', {}))
    audit_logger = SecurityAuditLogger(config.get('audit_logging', {}))
    
    # Create middleware instances
    http_middleware = SecurityMiddleware(
        app=None,  # Will be set when applied to FastAPI app
        config=security_config,
        auth_manager=auth_manager,
        authz_manager=authz_manager,
        rate_limiter=rate_limiter,
        input_validator=input_validator,
        audit_logger=audit_logger
    )
    
    websocket_manager = WebSocketSecurityManager(
        config=security_config,
        auth_manager=auth_manager,
        authz_manager=authz_manager,
        rate_limiter=rate_limiter,
        input_validator=input_validator,
        audit_logger=audit_logger
    )
    
    return http_middleware, websocket_manager