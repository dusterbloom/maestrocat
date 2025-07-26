// audio.js - Audio management for voice input/output

import { EventEmitter } from './event-emitter.js';

export class AudioManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.audioWs = null;
    this.audioStream = null;
    this.audioContext = null;
    this.scriptProcessor = null;
    this.activeSources = [];
    this.nextPlayTime = 0;
    this.isConnected = false;
    this.isRecording = false;
  }
  
  async init() {
    // Set up audio button listener
    const audioButton = document.getElementById('audio-control');
    if (audioButton) {
      audioButton.addEventListener('click', () => this.toggle());
    }
  }
  
  async toggle() {
    if (this.isConnected) {
      await this.disconnect();
    } else {
      await this.connect();
    }
  }
  
  async connect() {
    if (this.isConnected) {
      console.log('Audio already connected');
      return;
    }
    
    try {
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
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = 8765; // Audio pipeline port
      
      this.audioWs = new WebSocket(`${protocol}//${host}:${port}/ws`);
      this.audioWs.binaryType = 'arraybuffer';
      
      this.audioWs.onopen = () => {
        console.log('Connected to audio pipeline');
        this.isConnected = true;
        this.startRecording();
        this.emit('connected');
        this.state.set('connection.audio', true);
      };
      
      this.audioWs.onmessage = (event) => {
        this.handleAudioMessage(event);
      };
      
      this.audioWs.onclose = () => {
        console.log('Audio WebSocket closed');
        this.isConnected = false;
        this.emit('disconnected');
        this.state.set('connection.audio', false);
      };
      
      this.audioWs.onerror = (error) => {
        console.error('Audio WebSocket error:', error);
        this.emit('error', error);
      };
      
    } catch (error) {
      console.error('Failed to connect audio:', error);
      this.emit('error', error);
      throw error;
    }
  }
  
  async disconnect() {
    this.isConnected = false;
    this.isRecording = false;
    
    // Stop recording
    if (this.scriptProcessor) {
      this.scriptProcessor.disconnect();
      this.scriptProcessor = null;
    }
    
    // Stop all audio sources
    this.stopAllAudio();
    
    // Close audio context
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }
    
    // Stop microphone
    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
      this.audioStream = null;
    }
    
    // Close WebSocket
    if (this.audioWs) {
      this.audioWs.close();
      this.audioWs = null;
    }
    
    this.emit('disconnected');
    this.state.set('connection.audio', false);
  }
  
  startRecording() {
    if (!this.audioStream || this.isRecording) return;
    
    try {
      // Create audio context
      this.audioContext = new AudioContext({ sampleRate: 16000 });
      const source = this.audioContext.createMediaStreamSource(this.audioStream);
      
      // Create script processor for raw audio capture
      const bufferSize = 4096;
      this.scriptProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);
      
      this.scriptProcessor.onaudioprocess = (event) => {
        if (this.audioWs && this.audioWs.readyState === WebSocket.OPEN) {
          const inputData = event.inputBuffer.getChannelData(0);
          
          // Convert float32 to int16 PCM
          const buffer = new ArrayBuffer(inputData.length * 2);
          const view = new DataView(buffer);
          
          for (let i = 0; i < inputData.length; i++) {
            const sample = Math.max(-1, Math.min(1, inputData[i]));
            view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
          }
          
          // Send to audio pipeline
          this.audioWs.send(buffer);
          this.emit('audio_data', buffer);
        }
      };
      
      // Connect audio graph
      source.connect(this.scriptProcessor);
      this.scriptProcessor.connect(this.audioContext.destination);
      
      this.isRecording = true;
      console.log('Started audio recording');
      
    } catch (error) {
      console.error('Failed to start recording:', error);
      this.emit('error', error);
    }
  }
  
  handleAudioMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      // Audio response from TTS
      this.playAudioResponse(event.data);
    } else {
      // Text message
      try {
        const data = JSON.parse(event.data);
        console.log('Audio pipeline message:', data);
      } catch (error) {
        console.log('Audio pipeline text:', event.data);
      }
    }
  }
  
  async playAudioResponse(audioData) {
    try {
      // Initialize audio context for playback if needed
      if (!this.audioContext || this.audioContext.state === 'closed') {
        this.audioContext = new AudioContext({ sampleRate: 24000 });
        this.nextPlayTime = this.audioContext.currentTime;
      }
      
      // Resume context if suspended
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }
      
      // Check if it's WAV data
      const view = new DataView(audioData);
      const header = new Uint8Array(audioData, 0, 4);
      const headerStr = String.fromCharCode(...header);
      
      if (headerStr === 'RIFF') {
        // Decode WAV audio
        const audioBuffer = await this.audioContext.decodeAudioData(audioData);
        
        // Create and schedule audio source
        const source = this.audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.audioContext.destination);
        
        // Track for cleanup
        this.activeSources.push(source);
        
        // Remove from active sources when done
        source.onended = () => {
          const index = this.activeSources.indexOf(source);
          if (index > -1) {
            this.activeSources.splice(index, 1);
          }
        };
        
        // Schedule seamless playback
        const currentTime = this.audioContext.currentTime;
        const startTime = Math.max(currentTime, this.nextPlayTime);
        
        source.start(startTime);
        this.nextPlayTime = startTime + audioBuffer.duration;
        
        console.log(`Playing audio chunk: ${audioBuffer.duration.toFixed(3)}s`);
        
      } else {
        console.warn('Received non-WAV audio data');
      }
      
    } catch (error) {
      console.error('Failed to play audio response:', error);
    }
  }
  
  stopAllAudio() {
    // Stop all currently playing audio
    this.activeSources.forEach(source => {
      try {
        source.stop();
      } catch (error) {
        // Source might already be stopped
      }
    });
    this.activeSources = [];
    
    // Reset timing
    if (this.audioContext) {
      this.nextPlayTime = this.audioContext.currentTime;
    }
    
    console.log('Stopped all audio playback');
  }
  
  getState() {
    return {
      connected: this.isConnected,
      recording: this.isRecording,
      activeSources: this.activeSources.length
    };
  }
}