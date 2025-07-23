// script.js

class MaestroCatDebugUI {
  constructor() {
    this.ws = null;
    this.connect();
    this.setupEventListeners();
  }

  connect() {
    // Try to connect to the WebSocket
    this.ws = new WebSocket(`ws://${window.location.hostname}:8080/ws`);
    
    this.ws.onopen = () => {
      console.log('Connected to MaestroCat Debug UI');
      this.updateConnectionStatus(true);
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
    
    this.ws.onclose = () => {
      console.log('Disconnected. Reconnecting...');
      this.updateConnectionStatus(false);
      setTimeout(() => this.connect(), 1000);
    };
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  updateConnectionStatus(connected) {
    const statusDot = document.querySelector('.status-dot-active');
    if (statusDot) {
      statusDot.className = connected ? 'status-dot status-dot-active' : 'status-dot';
    }
  }

  handleMessage(data) {
    switch(data.type) {
      case 'event':
        this.handleEvent(data.event);
        break;
      case 'initial_state':
        this.updateUI(data);
        break;
    }
  }

  handleEvent(event) {
    // Update event log
    const eventLog = document.getElementById('event-log');
    const eventItem = document.createElement('div');
    eventItem.className = 'event-item';
    const timestamp = new Date(event.timestamp * 1000).toLocaleTimeString();
    eventItem.textContent = `[${timestamp}] ${event.type}: ${JSON.stringify(event.data)}`;
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
        this.updateMetrics(event.data);
        break;
      case 'transcription_final':
        this.addMessage('user', event.data.text);
        break;
      case 'llm_response_complete':
        this.addMessage('assistant', event.data.text);
        break;
      case 'module_loaded':
        this.updateModuleStatus(event.data.name, true);
        break;
      case 'module_unloaded':
        this.updateModuleStatus(event.data.name, false);
        break;
    }
  }

  updateMetrics(metrics) {
    document.getElementById('stt-latency').textContent = Math.round(metrics.stt_latency_ms || 0);
    document.getElementById('llm-latency').textContent = Math.round(metrics.llm_latency_ms || 0);
    document.getElementById('tts-latency').textContent = Math.round(metrics.tts_latency_ms || 0);
    document.getElementById('total-latency').textContent = Math.round(metrics.total_latency_ms || 0);
  }

  addMessage(speaker, text) {
    const conv = document.getElementById('conversation-view');
    const msg = document.createElement('div');
    msg.className = `message ${speaker}`;
    msg.textContent = text;
    conv.appendChild(msg);
    conv.scrollTop = conv.scrollHeight;
  }

  updateModuleStatus(name, active) {
    const statusElement = document.getElementById(`module-${name.toLowerCase().replace(' ', '-')}-status`);
    if (statusElement) {
      statusElement.className = `module-status ${active ? 'active' : ''}`;
    }
  }

  updateUI(state) {
    // Update with initial state
    if (state.config) {
      // Update config UI with initial values
      if (state.config.llm) {
        const llmConfig = state.config.llm;
        document.getElementById('llm-model').value = llmConfig.model || 'llama3.2:3b';
        document.getElementById('llm-temp').value = llmConfig.temperature || 0.7;
        document.getElementById('llm-temp-value').textContent = llmConfig.temperature || 0.7;
        document.getElementById('llm-max-tokens').value = llmConfig.max_tokens || 1000;
        document.getElementById('llm-max-tokens-value').textContent = llmConfig.max_tokens || 1000;
      }
      
      if (state.config.tts) {
        const ttsConfig = state.config.tts;
        document.getElementById('tts-voice').value = ttsConfig.voice || 'af_bella';
        document.getElementById('tts-speed').value = ttsConfig.speed || 1.0;
        document.getElementById('tts-speed-value').textContent = ttsConfig.speed || 1.0;
      }
      
      if (state.config.modules) {
        const modulesConfig = state.config.modules;
        document.getElementById('module-voice-recognition-toggle').checked = 
          modulesConfig.voice_recognition?.enabled || false;
        document.getElementById('module-memory-toggle').checked = 
          modulesConfig.memory?.enabled || false;
        
        this.updateModuleStatus('voice recognition', modulesConfig.voice_recognition?.enabled || false);
        this.updateModuleStatus('memory', modulesConfig.memory?.enabled || false);
      }
    }
    
    // Replay recent events
    if (state.event_history) {
      state.event_history.forEach(event => this.handleEvent(event));
    }
  }

  sendConfigUpdate(component, settings) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'config_update',
        component: component,
        settings: settings
      }));
    }
  }

  setupEventListeners() {
    // LLM Configuration
    document.getElementById('llm-temp').addEventListener('input', (e) => {
      const value = parseFloat(e.target.value);
      document.getElementById('llm-temp-value').textContent = value;
      this.sendConfigUpdate('llm', { temperature: value });
    });
    
    document.getElementById('llm-max-tokens').addEventListener('input', (e) => {
      const value = parseInt(e.target.value);
      document.getElementById('llm-max-tokens-value').textContent = value;
      this.sendConfigUpdate('llm', { max_tokens: value });
    });
    
    document.getElementById('llm-model').addEventListener('change', (e) => {
      this.sendConfigUpdate('llm', { model: e.target.value });
    });
    
    // TTS Configuration
    document.getElementById('tts-speed').addEventListener('input', (e) => {
      const value = parseFloat(e.target.value);
      document.getElementById('tts-speed-value').textContent = value;
      this.sendConfigUpdate('tts', { speed: value });
    });
    
    document.getElementById('tts-voice').addEventListener('change', (e) => {
      this.sendConfigUpdate('tts', { voice: e.target.value });
    });
    
    // Module Toggles
    document.getElementById('module-voice-recognition-toggle').addEventListener('change', (e) => {
      this.sendConfigUpdate('modules.voice_recognition', { enabled: e.target.checked });
    });
    
    document.getElementById('module-memory-toggle').addEventListener('change', (e) => {
      this.sendConfigUpdate('modules.memory', { enabled: e.target.checked });
    });
    
    // Presets
    document.getElementById('preset-select').addEventListener('change', (e) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: 'preset_change',
          preset: e.target.value
        }));
      }
    });
  }
}

// Initialize the UI when the page loads
document.addEventListener('DOMContentLoaded', () => {
  new MaestroCatDebugUI();
});