# MaestroCat Security Framework

## Overview

This document describes the comprehensive security framework implemented for MaestroCat, a voice agent system. The framework addresses critical security vulnerabilities identified during the security audit and implements industry best practices for voice AI systems.

## Security Architecture

### 1. Authentication & Authorization (`core/security/auth.py`)

#### Features
- **Multi-method Authentication**: JWT tokens, API keys, and session-based authentication
- **Role-Based Access Control (RBAC)**: Admin, Operator, Viewer, and Service roles
- **Secure Token Management**: Encrypted secrets storage with automatic key generation
- **Session Management**: Configurable session timeouts and secure session handling

#### Usage
```python
from core.security.auth import AuthenticationManager, AuthorizationManager

# Initialize authentication
auth_manager = AuthenticationManager(config['authentication'])
authz_manager = AuthorizationManager()

# Create JWT token
token = auth_manager.create_jwt_token('user_id')

# Authenticate request
auth_context = auth_manager.authenticate_jwt(token)

# Check permissions
if authz_manager.check_permission(auth_context, 'config:write'):
    # Allow operation
    pass
```

#### Security Controls
- JWT tokens with configurable expiration (default: 8 hours in production)
- API key length: 32+ characters with cryptographically secure generation
- Encrypted secrets storage using Fernet encryption
- Protection against timing attacks in authentication logic

### 2. Input Validation & Sanitization (`core/security/validation.py`)

#### Features
- **Schema-based Validation**: Structured validation for JSON payloads
- **Injection Prevention**: SQL, XSS, and command injection detection
- **File Path Validation**: Path traversal attack prevention
- **Audio Data Validation**: Secure handling of audio inputs
- **Size Limits**: Configurable limits for strings, arrays, and objects

#### Security Patterns Detected
- SQL injection patterns: `UNION`, `SELECT`, string concatenation
- XSS patterns: `<script>`, `javascript:`, event handlers
- Command injection: Shell metacharacters, path traversal sequences
- Path traversal: `../`, absolute paths, Windows path separators

#### Usage
```python
from core.security.validation import InputValidator

validator = InputValidator({'strict_mode': True})

# Validate WebSocket message
result = validator.validate_websocket_message(message)
if not result.is_valid:
    return {"error": result.errors}

# Validate configuration update
result = validator.validate_config_update(component, settings)
```

### 3. Rate Limiting & DDoS Protection (`core/security/rate_limiting.py`)

#### Features
- **Multi-tier Rate Limiting**: Per-minute, per-hour, and per-second limits
- **DDoS Detection**: Pattern-based attack detection from multiple IPs
- **Adaptive Throttling**: Automatic response to system load
- **IP Whitelisting**: Bypass rate limits for trusted IPs
- **Temporary Bans**: Automatic banning for repeated violations

#### Rate Limiting Policies
```yaml
rate_limiting:
  limits:
    - type: "requests_per_minute"
      max_requests: 30
      window_seconds: 60
      action: "throttle"
    - type: "requests_per_hour" 
      max_requests: 500
      window_seconds: 3600
      action: "temporary_ban"
      ban_duration_seconds: 300
```

#### DDoS Protection Thresholds
- Single IP: 50 requests/second
- Distributed attack: 500+ unique IPs in 5 minutes
- Connection flooding: 30+ connections/minute per IP

### 4. Secure Configuration Management (`core/security/config.py`)

#### Features
- **Encrypted Secrets**: Fernet encryption for sensitive configuration data
- **Environment Variable Support**: Secure injection of secrets at runtime
- **Configuration Validation**: Schema-based validation with security rules
- **Audit Trail**: Logging of configuration changes
- **Secure Defaults**: Production-ready security settings

#### Secret Management
```python
from core.security.config import SecureConfigManager

config_manager = SecureConfigManager()

# Set encrypted secret
config_manager.set_secret('jwt_secret', 'secure_random_key', 'authentication')

# Load configuration with secret substitution
config = config_manager.load_config('maestrocat.secure.yaml')

# Secrets are automatically decrypted: ${SECRET:JWT_SECRET}
```

#### Configuration Validation Rules
- LLM temperature: 0.0-2.0
- JWT expiry: 1-168 hours
- API key length: 16-128 characters
- Port numbers: 1-65535
- String patterns: Alphanumeric validation for model names, voices, etc.

