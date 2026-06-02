"""
DeepScan & Repair Tool - Perfektioniertes Bot-Optimierungs-System
Automatisches Fehlererkennung, Reparatur und kontinuierliche Verbesserung
"""

import os
import json
import logging
import asyncio
import time
import traceback
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import subprocess
import re

try:
    from cloud_backup_manager import CloudBackupManager, integrate_cloud_backup
except ImportError:
    CloudBackupManager = None
    integrate_cloud_backup = None

logger = logging.getLogger(__name__)

class DeepScanRepairTool:
    """Ultramodernes DeepScan & Repair System"""
    
    def __init__(self, bot_name: str = "SuperMegaBot"):
        self.bot_name = bot_name
        self.base_dir = Path(__file__).parent.parent
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.error_db = self.data_dir / "error_patterns.json"
        self.repair_history = self.data_dir / "repair_history.json"
        self.improvement_log = self.data_dir / "improvements.json"
        self.scan_results = self.data_dir / "scan_results.json"
        
        # Initialize data structures
        self._initialize_data_structures()
        
        # Error pattern database
        self.error_patterns = self._load_error_patterns()
        
        # Repair history tracking
        self.repair_history_data = self._load_repair_history()
        
        # Improvement tracking
        self.improvements = self._load_improvements()
        
        # Scan metrics
        self.scan_metrics = {
            "total_scans": 0,
            "errors_found": 0,
            "errors_fixed": 0,
            "improvements_made": 0,
            "last_scan": None,
            "scan_duration": []
        }
        
        # Cloud Backup Manager
        self.backup_manager = None
        if CloudBackupManager:
            self.backup_manager = CloudBackupManager(str(self.base_dir))
    
    def _initialize_data_structures(self):
        """Initialize all data directories and files"""
        for dir_path in [self.data_dir, self.logs_dir]:
            dir_path.mkdir(exist_ok=True)
        
        # Initialize JSON files with structure
        initial_files = {
            self.error_db: {"patterns": {}, "last_updated": None},
            self.repair_history: {"repairs": [], "successful_fixes": 0},
            self.improvement_log: {"improvements": [], "version": "1.0"},
            self.scan_results: {"scans": [], "latest": {}}
        }
        
        for file_path, initial_data in initial_files.items():
            if not file_path.exists():
                with open(file_path, 'w') as f:
                    json.dump(initial_data, f, indent=2)
    
    def _load_error_patterns(self) -> Dict:
        """Load error patterns database"""
        try:
            with open(self.error_db, 'r') as f:
                data = json.load(f)
                return data.get("patterns", {})
        except Exception as e:
            logger.error(f"Error loading patterns: {e}")
            return {}
    
    def _load_repair_history(self) -> Dict:
        """Load repair history"""
        try:
            with open(self.repair_history, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading repair history: {e}")
            return {"repairs": [], "successful_fixes": 0}
    
    def _load_improvements(self) -> Dict:
        """Load improvement log"""
        try:
            with open(self.improvement_log, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading improvements: {e}")
            return {"improvements": [], "version": "1.0"}
    
    async def perform_deep_scan(self) -> Dict:
        """Führt einen tiefen Scan durch und erkennt alle möglichen Fehler"""
        start_time = time.time()
        scan_id = hashlib.md5(f"{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        
        logger.info(f"🔍 Starting DeepScan #{scan_id} for {self.bot_name}")
        
        scan_results = {
            "scan_id": scan_id,
            "timestamp": datetime.now().isoformat(),
            "issues_found": [],
            "performance_issues": [],
            "security_issues": [],
            "code_quality_issues": [],
            "button_test_results": [],
            "functionality_tests": [],
            "recommendations": []
        }
        
        try:
            # 1. Code Quality Analysis
            code_issues = await self._analyze_code_quality()
            scan_results["code_quality_issues"] = code_issues
            
            # 2. Performance Analysis
            perf_issues = await self._analyze_performance()
            scan_results["performance_issues"] = perf_issues
            
            # 3. Security Analysis
            security_issues = await self._analyze_security()
            scan_results["security_issues"] = security_issues
            
            # 4. Button Testing
            button_results = await self._test_buttons()
            scan_results["button_test_results"] = button_results
            
            # 5. Functionality Testing
            func_results = await self._test_functionality()
            scan_results["functionality_tests"] = func_results
            
            # 6. Configuration Analysis
            config_issues = await self._analyze_configuration()
            scan_results["config_issues"] = config_issues
            
            # 7. Dependency Analysis
            dep_issues = await self._analyze_dependencies()
            scan_results["dependency_issues"] = dep_issues
            
            # 8. Resource Analysis
            resource_issues = await self._analyze_resources()
            scan_results["resource_issues"] = resource_issues
            
            # Aggregate all issues
            all_issues = []
            for category in ["code_quality_issues", "performance_issues", "security_issues", 
                           "config_issues", "dependency_issues", "resource_issues"]:
                all_issues.extend(scan_results.get(category, []))
            
            scan_results["issues_found"] = all_issues
            scan_results["total_issues"] = len(all_issues)
            
            # Generate recommendations
            scan_results["recommendations"] = await self._generate_recommendations(scan_results)
            
            # Update metrics
            scan_duration = time.time() - start_time
            self.scan_metrics["total_scans"] += 1
            self.scan_metrics["errors_found"] += len(all_issues)
            self.scan_metrics["last_scan"] = datetime.now().isoformat()
            self.scan_metrics["scan_duration"].append(scan_duration)
            
            # Save scan results
            await self._save_scan_results(scan_results)
            
            logger.info(f"✅ DeepScan #{scan_id} completed: {len(all_issues)} issues found in {scan_duration:.2f}s")
            
            return scan_results
            
        except Exception as e:
            logger.error(f"❌ DeepScan #{scan_id} failed: {e}")
            scan_results["error"] = str(e)
            return scan_results
    
    async def _analyze_code_quality(self) -> List[Dict]:
        """Analyse Code-Qualität und findet Code-Muster"""
        issues = []
        
        # Scan Python files
        python_files = list(self.base_dir.rglob("*.py"))
        for py_file in python_files[:20]:  # Limit to prevent too long scans
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for common code issues
                issues.extend(self._check_python_issues(content, str(py_file)))
                
            except Exception as e:
                issues.append({
                    "type": "code_quality",
                    "severity": "medium",
                    "file": str(py_file),
                    "issue": f"File read error: {e}",
                    "description": "Could not read file for analysis"
                })
        
        # Scan JavaScript files
        js_files = list(self.base_dir.rglob("*.js"))
        for js_file in js_files[:20]:
            try:
                with open(js_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                issues.extend(self._check_javascript_issues(content, str(js_file)))
                
            except Exception as e:
                issues.append({
                    "type": "code_quality",
                    "severity": "medium",
                    "file": str(js_file),
                    "issue": f"File read error: {e}",
                    "description": "Could not read file for analysis"
                })
        
        return issues
    
    def _check_python_issues(self, content: str, file_path: str) -> List[Dict]:
        """Check Python files for common issues"""
        issues = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Check for TODO comments without dates
            if re.search(r'#\s*TODO', line, re.IGNORECASE):
                if not re.search(r'\d{4}-\d{2}-\d{2}', line):
                    issues.append({
                        "type": "code_quality",
                        "severity": "low",
                        "file": file_path,
                        "line": i,
                        "issue": "TODO without date",
                        "description": "TODO comments should include dates for tracking"
                    })
            
            # Check for unused imports (basic check)
            if line_stripped.startswith('import ') or line_stripped.startswith('from '):
                import_name = line_stripped.split()[-1].replace('.', '')
                if import_name not in content.replace(line, ''):
                    issues.append({
                        "type": "code_quality",
                        "severity": "low",
                        "file": file_path,
                        "line": i,
                        "issue": "Potentially unused import",
                        "description": f"Import {import_name} may not be used"
                    })
            
            # Check for hardcoded secrets
            if re.search(r'(password|secret|key|token)\s*=\s*[\'"][^\'"]+[\'"]', line, re.IGNORECASE):
                issues.append({
                    "type": "security",
                    "severity": "high",
                    "file": file_path,
                    "line": i,
                    "issue": "Hardcoded secret detected",
                    "description": "Secrets should be stored in environment variables"
                })
            
            # Check for bare except clauses
            if re.search(r'except\s*:', line):
                issues.append({
                    "type": "code_quality",
                    "severity": "medium",
                    "file": file_path,
                    "line": i,
                    "issue": "Bare except clause",
                    "description": "Except clauses should specify exception types"
                })
        
        return issues
    
    def _check_javascript_issues(self, content: str, file_path: str) -> List[Dict]:
        """Check JavaScript files for common issues"""
        issues = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Check for console.log statements
            if 'console.log' in line and '//' not in line.split('console.log')[0]:
                issues.append({
                    "type": "code_quality",
                    "severity": "low",
                    "file": file_path,
                    "line": i,
                    "issue": "Console.log statement",
                    "description": "Console.log should be removed in production"
                })
            
            # Check for var usage (prefer const/let)
            if re.search(r'\bvar\s+\w+', line):
                issues.append({
                    "type": "code_quality",
                    "severity": "low",
                    "file": file_path,
                    "line": i,
                    "issue": "var usage detected",
                    "description": "Use const or let instead of var"
                })
            
            # Check for == instead of ===
            if '==' in line and '===' not in line and '//' not in line.split('==')[0]:
                issues.append({
                    "type": "code_quality",
                    "severity": "medium",
                    "file": file_path,
                    "line": i,
                    "issue": "Loose equality comparison",
                    "description": "Use === instead of == for strict equality"
                })
        
        return issues
    
    async def _analyze_performance(self) -> List[Dict]:
        """Analyse Performance-Probleme"""
        issues = []
        
        try:
            # Check memory usage
            import psutil
            memory = psutil.virtual_memory()
            if memory.percent > 85:
                issues.append({
                    "type": "performance",
                    "severity": "high",
                    "issue": "High memory usage",
                    "description": f"Memory usage is {memory.percent:.1f}%",
                    "value": memory.percent
                })
            
            # Check disk usage
            disk = psutil.disk_usage('/')
            if disk.percent > 90:
                issues.append({
                    "type": "performance",
                    "severity": "high",
                    "issue": "High disk usage",
                    "description": f"Disk usage is {disk.percent:.1f}%",
                    "value": disk.percent
                })
            
            # Check CPU usage (average over 5 seconds)
            cpu_percent = psutil.cpu_percent(interval=5)
            if cpu_percent > 80:
                issues.append({
                    "type": "performance",
                    "severity": "medium",
                    "issue": "High CPU usage",
                    "description": f"CPU usage is {cpu_percent:.1f}%",
                    "value": cpu_percent
                })
            
        except ImportError:
            issues.append({
                "type": "performance",
                "severity": "low",
                "issue": "psutil not available",
                "description": "Install psutil for performance monitoring"
            })
        except Exception as e:
            issues.append({
                "type": "performance",
                "severity": "medium",
                "issue": "Performance analysis failed",
                "description": str(e)
            })
        
        return issues
    
    async def analyzePerformancePatterns(self) -> Dict:
        """Analysiert Performance-Muster und Trends"""
        try:
            patterns = {
                "timestamp": datetime.now().isoformat(),
                "memory_trends": [],
                "cpu_trends": [],
                "disk_trends": [],
                "process_analysis": [],
                "bottlenecks": [],
                "recommendations": []
            }
            
            import psutil
            
            # Memory Pattern Analysis
            memory = psutil.virtual_memory()
            memory_pattern = {
                "current": memory.percent,
                "available_gb": memory.available / (1024**3),
                "used_gb": memory.used / (1024**3),
                "pressure": "high" if memory.percent > 85 else "medium" if memory.percent > 70 else "normal",
                "trend": self._analyze_memory_trend()
            }
            patterns["memory_trends"].append(memory_pattern)
            
            # CPU Pattern Analysis
            cpu_pattern = {
                "current": psutil.cpu_percent(interval=1),
                "cores": psutil.cpu_count(),
                "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0],
                "pressure": "high" if psutil.cpu_percent() > 80 else "medium" if psutil.cpu_percent() > 60 else "normal"
            }
            patterns["cpu_trends"].append(cpu_pattern)
            
            # Disk Pattern Analysis
            disk = psutil.disk_usage('/')
            disk_pattern = {
                "current": disk.percent,
                "free_gb": disk.free / (1024**3),
                "used_gb": disk.used / (1024**3),
                "pressure": "critical" if disk.percent > 95 else "high" if disk.percent > 85 else "normal"
            }
            patterns["disk_trends"].append(disk_pattern)
            
            # Process Analysis
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    proc_info = proc.info
                    if proc_info['cpu_percent'] > 10 or proc_info['memory_percent'] > 5:
                        patterns["process_analysis"].append({
                            "pid": proc_info['pid'],
                            "name": proc_info['name'],
                            "cpu": proc_info['cpu_percent'],
                            "memory": proc_info['memory_percent'],
                            "status": proc_info['status']
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Identify Bottlenecks
            if memory_pattern["pressure"] == "high":
                patterns["bottlenecks"].append({
                    "type": "memory",
                    "severity": "high",
                    "description": "High memory pressure detected",
                    "value": memory_pattern["current"]
                })
            
            if cpu_pattern["pressure"] == "high":
                patterns["bottlenecks"].append({
                    "type": "cpu",
                    "severity": "high", 
                    "description": "High CPU usage detected",
                    "value": cpu_pattern["current"]
                })
            
            if disk_pattern["pressure"] == "critical":
                patterns["bottlenecks"].append({
                    "type": "disk",
                    "severity": "critical",
                    "description": "Critical disk space",
                    "value": disk_pattern["current"]
                })
            
            # Generate Recommendations
            patterns["recommendations"] = self._generate_performance_recommendations(patterns)
            
            return patterns
            
        except ImportError:
            return {"error": "psutil not available for performance analysis"}
        except Exception as e:
            return {"error": f"Performance pattern analysis failed: {e}"}
    
    def _analyze_memory_trend(self) -> str:
        """Analysiert Memory-Trend basierend auf Historie"""
        try:
            # Load historical data
            if self.scan_results.exists():
                with open(self.scan_results, 'r') as f:
                    data = json.load(f)
                
                recent_scans = data.get("scans", [])[-5:]  # Last 5 scans
                memory_values = []
                
                for scan in recent_scans:
                    perf_issues = scan.get("performance_issues", [])
                    for issue in perf_issues:
                        if "memory" in issue.get("issue", "").lower():
                            memory_values.append(issue.get("value", 0))
                
                if len(memory_values) >= 3:
                    if memory_values[-1] > memory_values[-2] > memory_values[-3]:
                        return "increasing"
                    elif memory_values[-1] < memory_values[-2] < memory_values[-3]:
                        return "decreasing"
                    else:
                        return "stable"
            
            return "unknown"
        except Exception:
            return "unknown"
    
    def _generate_performance_recommendations(self, patterns: Dict) -> List[Dict]:
        """Generiert Performance-Optimierungsempfehlungen"""
        recommendations = []
        
        # Memory recommendations
        memory_pressure = patterns.get("memory_trends", [{}])[0].get("pressure", "normal")
        if memory_pressure == "high":
            recommendations.append({
                "type": "memory",
                "priority": "high",
                "title": "Memory Optimization Required",
                "description": "High memory usage detected. Consider memory cleanup or process optimization.",
                "action": "Review memory-intensive processes and implement cleanup routines"
            })
        
        # CPU recommendations
        cpu_pressure = patterns.get("cpu_trends", [{}])[0].get("pressure", "normal")
        if cpu_pressure == "high":
            recommendations.append({
                "type": "cpu",
                "priority": "medium",
                "title": "CPU Optimization",
                "description": "High CPU usage detected. Check for inefficient processes.",
                "action": "Optimize algorithms and consider process throttling"
            })
        
        # Disk recommendations
        disk_pressure = patterns.get("disk_trends", [{}])[0].get("pressure", "normal")
        if disk_pressure in ["high", "critical"]:
            recommendations.append({
                "type": "disk",
                "priority": "critical" if disk_pressure == "critical" else "high",
                "title": "Disk Space Management",
                "description": f"Disk usage is {patterns.get('disk_trends', [{}])[0].get('current', 0)}%",
                "action": "Clean up log files, cache, and unnecessary data"
            })
        
        # Process recommendations
        high_cpu_processes = [p for p in patterns.get("process_analysis", []) if p.get("cpu", 0) > 50]
        if high_cpu_processes:
            recommendations.append({
                "type": "process",
                "priority": "medium",
                "title": "High CPU Processes Detected",
                "description": f"{len(high_cpu_processes)} processes using >50% CPU",
                "action": "Investigate and optimize high-CPU processes"
            })
        
        return recommendations
    
    async def _analyze_security(self) -> List[Dict]:
        """Analyse Sicherheitsprobleme"""
        issues = []
        
        # Check for exposed API keys in .env files
        env_files = list(self.base_dir.rglob(".env*"))
        for env_file in env_files:
            try:
                with open(env_file, 'r') as f:
                    content = f.read()
                
                # Check for weak passwords
                if len(content) < 50:  # Very basic check
                    issues.append({
                        "type": "security",
                        "severity": "medium",
                        "file": str(env_file),
                        "issue": "Small .env file",
                        "description": ".env file might contain insufficient configuration"
                    })
                
            except Exception:
                continue
        
        # Check for world-writable files
        try:
            for file_path in self.base_dir.rglob("*"):
                if file_path.is_file() and os.access(file_path, os.W_OK):
                    try:
                        stat = file_path.stat()
                        if stat.st_mode & 0o002:  # World writable
                            issues.append({
                                "type": "security",
                                "severity": "high",
                                "file": str(file_path),
                                "issue": "World-writable file",
                                "description": "File is writable by anyone"
                            })
                    except Exception:
                        continue
        except Exception:
            pass
        
        return issues
    
    async def _test_buttons(self) -> List[Dict]:
        """Testet alle Button-Funktionen im System"""
        results = []
        
        # Test dashboard buttons
        dashboard_files = list(self.base_dir.rglob("*.html"))
        for html_file in dashboard_files:
            try:
                with open(html_file, 'r') as f:
                    content = f.read()
                
                # Find button elements
                button_matches = re.findall(r'<button[^>]*>(.*?)</button>', content, re.IGNORECASE)
                for i, button_text in enumerate(button_matches):
                    results.append({
                        "type": "button_test",
                        "file": str(html_file),
                        "button_index": i,
                        "button_text": button_text.strip(),
                        "status": "found",
                        "description": "Button detected in HTML"
                    })
                
            except Exception as e:
                results.append({
                    "type": "button_test",
                    "file": str(html_file),
                    "status": "error",
                    "description": f"Error reading file: {e}"
                })
        
        # Test JavaScript button handlers
        js_files = list(self.base_dir.rglob("*.js"))
        for js_file in js_files:
            try:
                with open(js_file, 'r') as f:
                    content = f.read()
                
                # Find click handlers
                click_handlers = re.findall(r'addEventListener\([\'"]click[\'"]', content)
                if click_handlers:
                    results.append({
                        "type": "button_test",
                        "file": str(js_file),
                        "handlers_found": len(click_handlers),
                        "status": "handlers_detected",
                        "description": f"Found {len(click_handlers)} click handlers"
                    })
                
            except Exception as e:
                results.append({
                    "type": "button_test",
                    "file": str(js_file),
                    "status": "error",
                    "description": f"Error reading file: {e}"
                })
        
        return results
    
    async def _test_functionality(self) -> List[Dict]:
        """Testet Funktionalität von Systemkomponenten"""
        results = []
        
        # Test API endpoints
        try:
            import aiohttp
            test_endpoints = [
                "http://localhost:8888/api/system",
                "http://localhost:8888/api/services",
                "http://localhost:8888/health"
            ]
            
            for endpoint in test_endpoints:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                results.append({
                                    "type": "functionality_test",
                                    "endpoint": endpoint,
                                    "status": "working",
                                    "response_code": response.status
                                })
                            else:
                                results.append({
                                    "type": "functionality_test",
                                    "endpoint": endpoint,
                                    "status": "error",
                                    "response_code": response.status,
                                    "description": f"HTTP {response.status}"
                                })
                except Exception as e:
                    results.append({
                        "type": "functionality_test",
                        "endpoint": endpoint,
                        "status": "failed",
                        "description": str(e)
                    })
                    
        except ImportError:
            results.append({
                "type": "functionality_test",
                "status": "skip",
                "description": "aiohttp not available for testing"
            })
        
        # Test service ports
        service_ports = {
            3001: "Shopify Suite",
            3002: "CreatorHub", 
            8000: "Telegram Bot",
            8888: "Dashboard"
        }
        
        for port, service_name in service_ports.items():
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(('localhost', port))
                sock.close()
                
                if result == 0:
                    results.append({
                        "type": "functionality_test",
                        "service": service_name,
                        "port": port,
                        "status": "running"
                    })
                else:
                    results.append({
                        "type": "functionality_test", 
                        "service": service_name,
                        "port": port,
                        "status": "down"
                    })
                    
            except Exception as e:
                results.append({
                    "type": "functionality_test",
                    "service": service_name,
                    "port": port,
                    "status": "error",
                    "description": str(e)
                })
        
        return results
    
    async def _analyze_configuration(self) -> List[Dict]:
        """Analysiert Konfigurationsdateien"""
        issues = []
        
        # Check .env files
        env_files = list(self.base_dir.rglob(".env*"))
        if not env_files:
            issues.append({
                "type": "configuration",
                "severity": "high",
                "issue": "No .env files found",
                "description": "Environment configuration files are missing"
            })
        
        for env_file in env_files:
            try:
                with open(env_file, 'r') as f:
                    content = f.read()
                
                # Check for required variables
                required_vars = ["PORT", "NODE_ENV", "API_KEY"]
                missing_vars = []
                
                for var in required_vars:
                    if var not in content:
                        missing_vars.append(var)
                
                if missing_vars:
                    issues.append({
                        "type": "configuration",
                        "severity": "medium",
                        "file": str(env_file),
                        "issue": "Missing environment variables",
                        "description": f"Missing: {', '.join(missing_vars)}"
                    })
                
            except Exception as e:
                issues.append({
                    "type": "configuration",
                    "severity": "medium",
                    "file": str(env_file),
                    "issue": "Error reading .env file",
                    "description": str(e)
                })
        
        return issues
    
    async def _analyze_dependencies(self) -> List[Dict]:
        """Analysiert Abhängigkeiten"""
        issues = []
        
        # Check package.json files
        package_files = list(self.base_dir.rglob("package.json"))
        for package_file in package_files:
            try:
                with open(package_file, 'r') as f:
                    package_data = json.load(f)
                
                # Check for outdated dependencies (basic check)
                deps = package_data.get("dependencies", {})
                dev_deps = package_data.get("devDependencies", {})
                
                all_deps = {**deps, **dev_deps}
                
                # Check for very old versions (simplified)
                for dep_name, version in all_deps.items():
                    if isinstance(version, str) and version.startswith("^0.") or version.startswith("0."):
                        issues.append({
                            "type": "dependency",
                            "severity": "medium",
                            "file": str(package_file),
                            "dependency": dep_name,
                            "version": version,
                            "issue": "Potentially outdated dependency",
                            "description": f"{dep_name} version {version} may be outdated"
                        })
                
            except Exception as e:
                issues.append({
                    "type": "dependency",
                    "severity": "medium",
                    "file": str(package_file),
                    "issue": "Error reading package.json",
                    "description": str(e)
                })
        
        return issues
    
    async def _analyze_resources(self) -> List[Dict]:
        """Analysiert Ressourcen-Nutzung"""
        issues = []
        
        try:
            # Check log files size
            log_files = list(self.logs_dir.rglob("*.log"))
            for log_file in log_files:
                size_mb = log_file.stat().st_size / (1024 * 1024)
                if size_mb > 100:  # Larger than 100MB
                    issues.append({
                        "type": "resource",
                        "severity": "medium",
                        "file": str(log_file),
                        "issue": "Large log file",
                        "description": f"Log file is {size_mb:.1f}MB - consider rotation"
                    })
            
            # Check data files
            data_files = list(self.data_dir.rglob("*.json"))
            for data_file in data_files:
                size_mb = data_file.stat().st_size / (1024 * 1024)
                if size_mb > 50:  # Larger than 50MB
                    issues.append({
                        "type": "resource",
                        "severity": "medium",
                        "file": str(data_file),
                        "issue": "Large data file",
                        "description": f"Data file is {size_mb:.1f}MB - consider cleanup"
                    })
            
        except Exception as e:
            issues.append({
                "type": "resource",
                "severity": "low",
                "issue": "Resource analysis failed",
                "description": str(e)
            })
        
        return issues
    
    async def _generate_recommendations(self, scan_results: Dict) -> List[Dict]:
        """Generiert Verbesserungsempfehlungen"""
        recommendations = []
        
        total_issues = scan_results.get("total_issues", 0)
        
        if total_issues > 50:
            recommendations.append({
                "priority": "high",
                "category": "overall",
                "title": "High number of issues detected",
                "description": f"Found {total_issues} issues. Consider systematic refactoring.",
                "action": "Plan systematic code cleanup and refactoring"
            })
        
        # Check for security issues
        security_issues = [i for i in scan_results.get("security_issues", []) if i.get("severity") == "high"]
        if security_issues:
            recommendations.append({
                "priority": "critical",
                "category": "security",
                "title": "Security vulnerabilities found",
                "description": f"Found {len(security_issues)} high-severity security issues",
                "action": "Address security issues immediately"
            })
        
        # Check for performance issues
        perf_issues = [i for i in scan_results.get("performance_issues", []) if i.get("severity") == "high"]
        if perf_issues:
            recommendations.append({
                "priority": "high",
                "category": "performance",
                "title": "Performance issues detected",
                "description": f"Found {len(perf_issues)} high-severity performance issues",
                "action": "Optimize performance bottlenecks"
            })
        
        # Check button functionality
        button_tests = scan_results.get("button_test_results", [])
        if button_tests:
            working_buttons = [b for b in button_tests if b.get("status") == "working"]
            total_buttons = len([b for b in button_tests if "button_text" in b])
            
            if total_buttons > 0 and len(working_buttons) < total_buttons:
                recommendations.append({
                    "priority": "medium",
                    "category": "functionality",
                    "title": "Button functionality issues",
                    "description": f"Only {len(working_buttons)}/{total_buttons} buttons are working",
                    "action": "Fix button event handlers and functionality"
                })
        
        return recommendations
    
    async def _save_scan_results(self, results: Dict):
        """Speichert Scan-Ergebnisse"""
        try:
            # Load existing results
            if self.scan_results.exists():
                with open(self.scan_results, 'r') as f:
                    data = json.load(f)
            else:
                data = {"scans": [], "latest": {}}
            
            # Add new scan
            data["scans"].append(results)
            data["latest"] = results
            
            # Keep only last 50 scans
            if len(data["scans"]) > 50:
                data["scans"] = data["scans"][-50:]
            
            # Save updated results
            with open(self.scan_results, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving scan results: {e}")
    
    async def auto_repair(self, scan_results: Dict) -> Dict:
        """Führt automatische Reparaturen durch"""
        repair_results = {
            "timestamp": datetime.now().isoformat(),
            "repairs_attempted": 0,
            "repairs_successful": 0,
            "repairs_failed": 0,
            "repairs": []
        }
        
        issues_to_fix = []
        
        # Collect fixable issues
        for category in ["code_quality_issues", "performance_issues", "security_issues"]:
            for issue in scan_results.get(category, []):
                if self._is_fixable(issue):
                    issues_to_fix.append(issue)
        
        repair_results["repairs_attempted"] = len(issues_to_fix)
        
        # Attempt repairs
        for issue in issues_to_fix:
            try:
                repair_result = await self._fix_issue(issue)
                repair_results["repairs"].append(repair_result)
                
                if repair_result.get("success"):
                    repair_results["repairs_successful"] += 1
                else:
                    repair_results["repairs_failed"] += 1
                    
            except Exception as e:
                repair_results["repairs"].append({
                    "issue": issue,
                    "success": False,
                    "error": str(e)
                })
                repair_results["repairs_failed"] += 1
        
        # Update repair history
        self._update_repair_history(repair_results)
        
        # Update metrics
        self.scan_metrics["errors_fixed"] += repair_results["repairs_successful"]
        
        logger.info(f"🔧 Auto-repair completed: {repair_results['repairs_successful']}/{repair_results['repairs_attempted']} successful")
        
        return repair_results
    
    def _is_fixable(self, issue: Dict) -> bool:
        """Prüft ob ein Issue automatisch repariert werden kann"""
        fixable_patterns = [
            "TODO without date",
            "Console.log statement",
            "var usage detected",
            "Loose equality comparison",
            "Bare except clause"
        ]
        
        issue_text = issue.get("issue", "")
        return any(pattern in issue_text for pattern in fixable_patterns)
    
    async def _fix_issue(self, issue: Dict) -> Dict:
        """Repariert ein einzelnes Issue"""
        try:
            file_path = issue.get("file")
            line_number = issue.get("line")
            issue_type = issue.get("issue", "")
            
            if not file_path or not line_number:
                return {
                    "issue": issue,
                    "success": False,
                    "error": "Missing file path or line number"
                }
            
            file_path = Path(file_path)
            if not file_path.exists():
                return {
                    "issue": issue,
                    "success": False,
                    "error": "File not found"
                }
            
            # Read file
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            if line_number > len(lines):
                return {
                    "issue": issue,
                    "success": False,
                    "error": "Line number out of range"
                }
            
            original_line = lines[line_number - 1]
            fixed_line = original_line
            
            # Apply fixes based on issue type
            if "TODO without date" in issue_type:
                date_str = datetime.now().strftime("%Y-%m-%d")
                fixed_line = re.sub(r'#\s*TODO', f'# TODO [{date_str}]', original_line)
            
            elif "Console.log statement" in issue_type and "console.log" in original_line:
                # Comment out console.log
                fixed_line = re.sub(r'(\s*)(console\.log)', r'\1// \2', original_line)
            
            elif "var usage detected" in issue_type:
                # Replace var with const
                fixed_line = re.sub(r'\bvar\s+', 'const ', original_line)
            
            elif "Loose equality comparison" in issue_type:
                # Replace == with ===
                fixed_line = original_line.replace('==', '===')
            
            elif "Bare except clause" in issue_type:
                # Add Exception to bare except
                fixed_line = re.sub(r'except\s*:', 'except Exception:', original_line)
            
            # Check if line was actually changed
            if fixed_line != original_line:
                # Write fixed file
                lines[line_number - 1] = fixed_line
                with open(file_path, 'w') as f:
                    f.writelines(lines)
                
                return {
                    "issue": issue,
                    "success": True,
                    "action": f"Fixed line {line_number} in {file_path.name}",
                    "original": original_line.strip(),
                    "fixed": fixed_line.strip()
                }
            else:
                return {
                    "issue": issue,
                    "success": False,
                    "error": "No changes made"
                }
                
        except Exception as e:
            return {
                "issue": issue,
                "success": False,
                "error": str(e)
            }
    
    def _update_repair_history(self, repair_results: Dict):
        """Aktualisiert Reparatur-Historie"""
        try:
            # Load existing history
            if self.repair_history.exists():
                with open(self.repair_history, 'r') as f:
                    history = json.load(f)
            else:
                history = {"repairs": [], "successful_fixes": 0}
            
            # Add new repair
            history["repairs"].append(repair_results)
            history["successful_fixes"] += repair_results["repairs_successful"]
            
            # Keep only last 100 repairs
            if len(history["repairs"]) > 100:
                history["repairs"] = history["repairs"][-100:]
            
            # Save updated history
            with open(self.repair_history, 'w') as f:
                json.dump(history, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error updating repair history: {e}")
    
    async def continuous_improvement(self) -> Dict:
        """Führt kontinuierliche Verbesserung durch"""
        improvement_results = {
            "timestamp": datetime.now().isoformat(),
            "patterns_learned": [],
            "improvements_made": 0,
            "new_fixes_added": 0
        }
        
        try:
            # Analyze repair history for patterns
            if self.repair_history_data.get("repairs"):
                recent_repairs = self.repair_history_data["repairs"][-10:]  # Last 10 repairs
                
                # Find common patterns
                pattern_counts = {}
                for repair in recent_repairs:
                    for repair_detail in repair.get("repairs", []):
                        if repair_detail.get("success"):
                            issue_type = repair_detail.get("issue", {}).get("issue", "")
                            pattern_counts[issue_type] = pattern_counts.get(issue_type, 0) + 1
                
                # Add new patterns for common issues
                for pattern, count in pattern_counts.items():
                    if count >= 3 and pattern not in self.error_patterns:
                        self.error_patterns[pattern] = {
                            "frequency": count,
                            "auto_fix_available": True,
                            "added_date": datetime.now().isoformat()
                        }
                        improvement_results["patterns_learned"].append(pattern)
                        improvement_results["new_fixes_added"] += 1
                
                # Save updated patterns
                with open(self.error_db, 'w') as f:
                    json.dump({"patterns": self.error_patterns, "last_updated": datetime.now().isoformat()}, f, indent=2)
            
            improvement_results["improvements_made"] = len(improvement_results["patterns_learned"])
            
            # Update improvement log
            self._update_improvement_log(improvement_results)
            
            logger.info(f"🚀 Continuous improvement: {improvement_results['improvements_made']} improvements made")
            
        except Exception as e:
            logger.error(f"Continuous improvement failed: {e}")
            improvement_results["error"] = str(e)
        
        return improvement_results
    
    def _update_improvement_log(self, improvement_results: Dict):
        """Aktualisiert Verbesserungs-Log"""
        try:
            # Load existing log
            if self.improvement_log.exists():
                with open(self.improvement_log, 'r') as f:
                    log = json.load(f)
            else:
                log = {"improvements": [], "version": "1.0"}
            
            # Add new improvement
            log["improvements"].append(improvement_results)
            
            # Update version
            version_parts = log["version"].split(".")
            version_parts[-1] = str(int(version_parts[-1]) + 1)
            log["version"] = ".".join(version_parts)
            
            # Keep only last 50 improvements
            if len(log["improvements"]) > 50:
                log["improvements"] = log["improvements"][-50:]
            
            # Save updated log
            with open(self.improvement_log, 'w') as f:
                json.dump(log, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error updating improvement log: {e}")
    
    async def run_scheduled_deep_scan(self) -> Dict:
        """Führt geplanten DeepScan mit Reparatur durch"""
        logger.info(f"🔄 Starting scheduled DeepScan for {self.bot_name}")
        
        # Perform deep scan
        scan_results = await self.perform_deep_scan()
        
        # Auto-repair if issues found
        if scan_results.get("total_issues", 0) > 0:
            repair_results = await self.auto_repair(scan_results)
            scan_results["auto_repair"] = repair_results
        
        # Continuous improvement
        improvement_results = await self.continuous_improvement()
        scan_results["continuous_improvement"] = improvement_results
        
        # Cloud Backup nach Scan
        backup_result = None
        if self.backup_manager and scan_results.get("total_issues", 0) > 0:
            backup_result = await self.backup_manager.create_backup()
            scan_results["backup"] = backup_result
        
        # Generate summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "scan_id": scan_results.get("scan_id"),
            "issues_found": scan_results.get("total_issues", 0),
            "issues_fixed": repair_results.get("repairs_successful", 0),
            "improvements_made": improvement_results.get("improvements_made", 0),
            "scan_duration": scan_results.get("scan_duration", 0),
            "backup_performed": backup_result.get("success", False) if backup_result else False,
            "status": "completed"
        }
        
        logger.info(f"✅ Scheduled DeepScan completed: {summary['issues_found']} issues, {summary['issues_fixed']} fixed")
        
        return summary
    
    def get_metrics(self) -> Dict:
        """Gibt aktuelle Metriken zurück"""
        return {
            "scan_metrics": self.scan_metrics,
            "error_patterns_count": len(self.error_patterns),
            "repair_history_count": len(self.repair_history_data.get("repairs", [])),
            "improvement_version": self.improvements.get("version", "1.0"),
            "last_update": datetime.now().isoformat()
        }


# Scheduler für 3x tägliche Scans
class DeepScanScheduler:
    """Scheduler für automatische DeepScans"""
    
    def __init__(self, tool: DeepScanRepairTool):
        self.tool = tool
        self.scan_times = ["06:00", "14:00", "22:00"]  # 3x täglich
        self.running = False
    
    async def start_scheduler(self):
        """Startet den Scheduler"""
        self.running = True
        logger.info("📅 DeepScan Scheduler started - 3x daily scans")
        
        while self.running:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            
            if current_time in self.scan_times:
                logger.info(f"⏰ Triggering scheduled scan at {current_time}")
                await self.tool.run_scheduled_deep_scan()
                
                # Wait 1 minute to avoid multiple triggers
                await asyncio.sleep(60)
            
            # Check every minute
            await asyncio.sleep(60)
    
    def stop_scheduler(self):
        """Stoppt den Scheduler"""
        self.running = False
        logger.info("📅 DeepScan Scheduler stopped")


# Integration in bestehende Bot-Systeme
def integrate_deepscan_tool(bot_instance):
    """Integriert das DeepScan Tool in ein Bot-System"""
    
    # Tool initialisieren
    deepscan_tool = DeepScanRepairTool()
    
    # Scheduler initialisieren
    scheduler = DeepScanScheduler(deepscan_tool)
    
    # Commands hinzufügen
    async def cmd_deepscan(ctx):
        """Führt manuellen DeepScan durch"""
        await ctx.send("🔍 Starte DeepScan...")
        results = await deepscan_tool.run_scheduled_deep_scan()
        
        await ctx.send(f"✅ DeepScan abgeschlossen:\n"
                      f"• Issues gefunden: {results['issues_found']}\n"
                      f"• Issues gefixt: {results['issues_fixed']}\n"
                      f"• Verbesserungen: {results['improvements_made']}")
    
    async def cmd_metrics(ctx):
        """Zeigt aktuelle Metriken"""
        metrics = deepscan_tool.get_metrics()
        
        await ctx.send(f"📊 DeepScan Metriken:\n"
                      f"• Scans insgesamt: {metrics['scan_metrics']['total_scans']}\n"
                      f"• Errors gefunden: {metrics['scan_metrics']['errors_found']}\n"
                      f"• Errors gefixt: {metrics['scan_metrics']['errors_fixed']}\n"
                      f"• Error-Patterns: {metrics['error_patterns_count']}\n"
                      f"• Version: {metrics['improvement_version']}")
    
    async def cmd_repair(ctx):
        """Führt automatische Reparatur durch"""
        await ctx.send("🔧 Starte automatische Reparatur...")
        
        # Quick scan for fixable issues
        scan_results = await deepscan_tool.perform_deep_scan()
        repair_results = await deepscan_tool.auto_repair(scan_results)
        
        await ctx.send(f"🔧 Reparatur abgeschlossen:\n"
                      f"• Versucht: {repair_results['repairs_attempted']}\n"
                      f"• Erfolgreich: {repair_results['repairs_successful']}\n"
                      f"• Fehlgeschlagen: {repair_results['repairs_failed']}")
    
    # Commands registrieren (Beispiel für Discord-Bot)
    if hasattr(bot_instance, 'add_command'):
        bot_instance.add_command('deepscan', cmd_deepscan)
        bot_instance.add_command('metrics', cmd_metrics) 
        bot_instance.add_command('repair', cmd_repair)
    
    # Background scheduler starten
    asyncio.create_task(scheduler.start_scheduler())
    
    logger.info("🔧 DeepScan Tool erfolgreich integriert")
    
    return deepscan_tool, scheduler


# Beispiel für die Verwendung
if __name__ == "__main__":
    async def main():
        tool = DeepScanRepairTool()
        
        # Manuel Test
        print("🔍 Test DeepScan...")
        results = await tool.run_scheduled_deep_scan()
        print(f"✅ Test abgeschlossen: {results}")
        
        # Metriken anzeigen
        metrics = tool.get_metrics()
        print(f"📊 Metriken: {metrics}")
    
    asyncio.run(main())
