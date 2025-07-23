// script.js

class MaestroCatDebugUI {
  constructor() {
    this.ws = null;
    this.audioWs = null;
    this.mediaRecorder = null;
    this.audioStream = null;
    this.isRecording = false;
    this.connect();
    this.setupEventListeners();
    this.setupAudioButton();
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

  setupAudioButton() {
    // Create an audio control button if it doesn't exist
    const header = document.querySelector('.header');
    if (header && !document.getElementById('audio-control')) {
      const audioButton = document.createElement('button');
      audioButton.id = 'audio-control';
      audioButton.textContent = '🎤 Connect Audio';
      audioButton.style.cssText = `
        background: #4CAF50;
        color: white;
        border: none;
        padding: 10px 15px;
        border-radius: 5px;
        cursor: pointer;
        margin-left: 20px;
      `;
      audioButton.addEventListener('click', () => this.toggleAudio());
      header.appendChild(audioButton);
    }
  }

  async toggleAudio() {
    const button = document.getElementById('audio-control');
    
    if (!this.isRecording) {
      try {
        await this.startAudio();
        button.textContent = '🔴 Stop Audio';
        button.style.background = '#f44336';
        this.updatePipelineStatus(true);
      } catch (error) {
        console.error('Failed to start audio:', error);
        alert('Failed to access microphone: ' + error.message);
      }
    } else {
      this.stopAudio();
      button.textContent = '🎤 Connect Audio';
      button.style.background = '#4CAF50';
      this.updatePipelineStatus(false);
    }
  }

  async startAudio() {
    // Get microphone access
    this.audioStream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true
      } 
    });
    
    // Connect to audio WebSocket
    this.audioWs = new WebSocket(`ws://${window.location.hostname}:8765/ws`);
    this.audioWs.binaryType = 'arraybuffer'; // Important for binary data
    
    this.audioWs.onopen = () => {
      console.log('Connected to audio pipeline');
      this.startRecording();
    };
    
    this.audioWs.onmessage = (event) => {
      console.log('Received message:', event.data);
      // Handle audio responses (TTS audio)
      if (event.data instanceof ArrayBuffer || event.data instanceof Blob) {
        console.log('Received audio data, size:', event.data.size || event.data.byteLength);
        this.playAudioResponse(event.data);
      } else {
        console.log('Received text message:', event.data);
      }
    };
    
    this.audioWs.onclose = () => {
      console.log('Audio WebSocket closed');
      this.updatePipelineStatus(false);
    };
    
    this.audioWs.onerror = (error) => {
      console.error('Audio WebSocket error:', error);
      this.updatePipelineStatus(false);
    };
  }

  startRecording() {
    if (!this.audioStream) return;
    
    // Use Web Audio API to capture raw PCM like WhisperLive Chrome extension
    const audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(this.audioStream);
    
    // Create script processor to capture raw audio (deprecated but still works)
    const bufferSize = 4096; // Same as WhisperLive
    const scriptProcessor = audioContext.createScriptProcessor(bufferSize, 1, 1);
    
    scriptProcessor.onaudioprocess = (event) => {
      if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
        // Get raw PCM data
        const inputData = event.inputBuffer.getChannelData(0);
        
        // Convert float32 to int16 PCM like WhisperLive
        const buffer = new ArrayBuffer(inputData.length * 2);
        const view = new DataView(buffer);
        
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        
        // Send raw PCM binary data
        this.audioWs.send(buffer);
        console.log('Sent audio chunk, size:', buffer.byteLength);
      }
    };
    
    // Connect the audio graph
    source.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);
    
    // Store references for cleanup
    this.audioContext = audioContext;
    this.scriptProcessor = scriptProcessor;
    this.isRecording = true;
  }

  stopAudio() {
    if (this.scriptProcessor) {
      this.scriptProcessor.disconnect();
      this.scriptProcessor = null;
    }
    
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
      this.audioStream = null;
    }
    
    if (this.audioWs) {
      this.audioWs.close();
      this.audioWs = null;
    }
    
    this.isRecording = false;
  }

  async playAudioResponse(audioBlob) {
    try {
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audio.play();
      
      // Clean up URL after playing
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
      };
    } catch (error) {
      console.error('Failed to play audio response:', error);
    }
  }

  updatePipelineStatus(active) {
    const statusElement = document.getElementById('pipeline-status');
    if (statusElement) {
      statusElement.className = `status-dot ${active ? 'status-dot-active' : ''}`;
    }
  }
}

// Initialize the UI when the page loads
document.addEventListener('DOMContentLoaded', () => {
  new MaestroCatDebugUI();
});