### 5. Security Middleware (`core/security/middleware.py`)

#### HTTP Middleware Features
- **Authentication Enforcement**: Automatic token validation
- **Authorization Checks**: Permission-based endpoint protection
- **Rate Limiting Integration**: Request throttling and blocking
- **Security Headers**: Comprehensive security header injection
- **Input Validation**: Automatic request validation
- **Audit Logging**: Security event logging

#### WebSocket Security Manager
- **Connection Authentication**: Token-based WebSocket authentication
- **Message Validation**: Real-time message security checking
- **Connection Limits**: Maximum concurrent connection enforcement
- **Session Management**: WebSocket session tracking and timeout

#### Security Headers Applied
```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; ...
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=(), ...
```

### 6. Audit Logging & Monitoring (`core/security/audit.py`)

#### Features
- **Structured Logging**: JSON-formatted security events
- **Real-time Monitoring**: Threat pattern detection
- **Event Categories**: Authentication, authorization, access, attacks
- **Threat Detection**: Brute force, SQL injection, privilege escalation
- **Alert Thresholds**: Configurable alerting for security events
- **Log Retention**: Automatic cleanup with configurable retention

#### Security Events Logged
- Authentication attempts (success/failure)
- Authorization failures
- Rate limit violations
- Input validation failures
- Configuration changes
- WebSocket connections/disconnections
- Threat pattern detections

#### Threat Detection Patterns
```python
# Automatically detects:
# - Brute force attacks (10+ auth failures from single IP in 5 minutes)
# - SQL injection attempts (validation failures with SQL keywords)
# - Distributed attacks (50+ unique IPs with errors in 1 minute)
# - Privilege escalation (5+ authz failures from single user in 5 minutes)
```

## Container Security Hardening

### Docker Security Configuration (`docker-compose.secure.yml`)

#### Security Measures
- **Non-root Users**: All containers run as non-root (UIDs 1001-1005)
- **Read-only Filesystems**: Containers use read-only root filesystems
- **Capability Dropping**: Remove all Linux capabilities, add only necessary ones
- **No New Privileges**: Prevent privilege escalation
- **Resource Limits**: CPU and memory limits for all containers
- **Network Isolation**: Private Docker network with restricted communication
- **Security Options**: AppArmor profiles and seccomp filters

#### Container Hardening Example
```yaml
whisperlive:
  user: "1001:1001"
  read_only: true
  cap_drop: [ALL]
  cap_add: [NET_BIND_SERVICE]
  security_opt:
    - no-new-privileges:true
    - seccomp:unconfined
  deploy:
    resources:
      limits: {cpus: '2.0', memory: 2G}
```

### Secure Dockerfile (`docker/maestrocat/Dockerfile.secure`)

#### Security Features
- **Multi-stage Build**: Separate build and runtime stages
- **Minimal Base Image**: Use slim Python image
- **Non-root User**: Create and use specific UID/GID
- **File Permissions**: Proper file ownership and permissions
- **Security Labels**: Container metadata for security scanning
- **Health Checks**: Built-in container health monitoring

## Production Security Configuration

### Secure Configuration File (`config/maestrocat.secure.yaml`)

#### Key Security Settings
```yaml
security:
  authentication:
    jwt_expiry_hours: 8  # Shorter expiry
    require_https: true
    secure_cookies: true
    
  rate_limiting:
    enabled: true
    limits:
      - type: "requests_per_minute"
        max_requests: 30  # Conservative limit
        
  input_validation:
    strict_mode: true
    max_string_length: 8192  # Reduced
    allow_html: false
    
  audit_logging:
    enabled: true
    log_retention_days: 30
    monitoring_enabled: true
```

#### Service Binding
- All services bind to `127.0.0.1` (localhost only)
- No external network exposure without reverse proxy
- Redis password protection enabled
- TLS termination handled by reverse proxy

## Security Testing Suite

### Test Coverage (`tests/security/`)

#### Authentication Tests
- JWT token validation and expiration
- API key generation and revocation
- Session management and timeout
- Brute force protection
- Timing attack resistance

#### Rate Limiting Tests
- Request rate enforcement
- DDoS attack simulation
- Whitelist functionality
- Concurrent request handling
- Memory cleanup verification

