# maestrocat/apps/debug_ui.py
"""
FastAPI-based debug UI server for MaestroCat
Provides real-time monitoring and configuration
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from processors import EventEmitter
from utils import MaestroCatConfig

logger = logging.getLogger(__name__)

app = FastAPI(title="MaestroCat Debug UI")


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                # Connection might be closed
                pass


manager = ConnectionManager()


class ConfigUpdate(BaseModel):
    """Configuration update request"""
    component: str
    settings: Dict[str, Any]


class DebugUIServer:
    """Debug UI server that integrates with MaestroCat pipeline"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.event_emitter: Optional[EventEmitter] = None
        self.config: Optional[MaestroCatConfig] = None
        self.metrics_history = []
        self.event_history = []
        
    def attach_event_emitter(self, event_emitter: EventEmitter):
        """Attach to pipeline's event emitter"""
        self.event_emitter = event_emitter
        
        # Subscribe to all events
        self.event_emitter.subscribe("*", self._handle_event)
        
    def attach_config(self, config: MaestroCatConfig):
        """Attach configuration"""
        self.config = config
        
    async def _handle_event(self, event: dict):
        """Handle events from the pipeline"""
        # Store in history
        self.event_history.append(event)
        if len(self.event_history) > 1000:
            self.event_history.pop(0)
            
        # Special handling for metrics
        if event["type"] == "metrics_update":
            self.metrics_history.append({
                "timestamp": event["timestamp"],
                "data": event["data"]
            })
            
        # Broadcast to connected clients
        await manager.broadcast({
            "type": "event",
            "event": event
        })
        
    async def start(self):
        """Start the debug UI server"""
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


# Global instance
debug_server = DebugUIServer()


