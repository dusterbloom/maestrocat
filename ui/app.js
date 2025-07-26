// app.js - Main application entry point

import { WebSocketManager } from './modules/websocket.js';
import { AudioManager } from './modules/audio.js';
import { UIManager } from './modules/ui.js';
import { TranscriptionManager } from './modules/transcription.js';
import { MetricsManager } from './modules/metrics.js';
import { ConfigManager } from './modules/config.js';
import { ShortcutsManager } from './modules/shortcuts.js';
import { CommandPalette } from './modules/command-palette.js';
import { EventManager } from './modules/events.js';
import { StateManager } from './modules/state.js';

class MaestroCatDebugApp {
  constructor() {
    // Initialize state management
    this.state = new StateManager();
    
    // Initialize managers
    this.websocket = new WebSocketManager(this.state);
    this.audio = new AudioManager(this.state);
    this.ui = new UIManager(this.state);
    this.transcription = new TranscriptionManager(this.state);
    this.metrics = new MetricsManager(this.state);
    this.config = new ConfigManager(this.state);
    this.shortcuts = new ShortcutsManager(this.state);
    this.commandPalette = new CommandPalette(this.state);
    this.events = new EventManager(this.state);
    
    // Bind managers together
    this.bindManagers();
    
    // Initialize application
    this.init();
  }
  
  bindManagers() {
    // WebSocket events
    this.websocket.on('connected', () => {
      this.ui.updateConnectionStatus('ws', true);
      this.ui.showToast('Connected to MaestroCat', 'success');
    });
    
    this.websocket.on('disconnected', () => {
      this.ui.updateConnectionStatus('ws', false);
      this.ui.showToast('Disconnected from MaestroCat', 'error');
    });
    
    this.websocket.on('message', (data) => {
      this.handleMessage(data);
    });
    
    // Audio events
    this.audio.on('connected', () => {
      this.ui.updateConnectionStatus('pipeline', true);
      this.transcription.setLive(true);
    });
    
    this.audio.on('disconnected', () => {
      this.ui.updateConnectionStatus('pipeline', false);
      this.transcription.setLive(false);
    });
    
    this.audio.on('audio_data', (data) => {
      // Audio data is sent directly through WebSocket
    });
    
    // Config changes
    this.config.on('change', (component, settings) => {
      this.websocket.sendConfigUpdate(component, settings);
    });
    
    // Command palette commands
    this.commandPalette.on('command', (command) => {
      this.executeCommand(command);
    });
    
    // Keyboard shortcuts
    this.shortcuts.on('shortcut', (action) => {
      this.executeShortcut(action);
    });
  }
  
  handleMessage(data) {
    switch(data.type) {
      case 'event':
        this.handleEvent(data.event);
        break;
        
      case 'initial_state':
        this.handleInitialState(data);
        break;
        
      case 'event_history':
        this.events.addBatch(data.events);
        break;
        
      case 'metrics':
        this.metrics.update(data.metrics);
        break;
    }
  }
  
  handleEvent(event) {
    // Add to event stream
    this.events.add(event);
    
    // Update state
    this.state.processEvent(event);
    
    // Handle specific event types
    switch(event.type) {
      case 'transcription_partial':
        this.transcription.updatePartial(event.data);
        break;
        
      case 'transcription_final':
        this.transcription.finalize(event.data);
        this.ui.addMessage('user', event.data.text);
        break;
        
      case 'llm_response_start':
        this.ui.startAssistantMessage();
        break;
        
      case 'llm_response_chunk':
        this.ui.updateAssistantMessage(event.data.chunk);
        break;
        
      case 'llm_response_complete':
        this.ui.finalizeAssistantMessage(event.data.text);
        break;
        
      case 'metrics_update':
        this.metrics.update(event.data);
        break;
        
      case 'module_loaded':
      case 'module_unloaded':
        this.ui.updateModuleStatus(event.data.name, event.type === 'module_loaded');
        break;
        
      case 'error':
        this.ui.showToast(`Error: ${event.data.message}`, 'error');
        break;
        
      case 'interruption_detected':
        this.transcription.handleInterruption();
        this.audio.stopAllAudio();
        break;
    }
  }
  
  handleInitialState(state) {
    // Update configuration UI
    if (state.config) {
      this.config.loadState(state.config);
    }
    
    // Replay recent events
    if (state.event_history) {
      state.event_history.forEach(event => this.handleEvent(event));
    }
    
    // Update metrics
    if (state.metrics_history && state.metrics_history.length > 0) {
      const latestMetrics = state.metrics_history[state.metrics_history.length - 1];
      this.metrics.update(latestMetrics.data);
    }
  }
  
  executeCommand(command) {
    switch(command.id) {
      case 'toggle-audio':
        this.audio.toggle();
        break;
        
      case 'clear-conversation':
        this.ui.clearConversation();
        break;
        
      case 'export-conversation':
        this.exportConversation();
        break;
        
      case 'toggle-event-stream':
        this.events.togglePause();
        break;
        
      case 'reload-config':
        this.config.reload();
        break;
        
      case 'switch-preset':
        this.config.switchPreset(command.value);
        break;
        
      default:
        console.warn('Unknown command:', command.id);
    }
  }
  
  executeShortcut(action) {
    switch(action) {
      case 'command-palette':
        this.commandPalette.toggle();
        break;
        
      case 'toggle-audio':
        this.audio.toggle();
        break;
        
      case 'clear-events':
        this.events.clear();
        break;
        
      case 'export-logs':
        this.exportLogs();
        break;
    }
  }
  
  exportConversation() {
    const conversation = this.state.getConversationHistory();
    const blob = new Blob([JSON.stringify(conversation, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `maestrocat-conversation-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    this.ui.showToast('Conversation exported', 'success');
  }
  
  exportLogs() {
    const logs = {
      events: this.events.getAll(),
      metrics: this.metrics.getHistory(),
      conversation: this.state.getConversationHistory(),
      config: this.config.getState()
    };
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `maestrocat-debug-logs-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    this.ui.showToast('Debug logs exported', 'success');
  }
  
  async init() {
    console.log('Initializing MaestroCat Debug UI...');
    
    // Initialize all managers
    await this.ui.init();
    await this.config.init();
    await this.shortcuts.init();
    await this.commandPalette.init();
    await this.events.init();
    await this.transcription.init();
    await this.metrics.init();
    
    // Connect to WebSocket
    await this.websocket.connect();
    
    // Initialize audio (but don't connect yet)
    await this.audio.init();
    
    console.log('MaestroCat Debug UI initialized');
  }
}

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.maestroCatApp = new MaestroCatDebugApp();
});