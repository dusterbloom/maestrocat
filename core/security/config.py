"""
Secure Configuration Management

Comprehensive secure configuration system including:
- Encrypted secrets storage
- Environment variable management
- Configuration validation
- Secure defaults
- Runtime configuration updates
- Audit trail for configuration changes
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import secrets
from loguru import logger

@dataclass
class SecretConfig:
    """Configuration for encrypted secrets"""
    name: str
    value: str
    encrypted: bool = True
    category: str = "general"
    description: str = ""
    required: bool = True

@dataclass
class ConfigValidationRule:
    """Validation rule for configuration values"""
    field_path: str  # e.g., "llm.temperature"
    validator_type: str  # "range", "regex", "enum", "type"
    validator_params: Dict[str, Any]
    error_message: str

class SecureConfigManager:
    """Manages secure configuration with encryption and validation"""
    
    def __init__(self, config_dir: str = "config", secrets_file: str = "secrets.enc"):
        self.config_dir = Path(config_dir)
        self.secrets_file = self.config_dir / secrets_file
        self.config_cache: Dict[str, Any] = {}
        self.secrets_cache: Dict[str, SecretConfig] = {}
        self.validation_rules: List[ConfigValidationRule] = []
        
        # Initialize encryption
        self.encryption_key = self._get_or_create_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        
        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Load validation rules
        self._load_validation_rules()
        
        # Load existing secrets
        self._load_secrets()
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for secrets"""
        # Try to get key from environment
        env_key = os.getenv('MAESTROCAT_ENCRYPTION_KEY')
        if env_key:
            try:
                return base64.urlsafe_b64decode(env_key)
            except Exception as e:
                logger.warning(f"Invalid encryption key in environment: {e}")
        
        # Try to load key from file
        key_file = self.config_dir / ".encryption_key"
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Could not load encryption key from file: {e}")
        
        # Generate new key
        key = Fernet.generate_key()
        
        # Save key to file with restrictive permissions
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Owner read/write only
            logger.info("Generated new encryption key")
        except Exception as e:
            logger.error(f"Could not save encryption key: {e}")
        
        return key
    
    def _load_validation_rules(self):
        """Load configuration validation rules"""
        self.validation_rules = [
            # LLM configuration validation
            ConfigValidationRule(
                field_path="llm.temperature",
                validator_type="range",
                validator_params={"min": 0.0, "max": 2.0},
                error_message="LLM temperature must be between 0.0 and 2.0"
            ),
            ConfigValidationRule(
                field_path="llm.max_tokens",
                validator_type="range",
                validator_params={"min": 1, "max": 8192},
                error_message="LLM max_tokens must be between 1 and 8192"
            ),
            ConfigValidationRule(
                field_path="llm.model",
                validator_type="regex",
                validator_params={"pattern": r"^[a-zA-Z0-9._:-]+$"},
                error_message="LLM model name contains invalid characters"
            ),
            
            # TTS configuration validation
            ConfigValidationRule(
                field_path="tts.speed",
                validator_type="range",
                validator_params={"min": 0.1, "max": 3.0},
                error_message="TTS speed must be between 0.1 and 3.0"
            ),
            ConfigValidationRule(
                field_path="tts.voice",
                validator_type="regex",
                validator_params={"pattern": r"^[a-zA-Z0-9._-]+$"},
                error_message="TTS voice name contains invalid characters"
            ),
            
            # STT configuration validation
            ConfigValidationRule(
                field_path="stt.language",
                validator_type="regex",
                validator_params={"pattern": r"^[a-z]{2}(-[A-Z]{2})?$"},
                error_message="STT language must be in format 'en' or 'en-US'"
            ),
            ConfigValidationRule(
                field_path="stt.port",
                validator_type="range",
                validator_params={"min": 1, "max": 65535},
                error_message="STT port must be between 1 and 65535"
            ),
            
            # Security configuration validation
            ConfigValidationRule(
                field_path="security.jwt_expiry_hours",
                validator_type="range",
                validator_params={"min": 1, "max": 168},  # Max 1 week
                error_message="JWT expiry must be between 1 and 168 hours"
            ),
            ConfigValidationRule(
                field_path="security.api_key_length",
                validator_type="range",
                validator_params={"min": 16, "max": 128},
                error_message="API key length must be between 16 and 128 characters"
            )
        ]
    
    def _load_secrets(self):
        """Load encrypted secrets from file"""
        if not self.secrets_file.exists():
            return
        
        try:
            with open(self.secrets_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.fernet.decrypt(encrypted_data)
            secrets_dict = json.loads(decrypted_data.decode())
            
            for name, secret_data in secrets_dict.items():
                self.secrets_cache[name] = SecretConfig(**secret_data)
            
            logger.info(f"Loaded {len(self.secrets_cache)} secrets")
            
        except Exception as e:
            logger.error(f"Could not load secrets: {e}")
    
    def _save_secrets(self):
        """Save encrypted secrets to file"""
        try:
            secrets_dict = {
                name: asdict(secret) for name, secret in self.secrets_cache.items()
            }
            
            json_data = json.dumps(secrets_dict, indent=2)
            encrypted_data = self.fernet.encrypt(json_data.encode())
            
            with open(self.secrets_file, 'wb') as f:
                f.write(encrypted_data)
            
            os.chmod(self.secrets_file, 0o600)  # Owner read/write only
            logger.debug("Saved encrypted secrets")
            
        except Exception as e:
            logger.error(f"Could not save secrets: {e}")
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file with secret substitution"""
        config_path = self.config_dir / config_file
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    config = yaml.safe_load(f)
                elif config_file.endswith('.json'):
                    config = json.load(f)
                else:
                    raise ValueError(f"Unsupported configuration file format: {config_file}")
            
            # Substitute secrets
            config = self._substitute_secrets(config)
            
            # Validate configuration
            validation_errors = self._validate_config(config)
            if validation_errors:
                logger.error(f"Configuration validation errors: {validation_errors}")
                raise ValueError(f"Configuration validation failed: {validation_errors}")
            
            # Cache configuration
            self.config_cache[config_file] = config
            
            logger.info(f"Loaded configuration from {config_file}")
            return config
            
        except Exception as e:
            logger.error(f"Could not load configuration from {config_file}: {e}")
            raise
    
    def _substitute_secrets(self, config: Any) -> Any:
        """Recursively substitute secret placeholders in configuration"""
        if isinstance(config, dict):
            result = {}
            for key, value in config.items():
                result[key] = self._substitute_secrets(value)
            return result
        elif isinstance(config, list):
            return [self._substitute_secrets(item) for item in config]
        elif isinstance(config, str) and config.startswith('${SECRET:') and config.endswith('}'):
            # Extract secret name
            secret_name = config[9:-1]  # Remove ${SECRET: and }
            return self.get_secret(secret_name)
        else:
            return config
    
    def _validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration against rules"""
        errors = []
        
        for rule in self.validation_rules:
            try:
                value = self._get_nested_value(config, rule.field_path)
                if value is not None:
                    if not self._validate_value(value, rule):
                        errors.append(rule.error_message)
            except KeyError:
                # Field not present in config - might be optional
                pass
        
        return errors
    
    def _get_nested_value(self, config: Dict[str, Any], field_path: str) -> Any:
        """Get nested value from configuration using dot notation"""
        keys = field_path.split('.')
        value = config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                raise KeyError(f"Field path not found: {field_path}")
        
        return value
    
    def _validate_value(self, value: Any, rule: ConfigValidationRule) -> bool:
        """Validate a single value against a validation rule"""
        if rule.validator_type == "range":
            min_val = rule.validator_params.get("min")
            max_val = rule.validator_params.get("max")
            return (min_val is None or value >= min_val) and (max_val is None or value <= max_val)
        
        elif rule.validator_type == "regex":
            import re
            pattern = rule.validator_params["pattern"]
            return bool(re.match(pattern, str(value)))
        
        elif rule.validator_type == "enum":
            allowed_values = rule.validator_params["values"]
            return value in allowed_values
        
        elif rule.validator_type == "type":
            expected_type = rule.validator_params["type"]
            return isinstance(value, expected_type)
        
        return True
    
    def set_secret(self, name: str, value: str, category: str = "general", 
                   description: str = "", required: bool = True):
        """Set an encrypted secret"""
        secret = SecretConfig(
            name=name,
            value=value,
            encrypted=True,
            category=category,
            description=description,
            required=required
        )
        
        self.secrets_cache[name] = secret
        self._save_secrets()
        
        logger.info(f"Set secret: {name} (category: {category})")
    
    def get_secret(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get decrypted secret value"""
        # Try environment variable first
        env_var = f"MAESTROCAT_SECRET_{name.upper()}"
        env_value = os.getenv(env_var)
        if env_value:
            return env_value
        
        # Try secrets cache
        if name in self.secrets_cache:
            return self.secrets_cache[name].value
        
        # Return default or None
        if default is not None:
            return default
        
        # Check if secret is required
        secret = self.secrets_cache.get(name)
        if secret and secret.required:
            logger.error(f"Required secret not found: {name}")
            raise ValueError(f"Required secret not found: {name}")
        
        return None
    
    def delete_secret(self, name: str) -> bool:
        """Delete a secret"""
        if name in self.secrets_cache:
            del self.secrets_cache[name]
            self._save_secrets()
            logger.info(f"Deleted secret: {name}")
            return True
        return False
    
    def list_secrets(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all secrets (without values)"""
        secrets_list = []
        
        for name, secret in self.secrets_cache.items():
            if category is None or secret.category == category:
                secrets_list.append({
                    'name': name,
                    'category': secret.category,
                    'description': secret.description,
                    'required': secret.required,
                    'encrypted': secret.encrypted
                })
        
        return secrets_list
    
    def update_config(self, config_file: str, updates: Dict[str, Any], 
                     validate: bool = True) -> Dict[str, Any]:
        """Update configuration with validation"""
        # Load current config
        current_config = self.load_config(config_file)
        
        # Apply updates
        updated_config = self._deep_merge(current_config, updates)
        
        # Validate if requested
        if validate:
            validation_errors = self._validate_config(updated_config)
            if validation_errors:
                raise ValueError(f"Configuration validation failed: {validation_errors}")
        
        # Save updated configuration
        config_path = self.config_dir / config_file
        try:
            with open(config_path, 'w') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    yaml.safe_dump(updated_config, f, default_flow_style=False)
                elif config_file.endswith('.json'):
                    json.dump(updated_config, f, indent=2)
            
            # Update cache
            self.config_cache[config_file] = updated_config
            
            logger.info(f"Updated configuration file: {config_file}")
            return updated_config
            
        except Exception as e:
            logger.error(f"Could not save updated configuration: {e}")
            raise
    
    def _deep_merge(self, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def get_secure_defaults(self) -> Dict[str, Any]:
        """Get secure default configuration"""
        return {
            'security': {
                'authentication': {
                    'jwt_secret': '${SECRET:JWT_SECRET}',
                    'jwt_algorithm': 'HS256',
                    'jwt_expiry_hours': 24,
                    'api_key_length': 32,
                    'require_https': True,
                    'secure_cookies': True
                },
                'rate_limiting': {
                    'enabled': True,
                    'limits': [
                        {
                            'type': 'requests_per_minute',
                            'max_requests': 60,
                            'window_seconds': 60,
                            'action': 'throttle'
                        },
                        {
                            'type': 'requests_per_hour',
                            'max_requests': 1000,
                            'window_seconds': 3600,
                            'action': 'temporary_ban',
                            'ban_duration_seconds': 300
                        }
                    ]
                },
                'input_validation': {
                    'strict_mode': True,
                    'max_string_length': 10000,
                    'max_array_length': 1000,
                    'max_object_depth': 10,
                    'allow_html': False
                },
                'logging': {
                    'log_level': 'INFO',
                    'audit_enabled': True,
                    'security_events': True,
                    'log_retention_days': 90
                }
            },
            'services': {
                'debug_ui': {
                    'enabled': False,  # Disabled by default in production
                    'host': '127.0.0.1',  # Localhost only
                    'port': 8080,
                    'require_auth': True
                }
            }
        }
    
    def generate_secure_secrets(self) -> Dict[str, str]:
        """Generate secure random secrets for configuration"""
        secrets = {}
        
        # JWT secret
        secrets['JWT_SECRET'] = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode()
        
        # API keys
        secrets['ADMIN_API_KEY'] = secrets.token_urlsafe(32)
        secrets['SERVICE_API_KEY'] = secrets.token_urlsafe(32)
        
        # Database credentials
        secrets['DB_PASSWORD'] = secrets.token_urlsafe(32)
        
        # Encryption keys
        secrets['DATA_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        
        return secrets
    
    def export_config(self, config_name: str, include_secrets: bool = False) -> str:
        """Export configuration as YAML string"""
        config = self.config_cache.get(config_name)
        if not config:
            config = self.load_config(config_name)
        
        if not include_secrets:
            # Replace secret values with placeholders
            config = self._mask_secrets(config)
        
        return yaml.safe_dump(config, default_flow_style=False)
    
    def _mask_secrets(self, config: Any) -> Any:
        """Recursively mask secret values in configuration"""
        if isinstance(config, dict):
            result = {}
            for key, value in config.items():
                if key.lower() in ['password', 'secret', 'key', 'token'] and isinstance(value, str):
                    result[key] = '***MASKED***'
                else:
                    result[key] = self._mask_secrets(value)
            return result
        elif isinstance(config, list):
            return [self._mask_secrets(item) for item in config]
        else:
            return config