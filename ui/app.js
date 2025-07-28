// app.js - Main application entry point

import { WebSocketManager } from './modules/websocket.js';
import { AudioManager } from './modules/audio.js';
import { UIManager } from './modules/ui.js';
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
    });
    
    this.audio.on('disconnected', () => {
      this.ui.updateConnectionStatus('pipeline', false);
    });
    
    this.audio.on('audio_data', (data) => {
      // Audio data is sent directly through WebSocket
    });
    
    // Config changes
    this.config.on('change', (component, settings) => {
      this.websocket.sendConfigUpdate(component, settings);
    });
    
    // UI events
    this.ui.on('conversation:export', () => {
      this.exportConversation();
    });
    
    this.ui.on('metrics:export', () => {
      this.exportMetrics();
    });
    
    this.ui.on('metrics:clear', () => {
      this.clearMetrics();
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
        // No longer displaying partial transcriptions
        break;
        
      case 'transcription_final':
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
        
      case 'turn_metrics':
        // NEW: Handle turn-based metrics for developer insights
        this.state.updateTurnMetrics(event.data);
        this.ui.updateTurnMetrics(event.data);
        this.ui.showToast(`Turn ${event.data.turn_id} completed: ${Math.round(event.data.total_latency_ms)}ms total`, 'info');
        break;
        
      case 'module_loaded':
      case 'module_unloaded':
        this.ui.updateModuleStatus(event.data.name, event.type === 'module_loaded');
        break;
        
      case 'error':
        this.ui.showToast(`Error: ${event.data.message}`, 'error');
        break;
        
      case 'interruption_detected':
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
        
      case 'export-metrics':
        this.exportMetrics();
        break;
        
      case 'clear-metrics':
        this.clearMetrics();
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
  
  exportMetrics() {
    const metricsHistory = this.metrics.getHistory();
    const csvData = this.convertMetricsToCSV(metricsHistory);
    
    // Export as CSV for easy analysis
    const csvBlob = new Blob([csvData], { type: 'text/csv' });
    const csvUrl = URL.createObjectURL(csvBlob);
    const csvLink = document.createElement('a');
    csvLink.href = csvUrl;
    csvLink.download = `maestrocat-metrics-${Date.now()}.csv`;
    csvLink.click();
    URL.revokeObjectURL(csvUrl);
    
    // Also export as JSON for full data
    const jsonBlob = new Blob([JSON.stringify(metricsHistory, null, 2)], { type: 'application/json' });
    const jsonUrl = URL.createObjectURL(jsonBlob);
    const jsonLink = document.createElement('a');
    jsonLink.href = jsonUrl;
    jsonLink.download = `maestrocat-metrics-${Date.now()}.json`;
    jsonLink.click();
    URL.revokeObjectURL(jsonUrl);
    
    this.ui.showToast(`Metrics exported (${metricsHistory.length} records)`, 'success');
  }
  
  convertMetricsToCSV(metricsHistory) {
    if (metricsHistory.length === 0) {
      return 'timestamp,component,stt_latency_ms,llm_latency_ms,tts_latency_ms,total_latency_ms\n';
    }
    
    const headers = 'timestamp,component,stt_latency_ms,llm_latency_ms,tts_latency_ms,total_latency_ms,date_time\n';
    const rows = metricsHistory.map(record => {
      const data = record.data || record;
      const timestamp = data.timestamp || Date.now() / 1000;
      const dateTime = new Date(timestamp * 1000).toISOString();
      
      return [
        timestamp,
        data.component || 'unknown',
        data.stt_latency_ms || 0,
        data.llm_latency_ms || 0,
        data.tts_latency_ms || 0,
        data.total_latency_ms || 0,
        dateTime
      ].join(',');
    }).join('\n');
    
    return headers + rows;
  }
  
  clearMetrics() {
    this.metrics.clear();
    this.ui.showToast('Metrics cleared', 'success');
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