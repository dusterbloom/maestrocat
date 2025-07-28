# core/modules/examples/smart_interruption_module.py
"""
Smart Interruption Module - Example implementation demonstrating advanced interruption handling
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from semantic_version import Version

from ..interface import (
    MaestroCatModule, ModuleMetadata, ExtensionPoint, ModuleCapability
)
from ...context.pipeline_context import PipelineContext, ContextScope


class InterruptionStrategy(Enum):
    """Available interruption handling strategies"""
    IMMEDIATE = "immediate"       # Stop immediately on any interruption
    THRESHOLD = "threshold"       # Stop only after threshold-based evaluation
    CONTEXT_AWARE = "context_aware"  # Consider context and conversation state
    ADAPTIVE = "adaptive"         # Learn from user patterns


class InterruptionReason(Enum):
    """Reasons for interruption"""
    USER_SPEECH = "user_speech"
    URGENT_INPUT = "urgent_input"
    ERROR_RECOVERY = "error_recovery"
    TIMEOUT = "timeout"
    MANUAL = "manual"


class SmartInterruptionModule(MaestroCatModule):
    """
    Smart interruption handling module demonstrating:
    - Multiple interruption strategies
    - Context-aware interruption decisions
    - Learning from user interruption patterns
    - Graceful recovery and continuation
    - Integration with pipeline flow control
    """
    
    @classmethod
    def get_metadata(cls) -> ModuleMetadata:
        """Return module metadata"""
        return ModuleMetadata(
            name="SmartInterruptionModule",
            version=Version("1.3.0"),
            description="Advanced interruption handling with context awareness and learning",
            author="MaestroCat Team",
            capabilities=[
                ModuleCapability.INTERRUPTION_HANDLING,
                ModuleCapability.FLOW_CONTROL,
                ModuleCapability.USER_PROFILING
            ],
            extension_points=[
                ExtensionPoint.INTERRUPTION_DETECTED,
                ExtensionPoint.INTERRUPTION_HANDLED,
                ExtensionPoint.PRE_LLM,
                ExtensionPoint.PRE_TTS,
                ExtensionPoint.POST_TTS
            ],
            dependencies=[],
            config_schema={
                "strategy": {
                    "type": "string",
                    "enum": ["immediate", "threshold", "context_aware", "adaptive"],
                    "default": "context_aware"
                },
                "base_threshold": {"type": "number", "default": 0.3, "minimum": 0.0, "maximum": 1.0},
                "context_weight": {"type": "number", "default": 0.4, "minimum": 0.0, "maximum": 1.0},
                "learning_enabled": {"type": "boolean", "default": True},
                "learning_window_hours": {"type": "integer", "default": 24, "minimum": 1},
                "min_response_length": {"type": "integer", "default": 10, "minimum": 1},
                "urgency_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["stop", "wait", "hold on", "excuse me", "sorry"]
                },
                "continuation_enabled": {"type": "boolean", "default": True},
                "continuation_timeout": {"type": "number", "default": 5.0, "minimum": 1.0}
            }
        )
    
    def __init__(self, context):
        super().__init__(context)
        
        # Configuration
        config = self.config
        self.strategy = InterruptionStrategy(config.get("strategy", "context_aware"))
        self.base_threshold = config.get("base_threshold", 0.3)
        self.context_weight = config.get("context_weight", 0.4)
        self.learning_enabled = config.get("learning_enabled", True)
        self.learning_window_hours = config.get("learning_window_hours", 24)
        self.min_response_length = config.get("min_response_length", 10)
        self.urgency_keywords = config.get("urgency_keywords", ["stop", "wait", "hold on", "excuse me", "sorry"])
        self.continuation_enabled = config.get("continuation_enabled", True)
        self.continuation_timeout = config.get("continuation_timeout", 5.0)
        
        # Interruption tracking
        self.interruption_history: List[Dict[str, Any]] = []
        self.user_patterns: Dict[str, Dict[str, Any]] = {}
        self.current_response_state: Optional[Dict[str, Any]] = None
        
        # Learning data
        self.interruption_outcomes: List[Dict[str, Any]] = []
        self.adaptive_threshold = self.base_threshold
        
        # State management
        self.pending_continuation: Optional[Dict[str, Any]] = None
        self._continuation_task: Optional[asyncio.Task] = None
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate module configuration"""
        errors = []
        
        if "strategy" in config:
            valid_strategies = [s.value for s in InterruptionStrategy]
            if config["strategy"] not in valid_strategies:
                errors.append(f"strategy must be one of: {valid_strategies}")
        
        if "base_threshold" in config:
            if not isinstance(config["base_threshold"], (int, float)) or not 0 <= config["base_threshold"] <= 1:
                errors.append("base_threshold must be a number between 0 and 1")
        
        return errors
    
    async def initialize(self) -> bool:
        """Initialize the interruption module"""
        try:
            self.logger.info(f"Initializing {self.name} with strategy: {self.strategy.value}")
            
            # Initialize user pattern tracking
            if self.learning_enabled:
                await self._initialize_learning_system()
            
            # Reset state
            self.current_response_state = None
            self.pending_continuation = None
            
            self.logger.info(f"Smart interruption module initialized with threshold: {self.base_threshold}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize interruption module: {e}")
            return False
    
    async def start(self) -> bool:
        """Start the interruption module"""
        try:
            self.logger.info("Starting smart interruption handling")
            
            # Start learning background tasks if enabled
            if self.learning_enabled:
                # Could start pattern analysis tasks here
                pass
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start interruption module: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop the interruption module"""
        try:
            self.logger.info("Stopping smart interruption handling")
            
            # Cancel any pending continuation
            if self._continuation_task:
                self._continuation_task.cancel()
                try:
                    await self._continuation_task
                except asyncio.CancelledError:
                    pass
            
            # Save learning data if enabled
            if self.learning_enabled:
                await self._save_learning_data()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop interruption module: {e}")
            return False
    
    # Extension Point Handlers
    
    async def handle_extension_point(
        self, 
        point: ExtensionPoint, 
        context: PipelineContext
    ) -> PipelineContext:
        """Handle pipeline extension points"""
        try:
            if point == ExtensionPoint.INTERRUPTION_DETECTED:
                # Main interruption handling logic
                should_interrupt = await self._evaluate_interruption(context)
                
                if should_interrupt:
                    await self._handle_interruption(context)
                else:
                    # Continue current processing
                    self.logger.debug("Interruption detected but not acting on it")
                
            elif point == ExtensionPoint.INTERRUPTION_HANDLED:
                # Post-interruption processing
                await self._post_interruption_processing(context)
                
            elif point == ExtensionPoint.PRE_LLM:
                # Check for continuation context
                await self._inject_continuation_context(context)
                
            elif point == ExtensionPoint.PRE_TTS:
                # Prepare response state tracking
                await self._prepare_response_tracking(context)
                
            elif point == ExtensionPoint.POST_TTS:
                # Finalize response and prepare for potential interruptions
                await self._finalize_response_tracking(context)
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error in interruption extension point {point.value}: {e}")
            return context
    
    # Event Handlers
    
    async def handle_event(self, event_type: str, data: Any) -> None:
        """Handle custom events"""
        try:
            if event_type == "manual_interruption":
                # Handle manual interruption request
                await self._handle_manual_interruption(data)
                
            elif event_type == "update_interruption_strategy":
                # Update interruption strategy dynamically
                await self._update_strategy(data)
                
            elif event_type == "get_interruption_stats":
                # Provide interruption statistics
                stats = self._get_interruption_statistics()
                # Could emit response event with stats
                
        except Exception as e:
            self.logger.error(f"Error handling event {event_type}: {e}")
    
    # Public Interface Methods
    
    def get_interruption_statistics(self) -> Dict[str, Any]:
        """Get comprehensive interruption statistics"""
        return self._get_interruption_statistics()
    
    async def update_strategy(self, new_strategy: str, **kwargs) -> bool:
        """Update interruption strategy"""
        try:
            if new_strategy in [s.value for s in InterruptionStrategy]:
                self.strategy = InterruptionStrategy(new_strategy)
                
                # Update related parameters
                for key, value in kwargs.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
                
                self.logger.info(f"Updated interruption strategy to: {new_strategy}")
                return True
            else:
                self.logger.error(f"Invalid strategy: {new_strategy}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to update strategy: {e}")
            return False
    
    # Private Helper Methods
    
    async def _evaluate_interruption(self, context: PipelineContext) -> bool:
        """Evaluate whether to act on an interruption"""
        interruption_data = {
            "timestamp": datetime.now(),
            "strategy": self.strategy.value,
            "context": context.get_context_summary()
        }
        
        if self.strategy == InterruptionStrategy.IMMEDIATE:
            decision = True
            reason = "immediate_strategy"
            
        elif self.strategy == InterruptionStrategy.THRESHOLD:
            decision = await self._threshold_based_decision(context)
            reason = "threshold_based"
            
        elif self.strategy == InterruptionStrategy.CONTEXT_AWARE:
            decision = await self._context_aware_decision(context)
            reason = "context_aware"
            
        elif self.strategy == InterruptionStrategy.ADAPTIVE:
            decision = await self._adaptive_decision(context)
            reason = "adaptive"
            
        else:
            decision = True  # Default fallback
            reason = "fallback"
        
        # Record decision for learning
        interruption_data.update({
            "decision": decision,
            "reason": reason,
            "threshold_used": getattr(self, 'last_threshold_used', self.base_threshold)
        })
        
        self.interruption_history.append(interruption_data)
        
        # Clean up old history
        cutoff_time = datetime.now() - timedelta(hours=self.learning_window_hours)
        self.interruption_history = [
            entry for entry in self.interruption_history
            if entry["timestamp"] > cutoff_time
        ]
        
        self.logger.debug(f"Interruption evaluation: {decision} (reason: {reason})")
        return decision
    
    async def _threshold_based_decision(self, context: PipelineContext) -> bool:
        """Make threshold-based interruption decision"""
        # Simple threshold logic (could be enhanced with more sophisticated metrics)
        current_threshold = self.adaptive_threshold if self.learning_enabled else self.base_threshold
        
        # Factors that influence the decision
        response_progress = self._calculate_response_progress(context)
        urgency_score = await self._calculate_urgency_score(context)
        
        # Combined score
        interrupt_score = (1 - response_progress) * 0.6 + urgency_score * 0.4
        
        self.last_threshold_used = current_threshold
        decision = interrupt_score > current_threshold
        
        self.logger.debug(f"Threshold decision: score={interrupt_score:.3f}, threshold={current_threshold:.3f}, decision={decision}")
        return decision
    
    async def _context_aware_decision(self, context: PipelineContext) -> bool:
        """Make context-aware interruption decision"""
        # Get basic threshold decision
        threshold_decision = await self._threshold_based_decision(context)
        
        # Context factors
        conversation_state = self._analyze_conversation_state(context)
        user_history = await self._get_user_interruption_history(context)
        response_importance = self._assess_response_importance(context)
        
        # Context adjustments
        context_score = 0.0
        
        # More likely to interrupt if conversation is casual
        if conversation_state.get("formality", "neutral") == "casual":
            context_score += 0.2
        
        # Less likely to interrupt if response is important
        if response_importance > 0.7:
            context_score -= 0.3
        
        # Consider user's interruption patterns
        if user_history.get("frequent_interrupter", False):
            context_score += 0.1
        
        # Apply context weight
        final_score = (threshold_decision * (1 - self.context_weight) + 
                      (threshold_decision + context_score) * self.context_weight)
        
        decision = final_score > 0.5
        
        self.logger.debug(f"Context-aware decision: base={threshold_decision}, context_adj={context_score:.3f}, final={decision}")
        return decision
    
    async def _adaptive_decision(self, context: PipelineContext) -> bool:
        """Make adaptive interruption decision using learned patterns"""
        # Start with context-aware decision
        base_decision = await self._context_aware_decision(context)
        
        # Apply learned adjustments
        if self.learning_enabled and self.interruption_outcomes:
            # Analyze recent outcomes to adjust threshold
            recent_outcomes = [
                outcome for outcome in self.interruption_outcomes
                if (datetime.now() - outcome["timestamp"]).total_seconds() < 3600  # Last hour
            ]
            
            if recent_outcomes:
                # Calculate success rate of recent interruptions
                success_rate = sum(1 for outcome in recent_outcomes if outcome["was_appropriate"]) / len(recent_outcomes)
                
                # Adjust threshold based on success rate
                if success_rate < 0.5:  # Too many inappropriate interruptions
                    self.adaptive_threshold = min(self.adaptive_threshold + 0.05, 0.9)
                elif success_rate > 0.8:  # Very appropriate interruptions
                    self.adaptive_threshold = max(self.adaptive_threshold - 0.02, 0.1)
        
        self.logger.debug(f"Adaptive decision: base={base_decision}, adaptive_threshold={self.adaptive_threshold:.3f}")
        return base_decision
    
    async def _handle_interruption(self, context: PipelineContext) -> None:
        """Handle the actual interruption"""
        interruption_id = f"int_{int(datetime.now().timestamp())}"
        
        # Store current response state for potential continuation
        if self.continuation_enabled and self.current_response_state:
            self.pending_continuation = {
                "id": interruption_id,
                "timestamp": datetime.now(),
                "response_state": self.current_response_state.copy(),
                "context_snapshot": context.to_dict()
            }
        
        # Set interruption in context
        context.set_interruption(True, f"Smart interruption by {self.name}")
        
        # Record interruption event
        interruption_event = {
            "id": interruption_id,
            "timestamp": datetime.now(),
            "reason": InterruptionReason.USER_SPEECH,
            "strategy": self.strategy.value,
            "continuation_possible": self.pending_continuation is not None
        }
        
        context.add_event("interruption_handled", interruption_event)
        
        self.logger.info(f"Interruption handled: {interruption_id}")
        
        # Start continuation timeout if enabled
        if self.continuation_enabled and self.pending_continuation:
            self._continuation_task = asyncio.create_task(
                self._continuation_timeout_handler(interruption_id)
            )
    
    async def _post_interruption_processing(self, context: PipelineContext) -> None:
        """Process after interruption has been handled"""
        # Check if user wants to continue the interrupted response
        if context.current_transcription and self.pending_continuation:
            user_input = context.current_transcription.text.lower()
            
            # Simple continuation detection (could be enhanced with NLP)
            continuation_phrases = ["continue", "go on", "keep going", "finish", "what were you saying"]
            
            if any(phrase in user_input for phrase in continuation_phrases):
                await self._trigger_continuation(context)
            else:
                # User doesn't want continuation, clear it
                self.pending_continuation = None
                if self._continuation_task:
                    self._continuation_task.cancel()
    
    async def _trigger_continuation(self, context: PipelineContext) -> None:
        """Trigger continuation of interrupted response"""
        if not self.pending_continuation:
            return
        
        try:
            # Restore previous context
            continuation_data = self.pending_continuation
            
            # Inject continuation context
            context.set_data("continuation_requested", True, ContextScope.REQUEST)
            context.set_data("continuation_data", continuation_data, ContextScope.REQUEST)
            
            self.logger.info(f"Triggering continuation for interruption: {continuation_data['id']}")
            
            # Clear pending continuation
            self.pending_continuation = None
            if self._continuation_task:
                self._continuation_task.cancel()
            
        except Exception as e:
            self.logger.error(f"Failed to trigger continuation: {e}")
    
    async def _continuation_timeout_handler(self, interruption_id: str) -> None:
        """Handle continuation timeout"""
        try:
            await asyncio.sleep(self.continuation_timeout)
            
            # If continuation is still pending, clear it
            if self.pending_continuation and self.pending_continuation["id"] == interruption_id:
                self.logger.debug(f"Continuation timeout for interruption: {interruption_id}")
                self.pending_continuation = None
            
        except asyncio.CancelledError:
            pass  # Task was cancelled, which is expected
    
    def _calculate_response_progress(self, context: PipelineContext) -> float:
        """Calculate how much of the current response has been delivered"""
        if not self.current_response_state:
            return 0.0
        
        # Simple progress calculation based on response length
        # In a real implementation, this could track actual audio delivery
        total_length = self.current_response_state.get("total_length", 1)
        delivered_length = self.current_response_state.get("delivered_length", 0)
        
        return min(delivered_length / total_length, 1.0)
    
    async def _calculate_urgency_score(self, context: PipelineContext) -> float:
        """Calculate urgency score based on user input"""
        if not context.current_transcription:
            return 0.0
        
        user_input = context.current_transcription.text.lower()
        urgency_score = 0.0
        
        # Check for urgency keywords
        for keyword in self.urgency_keywords:
            if keyword in user_input:
                urgency_score += 0.3
        
        # Check input characteristics
        if len(user_input.split()) <= 3:  # Short inputs often urgent
            urgency_score += 0.2
        
        if "!" in context.current_transcription.text:  # Exclamation marks
            urgency_score += 0.2
        
        return min(urgency_score, 1.0)
    
    def _analyze_conversation_state(self, context: PipelineContext) -> Dict[str, Any]:
        """Analyze current conversation state"""
        # Simple conversation analysis
        recent_messages = context.get_recent_messages(5)
        
        if not recent_messages:
            return {"formality": "neutral", "topic": "unknown"}
        
        # Analyze formality (very simple heuristic)
        recent_text = " ".join([msg.content for msg in recent_messages]).lower()
        formal_indicators = ["please", "thank you", "could you", "would you"]
        casual_indicators = ["yeah", "ok", "sure", "cool"]
        
        formal_count = sum(1 for indicator in formal_indicators if indicator in recent_text)
        casual_count = sum(1 for indicator in casual_indicators if indicator in recent_text)
        
        if formal_count > casual_count:
            formality = "formal"
        elif casual_count > formal_count:
            formality = "casual"
        else:
            formality = "neutral"
        
        return {
            "formality": formality,
            "message_count": len(recent_messages),
            "topic": "general"  # Could implement topic detection
        }
    
    async def _get_user_interruption_history(self, context: PipelineContext) -> Dict[str, Any]:
        """Get user's interruption history and patterns"""
        # Simple user pattern analysis
        speaker_id = "default"
        if context.current_transcription and hasattr(context.current_transcription, 'speaker_id'):
            speaker_id = context.current_transcription.speaker_id or "default"
        
        if speaker_id not in self.user_patterns:
            self.user_patterns[speaker_id] = {
                "interruption_count": 0,
                "last_interruption": None,
                "frequent_interrupter": False
            }
        
        pattern = self.user_patterns[speaker_id]
        
        # Update pattern
        pattern["interruption_count"] += 1
        pattern["last_interruption"] = datetime.now()
        pattern["frequent_interrupter"] = pattern["interruption_count"] > 5
        
        return pattern
    
    def _assess_response_importance(self, context: PipelineContext) -> float:
        """Assess importance of current response"""
        if not context.current_llm_response:
            return 0.5  # Default importance
        
        response_text = context.current_llm_response.text
        
        # Simple importance heuristics
        importance = 0.5
        
        # Longer responses might be more important
        if len(response_text) > 200:
            importance += 0.2
        
        # Responses with numbers/data might be important
        if any(char.isdigit() for char in response_text):
            importance += 0.1
        
        # Responses with question marks might be important
        if "?" in response_text:
            importance += 0.1
        
        return min(importance, 1.0)
    
    async def _prepare_response_tracking(self, context: PipelineContext) -> None:
        """Prepare to track response delivery"""
        if context.current_llm_response:
            self.current_response_state = {
                "start_time": datetime.now(),
                "total_length": len(context.current_llm_response.text),
                "delivered_length": 0,
                "response_text": context.current_llm_response.text
            }
    
    async def _finalize_response_tracking(self, context: PipelineContext) -> None:
        """Finalize response tracking"""
        if self.current_response_state:
            self.current_response_state["end_time"] = datetime.now()
            self.current_response_state["delivered_length"] = self.current_response_state["total_length"]
            
            # Record completion for learning
            if self.learning_enabled:
                outcome = {
                    "timestamp": datetime.now(),
                    "completed": True,
                    "interrupted": False,
                    "response_length": self.current_response_state["total_length"],
                    "was_appropriate": True  # Could be determined by user feedback
                }
                self.interruption_outcomes.append(outcome)
        
        # Reset state
        self.current_response_state = None
    
    async def _initialize_learning_system(self) -> None:
        """Initialize learning system"""
        self.logger.info("Initializing interruption learning system")
        # Could load previous learning data here
    
    async def _save_learning_data(self) -> None:
        """Save learning data"""
        # Could save interruption patterns and outcomes to persistent storage
        self.logger.debug("Saving interruption learning data")
    
    def _get_interruption_statistics(self) -> Dict[str, Any]:
        """Get comprehensive interruption statistics"""
        total_interruptions = len(self.interruption_history)
        
        if total_interruptions == 0:
            return {"total_interruptions": 0}
        
        # Calculate statistics
        recent_interruptions = [
            entry for entry in self.interruption_history
            if (datetime.now() - entry["timestamp"]).total_seconds() < 3600  # Last hour
        ]
        
        strategy_breakdown = {}
        for entry in self.interruption_history:
            strategy = entry.get("strategy", "unknown")
            if strategy not in strategy_breakdown:
                strategy_breakdown[strategy] = 0
            strategy_breakdown[strategy] += 1
        
        return {
            "total_interruptions": total_interruptions,
            "recent_interruptions": len(recent_interruptions),
            "strategy_breakdown": strategy_breakdown,
            "current_strategy": self.strategy.value,
            "adaptive_threshold": getattr(self, 'adaptive_threshold', self.base_threshold),
            "user_patterns": len(self.user_patterns),
            "continuation_enabled": self.continuation_enabled,
            "pending_continuation": self.pending_continuation is not None
        }
    
    async def _handle_manual_interruption(self, data: Any) -> None:
        """Handle manual interruption request"""
        self.logger.info("Manual interruption requested")
        # Could implement manual interruption logic here
    
    async def _update_strategy(self, data: Any) -> None:
        """Update interruption strategy from event"""
        if isinstance(data, dict) and "strategy" in data:
            await self.update_strategy(data["strategy"], **data.get("params", {}))
    
    async def _inject_continuation_context(self, context: PipelineContext) -> None:
        """Inject continuation context before LLM"""
        if context.get_data("continuation_requested", scope=ContextScope.REQUEST):
            continuation_data = context.get_data("continuation_data", scope=ContextScope.REQUEST)
            if continuation_data:
                # Add continuation instruction to LLM context
                context.set_data("llm_instruction", 
                    "Continue your previous response that was interrupted.", 
                    ContextScope.REQUEST)
    
    def get_interface_version(self) -> Version:
        """Return the version of interface implementations"""
        return Version("1.0.0")