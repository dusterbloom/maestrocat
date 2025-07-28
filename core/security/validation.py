"""
Input Validation and Sanitization Framework

Comprehensive validation system for all user inputs including:
- Schema-based validation for JSON payloads
- SQL injection prevention
- XSS prevention
- Command injection prevention
- File path validation
- Audio data validation
"""

import re
import html
import json
import base64
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass
from enum import Enum
import bleach
from pydantic import BaseModel, validator, ValidationError
from loguru import logger

class ValidationSeverity(Enum):
    """Validation error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ValidationResult:
    """Result of validation operation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    sanitized_value: Any = None
    severity: ValidationSeverity = ValidationSeverity.LOW

class SecuritySchema:
    """Security-focused validation schemas for MaestroCat"""
    
    # Common patterns for validation
    PATTERNS = {
        'alphanumeric': re.compile(r'^[a-zA-Z0-9_-]+$'),
        'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
        'uuid': re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
        'jwt': re.compile(r'^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_.+/=]+$'),
        'api_key': re.compile(r'^[A-Za-z0-9_-]{32,128}$'),
        'file_path': re.compile(r'^[a-zA-Z0-9._/-]+$'),
        'model_name': re.compile(r'^[a-zA-Z0-9._:-]+$'),
        'voice_name': re.compile(r'^[a-zA-Z0-9._-]+$'),
        'language_code': re.compile(r'^[a-z]{2}(-[A-Z]{2})?$'),
        'ip_address': re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
    }
    
    # Dangerous patterns to block
    DANGEROUS_PATTERNS = {
        'sql_injection': [
            re.compile(r"(\s*(union|select|insert|update|delete|drop|create|alter|exec|execute|sp_|xp_)\s+)", re.IGNORECASE),
            re.compile(r"(\s*['\";])", re.IGNORECASE),
            re.compile(r"(--|\#|\/\*|\*\/)", re.IGNORECASE)
        ],
        'command_injection': [
            re.compile(r"[;&|`$(){}[\]\\]"),
            re.compile(r"(\.\./|\.\.\\|/etc/|/bin/|/usr/|/var/)", re.IGNORECASE),
            re.compile(r"(rm\s+|del\s+|format\s+|mkfs\s+)", re.IGNORECASE)
        ],
        'xss': [
            re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
            re.compile(r"javascript:", re.IGNORECASE),
            re.compile(r"on\w+\s*=", re.IGNORECASE),
            re.compile(r"<iframe[^>]*>", re.IGNORECASE)
        ]
    }

