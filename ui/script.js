// script.js

class MaestroCatDebugUI {
  constructor() {
    this.ws = null;
    this.audioWs = null;
    this.mediaRecorder = null;
    this.audioStream = null;
    this.isRecording = false;
    this.audioChunks = []; // Buffer for accumulating audio chunks
    this.audioContext = null;
    this.activeSources = []; // Track active audio sources for cleanup
    this.nextPlayTime = 0; // Track scheduling for seamless playback
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
    
    // Stop all active audio sources
    if (this.activeSources) {
      this.activeSources.forEach(source => {
        try {
          source.stop();
        } catch (e) {
          // Source might already be stopped
        }
      });
      this.activeSources = [];
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

  async playAudioResponse(audioData) {
    try {
      if (audioData instanceof ArrayBuffer) {
        const view = new DataView(audioData);
        const first4Bytes = view.byteLength >= 4 ? 
          String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3)) : '';
        
        console.log('Audio data first 4 bytes:', first4Bytes, 'Size:', view.byteLength);
        
        // Check if it's a WAV file (should start with "RIFF")
        if (first4Bytes === 'RIFF') {
          // Parse WAV header to check format
          const sampleRate = view.getUint32(24, true);
          const bitsPerSample = view.getUint16(34, true);
          const numChannels = view.getUint16(22, true);
          console.log(`WAV format: ${sampleRate}Hz, ${bitsPerSample}-bit, ${numChannels} channel(s)`);
          
          // Play WAV chunk directly using Web Audio API
          await this.playWAVChunk(audioData);
          
        } else {
          console.warn('Received non-WAV audio data, skipping');
        }
      } else if (audioData instanceof Blob) {
        // Convert blob to ArrayBuffer and play
        const arrayBuffer = await audioData.arrayBuffer();
        await this.playWAVChunk(arrayBuffer);
      } else {
        console.error('Unexpected audio data type:', audioData);
      }
    } catch (error) {
      console.error('Failed to play audio response:', error);
    }
  }

  addWavHeader(pcmData, sampleRate, numChannels, bitsPerSample) {
    const dataLength = pcmData.byteLength;
    const header = new ArrayBuffer(44);
    const view = new DataView(header);
    
    // "RIFF" chunk descriptor
    view.setUint32(0, 0x46464952, false); // "RIFF"
    view.setUint32(4, dataLength + 36, true); // file size - 8
    view.setUint32(8, 0x45564157, false); // "WAVE"
    
    // "fmt " sub-chunk
    view.setUint32(12, 0x20746d66, false); // "fmt "
    view.setUint32(16, 16, true); // subchunk size
    view.setUint16(20, 1, true); // audio format (1 = PCM)
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * (bitsPerSample / 8), true); // byte rate
    view.setUint16(32, numChannels * (bitsPerSample / 8), true); // block align
    view.setUint16(34, bitsPerSample, true);
    
    // "data" sub-chunk
    view.setUint32(36, 0x61746164, false); // "data"
    view.setUint32(40, dataLength, true);
    
    // Combine header and PCM data
    const wavData = new Uint8Array(header.byteLength + dataLength);
    wavData.set(new Uint8Array(header), 0);
    wavData.set(new Uint8Array(pcmData), header.byteLength);
    
    return wavData.buffer;
  }

  async playWAVChunk(wavData) {
    try {
      // Initialize AudioContext if needed
      if (!this.audioContext) {
        this.audioContext = new AudioContext({ sampleRate: 24000 });
        this.nextPlayTime = this.audioContext.currentTime;
      }
      
      // Resume context if suspended (required for some browsers)
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }
      
      // Decode WAV data to AudioBuffer
      const audioBuffer = await this.audioContext.decodeAudioData(wavData);
      
      // Create buffer source and connect to output
      const source = this.audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioContext.destination);
      
      // Track active sources for cleanup
      this.activeSources.push(source);
      
      // Remove from active sources when done
      source.onended = () => {
        const index = this.activeSources.indexOf(source);
        if (index > -1) {
          this.activeSources.splice(index, 1);
        }
      };
      
      // Schedule playback for seamless transitions
      const currentTime = this.audioContext.currentTime;
      const startTime = Math.max(currentTime, this.nextPlayTime);
      
      source.start(startTime);
      
      // Update next play time to end of this chunk
      this.nextPlayTime = startTime + audioBuffer.duration;
      
      console.log(`Scheduled WAV chunk at ${startTime.toFixed(3)}s, duration: ${audioBuffer.duration.toFixed(3)}s, next: ${this.nextPlayTime.toFixed(3)}s`);
      
    } catch (error) {
      console.error('Failed to play WAV chunk:', error);
    }
  }

  stopAllAudio() {
    // Stop all currently playing audio sources
    if (this.activeSources) {
      this.activeSources.forEach(source => {
        try {
          source.stop();
        } catch (e) {
          // Source might already be stopped
        }
      });
      this.activeSources = [];
      console.log('Stopped all audio sources for interruption');
    }
    
    // Reset timing for next playback
    if (this.audioContext) {
      this.nextPlayTime = this.audioContext.currentTime;
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