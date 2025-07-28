#!/usr/bin/env python3
"""
Security Vulnerability Scanner for MaestroCat

Comprehensive security scanning tool that checks for:
- Common security vulnerabilities
- Configuration issues
- Dependency vulnerabilities  
- Container security issues
- Code security patterns
"""

import os
import sys
import json
import subprocess
import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse
from dataclasses import dataclass
from enum import Enum

class SeverityLevel(Enum):
    """Security issue severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityIssue:
    """Represents a security issue found during scanning"""
    title: str
    description: str
    severity: SeverityLevel
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    recommendation: Optional[str] = None
    cwe_id: Optional[str] = None  # Common Weakness Enumeration ID

class SecurityScanner:
    """Main security scanner class"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.issues: List[SecurityIssue] = []
        
        # Security patterns to check
        self.dangerous_patterns = {
            'hardcoded_secrets': [
                (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password detected'),
                (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', 'Hardcoded API key detected'),
                (r'secret[_-]?key\s*=\s*["\'][^"\']+["\']', 'Hardcoded secret key detected'),
                (r'token\s*=\s*["\'][^"\']+["\']', 'Hardcoded token detected'),
            ],
            'sql_injection': [
                (r'execute\s*\(\s*["\'].*%.*["\']', 'Potential SQL injection via string formatting'),
                (r'\.format\s*\([^)]*\)\s*INTO\s+', 'Potential SQL injection via .format()'),
                (r'f["\'].*\{.*\}.*SELECT|INSERT|UPDATE|DELETE', 'Potential SQL injection via f-strings'),
            ],
            'command_injection': [
                (r'subprocess\.(run|call|check_output)\s*\([^)]*shell\s*=\s*True', 'Command injection risk with shell=True'),
                (r'os\.system\s*\(', 'Command injection risk with os.system()'),
                (r'os\.popen\s*\(', 'Command injection risk with os.popen()'),
            ],
            'path_traversal': [
                (r'open\s*\([^)]*\+.*\+', 'Potential path traversal via string concatenation'),
                (r'\.\.\/|\.\.\\', 'Path traversal sequence detected'),
            ],
            'unsafe_deserialization': [
                (r'pickle\.loads?\s*\(', 'Unsafe pickle deserialization'),
                (r'yaml\.load\s*\([^)]*Loader\s*=\s*yaml\.Loader', 'Unsafe YAML loading'),
                (r'eval\s*\(', 'Use of eval() is dangerous'),
                (r'exec\s*\(', 'Use of exec() is dangerous'),
            ],
            'weak_crypto': [
                (r'md5\s*\(', 'MD5 is cryptographically weak'),
                (r'sha1\s*\(', 'SHA1 is cryptographically weak'),
                (r'DES|RC4|ECB', 'Weak cryptographic algorithm'),
            ],
            'debug_info': [
                (r'print\s*\([^)]*password|secret|token', 'Sensitive data in debug output'),
                (r'logger\.(debug|info)\s*\([^)]*password|secret|token', 'Sensitive data in logs'),
            ]
        }
    
    def scan_code_files(self) -> List[SecurityIssue]:
        """Scan Python code files for security issues"""
        print("🔍 Scanning code files for security vulnerabilities...")
        
        python_files = list(self.project_root.rglob("*.py"))
        
        for file_path in python_files:
            # Skip test files and virtual environments
            if any(skip in str(file_path) for skip in ['/test', '/.venv', '/venv', '__pycache__']):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self._scan_file_content(file_path, content)
            except Exception as e:
                print(f"⚠️  Could not scan {file_path}: {e}")
        
        return self.issues
    
    def _scan_file_content(self, file_path: Path, content: str):
        """Scan individual file content for security patterns"""
        lines = content.split('\n')
        
        for category, patterns in self.dangerous_patterns.items():
            for pattern, description in patterns:
                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        severity = self._get_severity_for_category(category)
                        
                        issue = SecurityIssue(
                            title=f"Security Issue: {category.replace('_', ' ').title()}",
                            description=description,
                            severity=severity,
                            file_path=str(file_path.relative_to(self.project_root)),
                            line_number=line_num,
                            recommendation=self._get_recommendation_for_category(category)
                        )
                        self.issues.append(issue)
    
    def _get_severity_for_category(self, category: str) -> SeverityLevel:
        """Get severity level for security category"""
        severity_map = {
            'hardcoded_secrets': SeverityLevel.CRITICAL,
            'sql_injection': SeverityLevel.HIGH,
            'command_injection': SeverityLevel.HIGH,
            'path_traversal': SeverityLevel.HIGH,
            'unsafe_deserialization': SeverityLevel.HIGH,
            'weak_crypto': SeverityLevel.MEDIUM,
            'debug_info': SeverityLevel.MEDIUM
        }
        return severity_map.get(category, SeverityLevel.LOW)
    
    def _get_recommendation_for_category(self, category: str) -> str:
        """Get recommendation for security category"""
        recommendations = {
            'hardcoded_secrets': "Use environment variables or secure secret management systems",
            'sql_injection': "Use parameterized queries or ORM methods",
            'command_injection': "Avoid shell=True, use subprocess with list arguments, validate inputs",
            'path_traversal': "Use os.path.join() and validate file paths",
            'unsafe_deserialization': "Use safe alternatives like json.loads() or yaml.safe_load()",
            'weak_crypto': "Use strong cryptographic algorithms like SHA-256 or bcrypt",
            'debug_info': "Remove sensitive data from debug output and logs"
        }
        return recommendations.get(category, "Review and fix the identified security issue")
    
    def scan_configuration_files(self) -> List[SecurityIssue]:
        """Scan configuration files for security issues"""
        print("🔍 Scanning configuration files...")
        
        config_patterns = ["*.yaml", "*.yml", "*.json", "*.env", "*.conf"]
        
        for pattern in config_patterns:
            for config_file in self.project_root.rglob(pattern):
                if any(skip in str(config_file) for skip in ['/.git', '/.venv', '/venv']):
                    continue
                
                self._scan_config_file(config_file)
        
        return self.issues
    
    def _scan_config_file(self, file_path: Path):
        """Scan individual configuration file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for secrets in config files
            secret_patterns = [
                (r'password\s*[:=]\s*["\']?[^"\'\s]+', 'Password in configuration file'),
                (r'secret\s*[:=]\s*["\']?[^"\'\s]+', 'Secret in configuration file'),
                (r'key\s*[:=]\s*["\']?[^"\'\s]+', 'Key in configuration file'),
                (r'token\s*[:=]\s*["\']?[^"\'\s]+', 'Token in configuration file'),
            ]
            
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                for pattern, description in secret_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Skip if it's a placeholder or environment variable reference
                        if any(placeholder in line for placeholder in ['${', '$ENV', 'placeholder', 'example']):
                            continue
                        
                        issue = SecurityIssue(
                            title="Configuration Security Issue",
                            description=description,
                            severity=SeverityLevel.HIGH,
                            file_path=str(file_path.relative_to(self.project_root)),
                            line_number=line_num,
                            recommendation="Use environment variables or encrypted secret storage"
                        )
                        self.issues.append(issue)
        
        except Exception as e:
            print(f"⚠️  Could not scan config file {file_path}: {e}")
    
    def scan_docker_files(self) -> List[SecurityIssue]:
        """Scan Docker files for security issues"""
        print("🔍 Scanning Docker files...")
        
        docker_files = list(self.project_root.rglob("Dockerfile*")) + list(self.project_root.rglob("docker-compose*.yml"))
        
        for docker_file in docker_files:
            self._scan_docker_file(docker_file)
        
        return self.issues
    
    def _scan_docker_file(self, file_path: Path):
        """Scan individual Docker file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            # Docker security checks
            security_checks = [
                (r'FROM\s+.*:latest', 'Using :latest tag is not secure', SeverityLevel.MEDIUM),
                (r'USER\s+root|^root', 'Running as root user', SeverityLevel.HIGH),
                (r'--privileged', 'Privileged container detected', SeverityLevel.CRITICAL),
                (r'ADD\s+http', 'Using ADD with URL, prefer COPY', SeverityLevel.LOW),
                (r'chmod\s+777', 'Overly permissive file permissions', SeverityLevel.HIGH),
                (r'password\s*[:=]', 'Password in Docker file', SeverityLevel.HIGH),
            ]
            
            for line_num, line in enumerate(lines, 1):
                for pattern, description, severity in security_checks:
                    if re.search(pattern, line, re.IGNORECASE):
                        issue = SecurityIssue(
                            title="Docker Security Issue",
                            description=description,
                            severity=severity,
                            file_path=str(file_path.relative_to(self.project_root)),
                            line_number=line_num,
                            recommendation=self._get_docker_recommendation(pattern)
                        )
                        self.issues.append(issue)
        
        except Exception as e:
            print(f"⚠️  Could not scan Docker file {file_path}: {e}")
    
    def _get_docker_recommendation(self, pattern: str) -> str:
        """Get recommendation for Docker security issues"""
        recommendations = {
            r'FROM\s+.*:latest': "Use specific version tags instead of :latest",
            r'USER\s+root': "Create and use a non-root user",
            r'--privileged': "Avoid privileged containers, use specific capabilities instead", 
            r'ADD\s+http': "Use COPY for local files, wget/curl for remote files",
            r'chmod\s+777': "Use more restrictive permissions",
            r'password': "Use Docker secrets or environment variables"
        }
        
        for pat, rec in recommendations.items():
            if re.search(pat, pattern):
                return rec
        
        return "Review and fix the Docker security issue"
    
    def scan_dependencies(self) -> List[SecurityIssue]:
        """Scan dependencies for known vulnerabilities"""
        print("🔍 Scanning dependencies for vulnerabilities...")
        
        # Check if safety is installed
        try:
            result = subprocess.run(['safety', '--version'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print("⚠️  'safety' tool not found. Install with: pip install safety")
                return self.issues
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("⚠️  'safety' tool not available, skipping dependency scan")
            return self.issues
        
        # Run safety check
        try:
            result = subprocess.run(
                ['safety', 'check', '--json', '--full-report'],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root
            )
            
            if result.stdout:
                try:
                    safety_report = json.loads(result.stdout)
                    vulnerabilities = safety_report.get('vulnerabilities', [])
                    
                    for vuln in vulnerabilities:
                        issue = SecurityIssue(
                            title=f"Vulnerable Dependency: {vuln.get('package_name', 'Unknown')}",
                            description=f"CVE: {vuln.get('vulnerability_id', 'N/A')} - {vuln.get('advisory', 'No description')}",
                            severity=self._map_safety_severity(vuln.get('severity', 'medium')),
                            recommendation=f"Upgrade to version {vuln.get('analyzed_version', 'latest')} or higher",
                            cwe_id=vuln.get('cwe')
                        )
                        self.issues.append(issue)
                        
                except json.JSONDecodeError:
                    print("⚠️  Could not parse safety report")
            
            elif result.stderr:
                print(f"⚠️  Safety check error: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("⚠️  Dependency scan timed out")
        except Exception as e:
            print(f"⚠️  Error running dependency scan: {e}")
        
        return self.issues
    
    def _map_safety_severity(self, safety_severity: str) -> SeverityLevel:
        """Map safety severity to our severity levels"""
        mapping = {
            'low': SeverityLevel.LOW,
            'medium': SeverityLevel.MEDIUM,
            'high': SeverityLevel.HIGH,
            'critical': SeverityLevel.CRITICAL
        }
        return mapping.get(safety_severity.lower(), SeverityLevel.MEDIUM)
    
    def check_security_headers(self) -> List[SecurityIssue]:
        """Check for security headers configuration"""
        print("🔍 Checking security headers configuration...")
        
        # Look for FastAPI or Flask applications
        app_files = list(self.project_root.rglob("*.py"))
        
        for app_file in app_files:
            try:
                with open(app_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check if it's a web application
                if any(framework in content for framework in ['FastAPI', 'Flask', 'Starlette']):
                    # Check for security headers
                    security_headers = [
                        'X-Content-Type-Options',
                        'X-Frame-Options', 
                        'X-XSS-Protection',
                        'Strict-Transport-Security',
                        'Content-Security-Policy'
                    ]
                    
                    missing_headers = []
                    for header in security_headers:
                        if header not in content:
                            missing_headers.append(header)
                    
                    if missing_headers:
                        issue = SecurityIssue(
                            title="Missing Security Headers",
                            description=f"Missing security headers: {', '.join(missing_headers)}",
                            severity=SeverityLevel.MEDIUM,
                            file_path=str(app_file.relative_to(self.project_root)),
                            recommendation="Add security headers to protect against common attacks"
                        )
                        self.issues.append(issue)
            
            except Exception as e:
                print(f"⚠️  Could not check {app_file}: {e}")
        
        return self.issues
    
    def generate_report(self, output_format: str = 'console') -> str:
        """Generate security report"""
        if not self.issues:
            return "✅ No security issues found!"
        
        # Sort issues by severity
        severity_order = {
            SeverityLevel.CRITICAL: 0,
            SeverityLevel.HIGH: 1,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.LOW: 3
        }
        
        sorted_issues = sorted(self.issues, key=lambda x: severity_order[x.severity])
        
        if output_format == 'json':
            return self._generate_json_report(sorted_issues)
        elif output_format == 'html':
            return self._generate_html_report(sorted_issues)
        else:
            return self._generate_console_report(sorted_issues)
    
    def _generate_console_report(self, issues: List[SecurityIssue]) -> str:
        """Generate console report"""
        report = []
        report.append("🔒 MAESTROCAT SECURITY SCAN REPORT")
        report.append("=" * 50)
        report.append("")
        
        # Summary
        severity_counts = {}
        for issue in issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        
        report.append("📊 SUMMARY:")
        for severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH, SeverityLevel.MEDIUM, SeverityLevel.LOW]:
            count = severity_counts.get(severity, 0)
            if count > 0:
                emoji = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️"}[severity.value]
                report.append(f"  {emoji} {severity.value.upper()}: {count}")
        
        report.append("")
        report.append("🔍 DETAILED FINDINGS:")
        report.append("-" * 30)
        
        # Detailed issues
        for i, issue in enumerate(issues, 1):
            emoji = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️"}[issue.severity.value]
            
            report.append(f"\n{i}. {emoji} {issue.title}")
            report.append(f"   Severity: {issue.severity.value.upper()}")
            report.append(f"   Description: {issue.description}")
            
            if issue.file_path:
                location = issue.file_path
                if issue.line_number:
                    location += f":{issue.line_number}"
                report.append(f"   Location: {location}")
            
            if issue.recommendation:
                report.append(f"   Recommendation: {issue.recommendation}")
            
            if issue.cwe_id:
                report.append(f"   CWE ID: {issue.cwe_id}")
        
        return "\n".join(report)
    
    def _generate_json_report(self, issues: List[SecurityIssue]) -> str:
        """Generate JSON report"""
        report_data = {
            "scan_timestamp": "2024-01-01T00:00:00Z",  # Would use actual timestamp
            "total_issues": len(issues),
            "severity_counts": {},
            "issues": []
        }
        
        # Count by severity
        for issue in issues:
            severity = issue.severity.value
            report_data["severity_counts"][severity] = report_data["severity_counts"].get(severity, 0) + 1
        
        # Add issues
        for issue in issues:
            issue_data = {
                "title": issue.title,
                "description": issue.description,
                "severity": issue.severity.value,
                "file_path": issue.file_path,
                "line_number": issue.line_number,
                "recommendation": issue.recommendation,
                "cwe_id": issue.cwe_id
            }
            report_data["issues"].append(issue_data)
        
        return json.dumps(report_data, indent=2)
    
    def _generate_html_report(self, issues: List[SecurityIssue]) -> str:
        """Generate HTML report"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MaestroCat Security Scan Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .critical {{ color: #d32f2f; }}
                .high {{ color: #f57c00; }}
                .medium {{ color: #fbc02d; }}
                .low {{ color: #388e3c; }}
                .issue {{ margin: 20px 0; padding: 15px; border-left: 4px solid #ccc; }}
                .summary {{ background: #f5f5f5; padding: 15px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h1>🔒 MaestroCat Security Scan Report</h1>
            
            <div class="summary">
                <h2>Summary</h2>
                <p>Total Issues: {len(issues)}</p>
            </div>
            
            <h2>Issues</h2>
        """
        
        for i, issue in enumerate(issues, 1):
            severity_class = issue.severity.value
            html += f"""
            <div class="issue">
                <h3 class="{severity_class}">{i}. {issue.title}</h3>
                <p><strong>Severity:</strong> <span class="{severity_class}">{issue.severity.value.upper()}</span></p>
                <p><strong>Description:</strong> {issue.description}</p>
            """
            
            if issue.file_path:
                location = issue.file_path
                if issue.line_number:
                    location += f":{issue.line_number}"
                html += f"<p><strong>Location:</strong> {location}</p>"
            
            if issue.recommendation:
                html += f"<p><strong>Recommendation:</strong> {issue.recommendation}</p>"
            
            html += "</div>"
        
        html += """
        </body>
        </html>
        """
        
        return html


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="MaestroCat Security Vulnerability Scanner")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--output-format", choices=['console', 'json', 'html'], default='console',
                       help="Output format")
    parser.add_argument("--output-file", help="Output file path")
    parser.add_argument("--skip-deps", action='store_true', help="Skip dependency scanning")
    
    args = parser.parse_args()
    
    scanner = SecurityScanner(args.project_root)
    
    print("🔒 Starting MaestroCat Security Scan...")
    print(f"📁 Project root: {os.path.abspath(args.project_root)}")
    print()
    
    # Run scans
    scanner.scan_code_files()
    scanner.scan_configuration_files()
    scanner.scan_docker_files()
    scanner.check_security_headers()
    
    if not args.skip_deps:
        scanner.scan_dependencies()
    
    # Generate report
    report = scanner.generate_report(args.output_format)
    
    if args.output_file:
        with open(args.output_file, 'w') as f:
            f.write(report)
        print(f"📄 Report saved to: {args.output_file}")
    else:
        print(report)
    
    # Exit with non-zero code if critical/high issues found
    critical_high_issues = [i for i in scanner.issues 
                           if i.severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH]]
    
    if critical_high_issues:
        print(f"\n❌ Found {len(critical_high_issues)} critical/high severity issues!")
        sys.exit(1)
    else:
        print("\n✅ No critical or high severity issues found!")
        sys.exit(0)


if __name__ == "__main__":
    main()