class InputValidator:
    """Main input validation class"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.strict_mode = self.config.get('strict_mode', True)
        self.allow_html = self.config.get('allow_html', False)
        self.max_string_length = self.config.get('max_string_length', 10000)
        self.max_array_length = self.config.get('max_array_length', 1000)
        self.max_object_depth = self.config.get('max_object_depth', 10)
        
    def validate_string(self, value: Any, pattern: str = None, 
                       min_length: int = 0, max_length: int = None,
                       allow_empty: bool = True) -> ValidationResult:
        """Validate string input with security checks"""
        errors = []
        warnings = []
        severity = ValidationSeverity.LOW
        
        # Type check
        if not isinstance(value, str):
            errors.append(f"Expected string, got {type(value).__name__}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        # Length validation
        max_len = max_length or self.max_string_length
        if len(value) > max_len:
            errors.append(f"String too long: {len(value)} > {max_len}")
            severity = ValidationSeverity.HIGH
        
        if len(value) < min_length:
            errors.append(f"String too short: {len(value)} < {min_length}")
        
        if not allow_empty and not value.strip():
            errors.append("Empty string not allowed")
        
        # Pattern validation
        if pattern and pattern in SecuritySchema.PATTERNS:
            if not SecuritySchema.PATTERNS[pattern].match(value):
                errors.append(f"String does not match required pattern: {pattern}")
                severity = ValidationSeverity.MEDIUM
        
        # Security checks
        security_result = self._check_dangerous_patterns(value)
        if security_result.errors:
            errors.extend(security_result.errors)
            severity = ValidationSeverity.CRITICAL
        
        # Sanitization
        sanitized_value = self._sanitize_string(value) if not errors else None
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=sanitized_value,
            severity=severity
        )
    
    def validate_number(self, value: Any, min_value: float = None, 
                       max_value: float = None, integer_only: bool = False) -> ValidationResult:
        """Validate numeric input"""
        errors = []
        warnings = []
        
        # Type check
        if not isinstance(value, (int, float)):
            try:
                value = float(value) if not integer_only else int(value)
            except (ValueError, TypeError):
                errors.append(f"Invalid number: {value}")
                return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        # Range validation
        if min_value is not None and value < min_value:
            errors.append(f"Number too small: {value} < {min_value}")
        
        if max_value is not None and value > max_value:
            errors.append(f"Number too large: {value} > {max_value}")
        
        # Integer check
        if integer_only and not isinstance(value, int) and not value.is_integer():
            errors.append(f"Expected integer, got float: {value}")
        
        sanitized_value = int(value) if integer_only and isinstance(value, float) and value.is_integer() else value
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=sanitized_value,
            severity=ValidationSeverity.LOW
        )
    
    def validate_array(self, value: Any, element_validator: Callable = None,
                      min_length: int = 0, max_length: int = None) -> ValidationResult:
        """Validate array input"""
        errors = []
        warnings = []
        
        # Type check
        if not isinstance(value, list):
            errors.append(f"Expected array, got {type(value).__name__}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        # Length validation
        max_len = max_length or self.max_array_length
        if len(value) > max_len:
            errors.append(f"Array too long: {len(value)} > {max_len}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        if len(value) < min_length:
            errors.append(f"Array too short: {len(value)} < {min_length}")
        
        # Element validation
        sanitized_elements = []
        if element_validator:
            for i, element in enumerate(value):
                element_result = element_validator(element)
                if not element_result.is_valid:
                    errors.extend([f"Element {i}: {error}" for error in element_result.errors])
                else:
                    sanitized_elements.append(element_result.sanitized_value or element)
        else:
            sanitized_elements = value.copy()
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=sanitized_elements,
            severity=ValidationSeverity.LOW
        )
    
    def validate_object(self, value: Any, schema: Dict[str, Callable] = None,
                       allow_extra_fields: bool = False, depth: int = 0) -> ValidationResult:
        """Validate object input with schema"""
        errors = []
        warnings = []
        
        # Depth check to prevent infinite recursion
        if depth > self.max_object_depth:
            errors.append(f"Object nesting too deep: {depth} > {self.max_object_depth}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        # Type check
        if not isinstance(value, dict):
            errors.append(f"Expected object, got {type(value).__name__}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        sanitized_object = {}
        
        # Schema validation
        if schema:
            # Check required fields
            for field_name, field_validator in schema.items():
                if field_name in value:
                    field_result = field_validator(value[field_name])
                    if not field_result.is_valid:
                        errors.extend([f"Field '{field_name}': {error}" for error in field_result.errors])
                    else:
                        sanitized_object[field_name] = field_result.sanitized_value or value[field_name]
                else:
                    warnings.append(f"Missing field: {field_name}")
            
            # Check for extra fields
            extra_fields = set(value.keys()) - set(schema.keys())
            if extra_fields:
                if allow_extra_fields:
                    for field in extra_fields:
                        sanitized_object[field] = value[field]
                        warnings.append(f"Extra field: {field}")
                else:
                    errors.append(f"Unexpected fields: {list(extra_fields)}")
        else:
            sanitized_object = value.copy()
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=sanitized_object,
            severity=ValidationSeverity.LOW
        )
    
    def validate_websocket_message(self, message: Dict[str, Any]) -> ValidationResult:
        """Validate WebSocket message format"""
        schema = {
            'type': lambda v: self.validate_string(v, pattern='alphanumeric', max_length=50),
            'data': lambda v: self.validate_object(v, allow_extra_fields=True),
            'timestamp': lambda v: self.validate_number(v, min_value=0)
        }
        
        result = self.validate_object(message, schema, allow_extra_fields=False)
        
        # Additional WebSocket-specific validation
        if result.is_valid:
            msg_type = message.get('type')
            if msg_type in ['config_update', 'command', 'get_events']:
                # These message types require additional validation
                if msg_type == 'config_update':
                    component = message.get('component')
                    settings = message.get('settings')
                    if not component or not isinstance(settings, dict):
                        result.errors.append("config_update requires 'component' and 'settings'")
                        result.is_valid = False
        
        return result
    
    def validate_config_update(self, component: str, settings: Dict[str, Any]) -> ValidationResult:
        """Validate configuration update request"""
        errors = []
        warnings = []
        
        # Validate component name
        component_result = self.validate_string(component, pattern='alphanumeric', max_length=50)
        if not component_result.is_valid:
            errors.extend([f"Component: {error}" for error in component_result.errors])
        
        # Validate settings based on component type
        if component == 'llm':
            settings_schema = {
                'temperature': lambda v: self.validate_number(v, min_value=0.0, max_value=2.0),
                'max_tokens': lambda v: self.validate_number(v, min_value=1, max_value=8192, integer_only=True),
                'model': lambda v: self.validate_string(v, pattern='model_name', max_length=100)
            }
        elif component == 'tts':
            settings_schema = {
                'voice': lambda v: self.validate_string(v, pattern='voice_name', max_length=50),
                'speed': lambda v: self.validate_number(v, min_value=0.1, max_value=3.0),
                'volume': lambda v: self.validate_number(v, min_value=0.0, max_value=1.0)
            }
        elif component == 'stt':
            settings_schema = {
                'language': lambda v: self.validate_string(v, pattern='language_code', max_length=10),
                'model': lambda v: self.validate_string(v, pattern='model_name', max_length=100),
                'vad_threshold': lambda v: self.validate_number(v, min_value=0.0, max_value=1.0)
            }
        else:
            # Generic validation for unknown components
            settings_schema = {}
        
        settings_result = self.validate_object(settings, settings_schema, allow_extra_fields=True)
        if not settings_result.is_valid:
            errors.extend([f"Settings: {error}" for error in settings_result.errors])
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value={
                'component': component_result.sanitized_value or component,
                'settings': settings_result.sanitized_value or settings
            },
            severity=ValidationSeverity.MEDIUM
        )
    
    def validate_audio_data(self, audio_data: bytes, max_size: int = None) -> ValidationResult:
        """Validate audio data input"""
        errors = []
        warnings = []
        
        # Type check
        if not isinstance(audio_data, bytes):
            errors.append(f"Expected bytes, got {type(audio_data).__name__}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        # Size check
        max_audio_size = max_size or (10 * 1024 * 1024)  # 10MB default
        if len(audio_data) > max_audio_size:
            errors.append(f"Audio data too large: {len(audio_data)} > {max_audio_size}")
            return ValidationResult(False, errors, warnings, None, ValidationSeverity.HIGH)
        
        if len(audio_data) == 0:
            warnings.append("Empty audio data")
        
        # Basic format validation (check for common audio headers)
        if len(audio_data) >= 4:
            header = audio_data[:4]
            # Check for WAV header
            if header == b'RIFF':
                pass  # Valid WAV
            # Check for other formats as needed
            else:
                warnings.append("Unknown audio format")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=audio_data,
            severity=ValidationSeverity.LOW
        )
    
    def _check_dangerous_patterns(self, value: str) -> ValidationResult:
        """Check for dangerous patterns in string input"""
        errors = []
        severity = ValidationSeverity.LOW
        
        for category, patterns in SecuritySchema.DANGEROUS_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(value):
                    errors.append(f"Potentially dangerous {category} pattern detected")
                    severity = ValidationSeverity.CRITICAL
                    logger.warning(f"Dangerous pattern detected in input: {category}")
                    break
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
            severity=severity
        )
    
    def _sanitize_string(self, value: str) -> str:
        """Sanitize string input"""
        # HTML escape to prevent XSS
        if not self.allow_html:
            value = html.escape(value)
        else:
            # Use bleach for safe HTML
            allowed_tags = ['b', 'i', 'u', 'strong', 'em']
            value = bleach.clean(value, tags=allowed_tags, strip=True)
        
        # Remove null bytes and control characters
        value = ''.join(char for char in value if ord(char) >= 32 or char in '\t\n\r')
        
        # Normalize unicode
        value = value.encode('utf-8', errors='ignore').decode('utf-8')
        
        return value

# Pydantic models for API validation
class ConfigUpdateRequest(BaseModel):
    """Pydantic model for configuration updates"""
    component: str
    settings: Dict[str, Any]
    
    @validator('component')
    def validate_component(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Invalid component name')
        return v
    
    @validator('settings')
    def validate_settings(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Settings must be a dictionary')
        return v

class CommandRequest(BaseModel):
    """Pydantic model for command execution"""
    command: str
    params: Dict[str, Any] = {}
    
    @validator('command')
    def validate_command(cls, v):
        allowed_commands = [
            'restart_service', 'reload_config', 'clear_cache',
            'get_status', 'export_logs', 'run_diagnostics'
        ]
        if v not in allowed_commands:
            raise ValueError(f'Command not allowed: {v}')
        return v

class AuthRequest(BaseModel):
    """Pydantic model for authentication"""
    username: str
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]{3,50}$', v):
            raise ValueError('Invalid username format')
        return v