#### Input Validation Tests
- SQL injection detection
- XSS prevention
- Command injection blocking
- Path traversal protection
- Oversized input rejection

### Security Scanner (`scripts/security-scan.py`)

#### Vulnerability Detection
- **Code Analysis**: Pattern-based security vulnerability scanning
- **Configuration Audit**: Security misconfigurations in YAML/JSON files
- **Docker Security**: Container security best practices validation
- **Dependency Scanning**: Known vulnerability detection using `safety`
- **Security Headers**: Web application security header verification

#### Usage
```bash
# Run comprehensive security scan
python scripts/security-scan.py --project-root . --output-format console

# Generate JSON report
python scripts/security-scan.py --output-format json --output-file security-report.json

# Skip dependency scanning
python scripts/security-scan.py --skip-deps
```

## Deployment Security Checklist

### Pre-deployment
- [ ] Run security scanner and fix critical/high issues
- [ ] Update all dependencies to latest secure versions
- [ ] Generate unique secrets for production (JWT secret, API keys)
- [ ] Configure proper SSL/TLS termination
- [ ] Set up monitoring and alerting

### Infrastructure
- [ ] Use hardened Docker configuration (`docker-compose.secure.yml`)
- [ ] Deploy behind reverse proxy (nginx/Traefik) with SSL
- [ ] Configure firewall rules (block direct container access)
- [ ] Set up log aggregation and monitoring
- [ ] Enable automated security updates

### Monitoring
- [ ] Configure security event alerting
- [ ] Set up rate limiting dashboards
- [ ] Monitor authentication failure rates
- [ ] Track resource usage and anomalies
- [ ] Regular security scan automation

## Security Incident Response

### Incident Types
1. **Authentication Bypass**: Immediate token revocation and audit
2. **Rate Limiting Bypass**: IP blocking and threshold adjustment
3. **Injection Attack**: Input validation enhancement and patching
4. **DDoS Attack**: Automatic mitigation activation and upstream filtering
5. **Data Breach**: Immediate system isolation and forensic analysis

### Response Procedures
1. **Detection**: Automated alerts via audit logging system
2. **Containment**: Automatic rate limiting and temporary bans
3. **Investigation**: Log analysis and threat pattern identification
4. **Mitigation**: Security policy updates and system hardening
5. **Recovery**: Secure system restoration and monitoring enhancement

## Compliance and Standards

### Security Standards Adherence
- **OWASP Top 10**: Protection against common web vulnerabilities
- **CWE/SANS Top 25**: Common weakness enumeration coverage
- **NIST Cybersecurity Framework**: Identify, Protect, Detect, Respond, Recover
- **Docker Security Best Practices**: Container hardening and isolation
- **API Security Best Practices**: Authentication, authorization, rate limiting

### Privacy Protection
- **Data Minimization**: No persistent storage of voice data
- **Anonymization**: User data anonymization in logs
- **Retention Limits**: Configurable data retention periods
- **GDPR Compliance**: Data protection and user rights support

## Maintenance and Updates

### Regular Security Tasks
- **Weekly**: Dependency vulnerability scans
- **Monthly**: Security configuration reviews  
- **Quarterly**: Penetration testing and security audits
- **Annually**: Security framework architecture review

### Automated Security
- **CI/CD Integration**: Security scanner in deployment pipeline
- **Dependency Updates**: Automated security patch deployment
- **Log Monitoring**: Real-time threat detection and alerting
- **Backup Verification**: Regular backup integrity and recovery testing

---

## Quick Start Security Setup

1. **Install Dependencies**
   ```bash
   pip install "maestrocat[security]"
   pip install safety  # For dependency scanning
   ```

2. **Generate Secrets**
   ```bash
   python -c "from core.security.config import SecureConfigManager; print(SecureConfigManager().generate_secure_secrets())"
   ```

3. **Run Security Scan**
   ```bash
   python scripts/security-scan.py
   ```

4. **Deploy with Security**
   ```bash
   docker-compose -f docker-compose.secure.yml up -d
   ```

5. **Monitor Security Events**
   ```bash
   tail -f logs/security/security_$(date +%Y%m%d).log
   ```

This security framework provides comprehensive protection for MaestroCat voice agent deployments, addressing authentication, authorization, input validation, rate limiting, container security, and monitoring requirements for production environments.