@app.get("/")
async def root():
    """Serve the debug UI HTML"""
    return HTMLResponse(content=debug_ui_html, status_code=200)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "initial_state",
            "config": debug_server.config.to_dict() if debug_server.config else {},
            "event_history": debug_server.event_history[-100:],  # Last 100 events
            "metrics_history": debug_server.metrics_history[-50:]  # Last 50 metrics
        })
        
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "config_update":
                # Handle configuration updates
                component = data.get("component")
                settings = data.get("settings")
                
                # Emit configuration change event
                if debug_server.event_emitter:
                    await debug_server.event_emitter.emit(
                        "config_change",
                        {
                            "component": component,
                            "settings": settings
                        }
                    )
                    
            elif message_type == "get_events":
                # Send event history
                since = data.get("since", 0)
                events = [e for e in debug_server.event_history if e["timestamp"] > since]
                await websocket.send_json({
                    "type": "event_history",
                    "events": events
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/metrics")
async def get_metrics():
    """Get current metrics"""
    if debug_server.metrics_history:
        return debug_server.metrics_history[-1]
    return {}


@app.get("/api/config")
async def get_config():
    """Get current configuration"""
    if debug_server.config:
        return debug_server.config.to_dict()
    return {}


@app.post("/api/config/{component}")
async def update_config(component: str, update: ConfigUpdate):
    """Update component configuration"""
    if debug_server.event_emitter:
        await debug_server.event_emitter.emit(
            "config_change",
            {
                "component": component,
                "settings": update.settings
            }
        )
    return {"status": "ok"}


# Simple HTML UI (in production, use React app from ui/ folder)
debug_ui_html = """
<!DOCTYPE html>
<html>
<head>
    <title>MaestroCat Debug UI</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #1a1a1a;
            color: #fff;
        }
        .container {
            display: grid;
            grid-template-columns: 200px 1fr 300px;
            grid-template-rows: 150px 1fr 200px;
            gap: 20px;
            height: calc(100vh - 40px);
        }
        .panel {
            background: #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            overflow: auto;
        }
        .pipeline-viz {
            grid-column: 2;
            grid-row: 1;
        }
        .modules {
            grid-column: 1;
            grid-row: 1 / 3;
        }
        .conversation {
            grid-column: 2;
            grid-row: 2;
        }
        .config {
            grid-column: 3;
            grid-row: 1 / 3;
        }
        .events {
            grid-column: 1 / 4;
            grid-row: 3;
        }
        .metric {
            display: inline-block;
            margin: 10px;
            padding: 10px;
            background: #3a3a3a;
            border-radius: 4px;
        }
        .message {
            margin: 10px 0;
            padding: 10px;
            border-radius: 4px;
        }
        .user-message {
            background: #4a4a4a;
            text-align: right;
        }
        .assistant-message {
            background: #3a3a3a;
        }
        .event-item {
            font-size: 12px;
            margin: 2px 0;
            padding: 4px;
            background: #3a3a3a;
            border-radius: 2px;
        }
        input, select {
            width: 100%;
            padding: 8px;
            margin: 4px 0;
            background: #3a3a3a;
            border: 1px solid #4a4a4a;
            color: #fff;
            border-radius: 4px;
        }
        .status {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 5px;
        }
        .status.active { background: #4CAF50; }
        .status.inactive { background: #f44336; }
    </style>
</head>
<body>
    <div class="container">
        <div class="panel pipeline-viz">
            <h3>Pipeline Flow</h3>
            <div id="pipeline">
                <div class="metric">STT: <span id="stt-latency">-</span>ms</div>
                <div class="metric">LLM: <span id="llm-latency">-</span>ms</div>
                <div class="metric">TTS: <span id="tts-latency">-</span>ms</div>
                <div class="metric">Total: <span id="total-latency">-</span>ms</div>
            </div>
        </div>
        
        <div class="panel modules">
            <h3>Modules</h3>
            <div id="module-list">
                <div><span class="status inactive"></span>Voice Recognition</div>
                <div><span class="status inactive"></span>Memory</div>
            </div>
        </div>
        
        <div class="panel conversation">
            <h3>Conversation</h3>
            <div id="conversation-view"></div>
        </div>
        
        <div class="panel config">
            <h3>Configuration</h3>
            <h4>LLM</h4>
            <label>Temperature</label>
            <input type="range" id="llm-temp" min="0" max="2" step="0.1" value="0.7">
            <label>Model</label>
            <select id="llm-model">
                <option value="llama3.2:3b">Llama 3.2 3B</option>
                <option value="llama3.2:7b">Llama 3.2 7B</option>
            </select>
            
            <h4>TTS</h4>
            <label>Speed</label>
            <input type="range" id="tts-speed" min="0.5" max="2" step="0.1" value="1">
            
            <h4>Presets</h4>
            <select id="preset-select">
                <option value="default">Default</option>
                <option value="low_latency">Low Latency</option>
                <option value="high_quality">High Quality</option>
            </select>
        </div>
        
        <div class="panel events">
            <h3>Event Log</h3>
            <div id="event-log"></div>
        </div>
    </div>
    
    <script>
        let ws = null;
        
        function connect() {
            ws = new WebSocket('ws://localhost:8080/ws');
            
            ws.onopen = () => {
                console.log('Connected to MaestroCat Debug UI');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };
            
            ws.onclose = () => {
                console.log('Disconnected. Reconnecting...');
                setTimeout(connect, 1000);
            };
        }
        
        function handleMessage(data) {
            switch(data.type) {
                case 'event':
                    handleEvent(data.event);
                    break;
                case 'initial_state':
                    updateUI(data);
                    break;
            }
        }
        
        function handleEvent(event) {
            // Update event log
            const eventLog = document.getElementById('event-log');
            const eventItem = document.createElement('div');
            eventItem.className = 'event-item';
            eventItem.textContent = `[${new Date(event.timestamp * 1000).toLocaleTimeString()}] ${event.type}: ${JSON.stringify(event.data)}`;
            eventLog.appendChild(eventItem);
            
            // Keep only last 100 events
            while (eventLog.children.length > 100) {
                eventLog.removeChild(eventLog.firstChild);
            }
            
            // Scroll to bottom
            eventLog.scrollTop = eventLog.scrollHeight;
            
            // Handle specific event types
            switch(event.type) {
                case 'metrics_update':
                    updateMetrics(event.data);
                    break;
                case 'transcription_final':
                    addMessage('user', event.data.text);
                    break;
                case 'llm_response_complete':
                    addMessage('assistant', event.data.text);
                    break;
                case 'module_loaded':
                    updateModuleStatus(event.data.name, true);
                    break;
            }
        }
        
        function updateMetrics(metrics) {
            document.getElementById('stt-latency').textContent = Math.round(metrics.stt_latency_ms || 0);
            document.getElementById('llm-latency').textContent = Math.round(metrics.llm_latency_ms || 0);
            document.getElementById('tts-latency').textContent = Math.round(metrics.tts_latency_ms || 0);
            document.getElementById('total-latency').textContent = Math.round(metrics.total_latency_ms || 0);
        }
        
        function addMessage(speaker, text) {
            const conv = document.getElementById('conversation-view');
            const msg = document.createElement('div');
            msg.className = `message ${speaker}-message`;
            msg.textContent = text;
            conv.appendChild(msg);
            conv.scrollTop = conv.scrollHeight;
        }
        
        function updateModuleStatus(name, active) {
            // Update module status indicators
            const modules = document.getElementById('module-list').children;
            for (let module of modules) {
                if (module.textContent.includes(name)) {
                    const status = module.querySelector('.status');
                    status.className = `status ${active ? 'active' : 'inactive'}`;
                }
            }
        }
        
        function updateUI(state) {
            // Update with initial state
            if (state.config) {
                // Update config UI
            }
            
            // Replay recent events
            state.event_history.forEach(event => handleEvent(event));
        }
        
        // Config change handlers
        document.getElementById('llm-temp').addEventListener('change', (e) => {
            ws.send(JSON.stringify({
                type: 'config_update',
                component: 'llm',
                settings: { temperature: parseFloat(e.target.value) }
            }));
        });
        
        document.getElementById('preset-select').addEventListener('change', (e) => {
            ws.send(JSON.stringify({
                type: 'preset_change',
                preset: e.target.value
            }));
        });
        
        // Connect on load
        connect();
    </script>
</body>
</html>
"""


def main():
    """Run the debug UI server standalone"""
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    
    server = DebugUIServer(port=port)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()