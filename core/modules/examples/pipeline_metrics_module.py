# core/modules/examples/pipeline_metrics_module.py
"""
Pipeline Metrics Module - Example implementation demonstrating metrics collection and monitoring
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import statistics
from semantic_version import Version

from ..interface import (
    MaestroCatModule, ModuleMetadata, ExtensionPoint, ModuleCapability
)
from ...context.pipeline_context import PipelineContext, ContextScope


class PipelineMetricsModule(MaestroCatModule):
    """
    Pipeline metrics collection module demonstrating:
    - Performance monitoring across all pipeline stages
    - Real-time metrics calculation
    - Historical data tracking
    - Alerting on performance thresholds
    - Extension point usage for comprehensive monitoring
    """
    
    @classmethod
    def get_metadata(cls) -> ModuleMetadata:
        """Return module metadata"""
        return ModuleMetadata(
            name="PipelineMetricsModule",
            version=Version("1.5.0"),
            description="Comprehensive pipeline performance monitoring and metrics collection",
            author="MaestroCat Team",
            capabilities=[
                ModuleCapability.METRICS_COLLECTION,
                ModuleCapability.PERFORMANCE_MONITORING,
                ModuleCapability.DEBUG_LOGGING
            ],
            extension_points=[
                ExtensionPoint.PRE_STT,
                ExtensionPoint.POST_STT,
                ExtensionPoint.PRE_LLM,
                ExtensionPoint.POST_LLM,
                ExtensionPoint.PRE_TTS,
                ExtensionPoint.POST_TTS,
                ExtensionPoint.INTERRUPTION_DETECTED,
                ExtensionPoint.ERROR_OCCURRED
            ],
            dependencies=[],
            config_schema={
                "collection_interval": {"type": "number", "default": 1.0, "minimum": 0.1},
                "history_retention_hours": {"type": "integer", "default": 24, "minimum": 1},
                "alert_thresholds": {
                    "type": "object",
                    "properties": {
                        "stt_latency_ms": {"type": "number", "default": 1000},
                        "llm_latency_ms": {"type": "number", "default": 3000},
                        "tts_latency_ms": {"type": "number", "default": 2000},
                        "total_latency_ms": {"type": "number", "default": 5000}
                    }
                },
                "enable_detailed_logging": {"type": "boolean", "default": False},
                "export_metrics": {"type": "boolean", "default": False},
                "export_interval": {"type": "number", "default": 60.0}
            }
        )
    
    def __init__(self, context):
        super().__init__(context)
        
        # Configuration
        config = self.config
        self.collection_interval = config.get("collection_interval", 1.0)
        self.history_retention_hours = config.get("history_retention_hours", 24)
        self.alert_thresholds = config.get("alert_thresholds", {
            "stt_latency_ms": 1000,
            "llm_latency_ms": 3000,
            "tts_latency_ms": 2000,
            "total_latency_ms": 5000
        })
        self.enable_detailed_logging = config.get("enable_detailed_logging", False)
        self.export_metrics = config.get("export_metrics", False)
        self.export_interval = config.get("export_interval", 60.0)
        
        # Metrics storage
        self.current_metrics = {
            "stt_latency": [],
            "llm_latency": [],
            "tts_latency": [],
            "total_latency": [],
            "interruption_count": 0,
            "error_count": 0,
            "requests_processed": 0,
            "active_requests": 0
        }
        
        # Historical data
        self.metrics_history: List[Dict[str, Any]] = []
        
        # Request tracking
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        
        # Performance statistics
        self.performance_stats = {
            "uptime_start": datetime.now(),
            "last_alert": None,
            "alert_count": 0
        }
        
        # Background tasks
        self._collection_task: Optional[asyncio.Task] = None
        self._export_task: Optional[asyncio.Task] = None
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate module configuration"""
        errors = []
        
        if "collection_interval" in config:
            if not isinstance(config["collection_interval"], (int, float)) or config["collection_interval"] < 0.1:
                errors.append("collection_interval must be a number >= 0.1")
        
        if "history_retention_hours" in config:
            if not isinstance(config["history_retention_hours"], int) or config["history_retention_hours"] < 1:
                errors.append("history_retention_hours must be an integer >= 1")
        
        return errors
    
    async def initialize(self) -> bool:
        """Initialize the metrics module"""
        try:
            self.logger.info(f"Initializing {self.name} with collection interval {self.collection_interval}s")
            
            # Initialize metrics storage
            self.current_metrics = {
                "stt_latency": [],
                "llm_latency": [],
                "tts_latency": [],
                "total_latency": [],
                "interruption_count": 0,
                "error_count": 0,
                "requests_processed": 0,
                "active_requests": 0
            }
            
            self.performance_stats["uptime_start"] = datetime.now()
            
            self.logger.info("Pipeline metrics module initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize metrics module: {e}")
            return False
    
    async def start(self) -> bool:
        """Start the metrics module"""
        try:
            self.logger.info("Starting pipeline metrics collection")
            
            # Start metrics collection task
            self._collection_task = asyncio.create_task(self._metrics_collection_loop())
            
            # Start export task if enabled
            if self.export_metrics:
                self._export_task = asyncio.create_task(self._metrics_export_loop())
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start metrics module: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop the metrics module"""
        try:
            self.logger.info("Stopping pipeline metrics collection")
            
            # Cancel background tasks
            if self._collection_task:
                self._collection_task.cancel()
                try:
                    await self._collection_task
                except asyncio.CancelledError:
                    pass
            
            if self._export_task:
                self._export_task.cancel()
                try:
                    await self._export_task
                except asyncio.CancelledError:
                    pass
            
            # Export final metrics
            if self.export_metrics:
                await self._export_current_metrics()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop metrics module: {e}")
            return False
    
    # Extension Point Handlers
    
    async def handle_extension_point(
        self, 
        point: ExtensionPoint, 
        context: PipelineContext
    ) -> PipelineContext:
        """Handle pipeline extension points for metrics collection"""
        try:
            request_id = id(context)
            current_time = datetime.now()
            
            if point == ExtensionPoint.PRE_STT:
                # Start tracking a new request
                self.active_requests[request_id] = {
                    "start_time": current_time,
                    "stt_start": current_time,
                    "stages": []
                }
                self.current_metrics["active_requests"] += 1
                
            elif point == ExtensionPoint.POST_STT:
                # Record STT completion
                if request_id in self.active_requests:
                    req = self.active_requests[request_id]
                    stt_latency = (current_time - req["stt_start"]).total_seconds() * 1000
                    self.current_metrics["stt_latency"].append(stt_latency)
                    req["stages"].append(("stt", stt_latency))
                    
                    # Check alert threshold
                    if stt_latency > self.alert_thresholds.get("stt_latency_ms", 1000):
                        await self._trigger_alert("stt_latency", stt_latency)
                
            elif point == ExtensionPoint.PRE_LLM:
                # Record LLM start
                if request_id in self.active_requests:
                    self.active_requests[request_id]["llm_start"] = current_time
                
            elif point == ExtensionPoint.POST_LLM:
                # Record LLM completion
                if request_id in self.active_requests:
                    req = self.active_requests[request_id]
                    if "llm_start" in req:
                        llm_latency = (current_time - req["llm_start"]).total_seconds() * 1000
                        self.current_metrics["llm_latency"].append(llm_latency)
                        req["stages"].append(("llm", llm_latency))
                        
                        # Check alert threshold
                        if llm_latency > self.alert_thresholds.get("llm_latency_ms", 3000):
                            await self._trigger_alert("llm_latency", llm_latency)
                
            elif point == ExtensionPoint.PRE_TTS:
                # Record TTS start
                if request_id in self.active_requests:
                    self.active_requests[request_id]["tts_start"] = current_time
                
            elif point == ExtensionPoint.POST_TTS:
                # Record TTS completion and finalize request
                if request_id in self.active_requests:
                    req = self.active_requests[request_id]
                    if "tts_start" in req:
                        tts_latency = (current_time - req["tts_start"]).total_seconds() * 1000
                        self.current_metrics["tts_latency"].append(tts_latency)
                        req["stages"].append(("tts", tts_latency))
                        
                        # Check alert threshold
                        if tts_latency > self.alert_thresholds.get("tts_latency_ms", 2000):
                            await self._trigger_alert("tts_latency", tts_latency)
                    
                    # Calculate total latency
                    total_latency = (current_time - req["start_time"]).total_seconds() * 1000
                    self.current_metrics["total_latency"].append(total_latency)
                    req["total_latency"] = total_latency
                    
                    # Check total latency alert
                    if total_latency > self.alert_thresholds.get("total_latency_ms", 5000):
                        await self._trigger_alert("total_latency", total_latency)
                    
                    # Finalize request
                    self.current_metrics["requests_processed"] += 1
                    self.current_metrics["active_requests"] -= 1
                    
                    # Log detailed request info if enabled
                    if self.enable_detailed_logging:
                        self.logger.info(f"Request completed - Total: {total_latency:.1f}ms, "
                                       f"Stages: {req['stages']}")
                    
                    # Clean up request tracking
                    del self.active_requests[request_id]
                
            elif point == ExtensionPoint.INTERRUPTION_DETECTED:
                # Record interruption
                self.current_metrics["interruption_count"] += 1
                
            elif point == ExtensionPoint.ERROR_OCCURRED:
                # Record error
                self.current_metrics["error_count"] += 1
            
            # Inject current metrics into context
            context.set_data("current_metrics", self._get_current_stats(), ContextScope.REQUEST)
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error in metrics extension point {point.value}: {e}")
            return context
    
    # Event Handlers
    
    async def handle_event(self, event_type: str, data: Any) -> None:
        """Handle custom events"""
        try:
            if event_type == "metrics_request":
                # Respond with current metrics
                response_data = self.get_comprehensive_metrics()
                # Could emit response event here
                
            elif event_type == "reset_metrics":
                await self._reset_metrics()
                
            elif event_type == "export_metrics":
                if self.export_metrics:
                    await self._export_current_metrics()
                
        except Exception as e:
            self.logger.error(f"Error handling event {event_type}: {e}")
    
    # Public Interface Methods
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot"""
        return self._get_current_stats()
    
    def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics including history and statistics"""
        current_stats = self._get_current_stats()
        
        return {
            "current": current_stats,
            "history": self.metrics_history[-10:],  # Last 10 snapshots
            "performance": {
                "uptime_seconds": (datetime.now() - self.performance_stats["uptime_start"]).total_seconds(),
                "alert_count": self.performance_stats["alert_count"],
                "last_alert": self.performance_stats["last_alert"].isoformat() if self.performance_stats["last_alert"] else None
            },
            "thresholds": self.alert_thresholds,
            "active_requests": len(self.active_requests)
        }
    
    def get_latency_percentiles(self, metric_name: str) -> Dict[str, float]:
        """Get latency percentiles for a specific metric"""
        if metric_name not in self.current_metrics or not self.current_metrics[metric_name]:
            return {}
        
        data = self.current_metrics[metric_name]
        if len(data) < 2:
            return {"p50": data[0] if data else 0}
        
        return {
            "p50": statistics.median(data),
            "p90": statistics.quantiles(data, n=10)[8] if len(data) >= 10 else max(data),
            "p95": statistics.quantiles(data, n=20)[18] if len(data) >= 20 else max(data),
            "p99": statistics.quantiles(data, n=100)[98] if len(data) >= 100 else max(data),
            "min": min(data),
            "max": max(data),
            "mean": statistics.mean(data)
        }
    
    # Private Helper Methods
    
    def _get_current_stats(self) -> Dict[str, Any]:
        """Get current statistics snapshot"""
        stats = {
            "timestamp": datetime.now().isoformat(),
            "requests_processed": self.current_metrics["requests_processed"],
            "active_requests": self.current_metrics["active_requests"],
            "interruption_count": self.current_metrics["interruption_count"],
            "error_count": self.current_metrics["error_count"]
        }
        
        # Add latency statistics
        for metric in ["stt_latency", "llm_latency", "tts_latency", "total_latency"]:
            data = self.current_metrics[metric]
            if data:
                stats[f"{metric}_ms"] = {
                    "count": len(data),
                    "mean": statistics.mean(data),
                    "median": statistics.median(data),
                    "min": min(data),
                    "max": max(data)
                }
            else:
                stats[f"{metric}_ms"] = {"count": 0}
        
        return stats
    
    async def _metrics_collection_loop(self) -> None:
        """Background task for periodic metrics collection"""
        while True:
            try:
                await asyncio.sleep(self.collection_interval)
                
                # Take metrics snapshot
                snapshot = self._get_current_stats()
                self.metrics_history.append(snapshot)
                
                # Clean up old history
                cutoff_time = datetime.now() - timedelta(hours=self.history_retention_hours)
                self.metrics_history = [
                    entry for entry in self.metrics_history
                    if datetime.fromisoformat(entry["timestamp"]) > cutoff_time
                ]
                
                # Clean up old latency data (keep only recent samples)
                max_samples = 1000
                for metric in ["stt_latency", "llm_latency", "tts_latency", "total_latency"]:
                    if len(self.current_metrics[metric]) > max_samples:
                        self.current_metrics[metric] = self.current_metrics[metric][-max_samples//2:]
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in metrics collection loop: {e}")
    
    async def _metrics_export_loop(self) -> None:
        """Background task for periodic metrics export"""
        while True:
            try:
                await asyncio.sleep(self.export_interval)
                await self._export_current_metrics()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in metrics export loop: {e}")
    
    async def _export_current_metrics(self) -> None:
        """Export current metrics (placeholder for actual export implementation)"""
        try:
            metrics = self.get_comprehensive_metrics()
            
            # In a real implementation, this could export to:
            # - Prometheus metrics endpoint
            # - InfluxDB time series database
            # - CloudWatch/DataDog
            # - Log files in structured format
            
            self.logger.debug(f"Exported metrics: {metrics['current']['requests_processed']} requests processed")
            
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")
    
    async def _trigger_alert(self, metric_name: str, value: float) -> None:
        """Trigger an alert for threshold violation"""
        try:
            alert_message = f"Performance alert: {metric_name} = {value:.1f}ms exceeds threshold {self.alert_thresholds.get(metric_name, 0)}ms"
            
            self.logger.warning(alert_message)
            self.performance_stats["alert_count"] += 1
            self.performance_stats["last_alert"] = datetime.now()
            
            # In a real implementation, could send notifications via:
            # - Email
            # - Slack/Discord
            # - PagerDuty
            # - Custom webhook
            
        except Exception as e:
            self.logger.error(f"Failed to trigger alert: {e}")
    
    async def _reset_metrics(self) -> None:
        """Reset all metrics counters"""
        self.current_metrics = {
            "stt_latency": [],
            "llm_latency": [],
            "tts_latency": [],
            "total_latency": [],
            "interruption_count": 0,
            "error_count": 0,
            "requests_processed": 0,
            "active_requests": len(self.active_requests)  # Keep current active count
        }
        
        self.performance_stats["uptime_start"] = datetime.now()
        self.performance_stats["alert_count"] = 0
        self.performance_stats["last_alert"] = None
        
        self.logger.info("Metrics reset completed")
    
    def get_interface_version(self) -> Version:
        """Return the version of interface implementations"""
        return Version("1.0.0")