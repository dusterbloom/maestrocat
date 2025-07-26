// state.js - Centralized state management

import { EventEmitter } from './event-emitter.js';

export class StateManager extends EventEmitter {
  constructor() {
    super();
    
    this.state = {
      connection: {
        websocket: false,
        pipeline: false,
        audio: false
      },
      conversation: {
        messages: [],
        currentTranscription: null,
        currentResponse: null
      },
      metrics: {
        current: {
          stt_latency_ms: 0,
          llm_latency_ms: 0,
          tts_latency_ms: 0,
          total_latency_ms: 0
        },
        history: []
      },
      modules: {
        memory: { enabled: false, loaded: false },
        voice_recognition: { enabled: false, loaded: false }
      },
      config: {
        llm: {
          model: 'llama3.2:3b',
          temperature: 0.7,
          max_tokens: 1000,
          top_p: 0.9
        },
        tts: {
          voice: 'af_bella',
          speed: 1.0
        },
        stt: {
          language: 'en',
          vad_threshold: 0.5
        }
      },
      events: {
        paused: false,
        filter: 'all',
        searchQuery: ''
      }
    };
    
    // Create a proxy to track state changes
    this.state = this.createReactiveState(this.state);
  }
  
  createReactiveState(obj, path = []) {
    const self = this;
    
    return new Proxy(obj, {
      get(target, property) {
        const value = target[property];
        if (value !== null && typeof value === 'object') {
          return self.createReactiveState(value, [...path, property]);
        }
        return value;
      },
      
      set(target, property, value) {
        const oldValue = target[property];
        target[property] = value;
        
        // Emit change event
        const fullPath = [...path, property].join('.');
        self.emit('change', {
          path: fullPath,
          oldValue,
          newValue: value
        });
        
        // Emit specific event for the path
        self.emit(`change:${fullPath}`, value, oldValue);
        
        return true;
      }
    });
  }
  
  get(path) {
    const keys = path.split('.');
    let value = this.state;
    
    for (const key of keys) {
      if (value && typeof value === 'object' && key in value) {
        value = value[key];
      } else {
        return undefined;
      }
    }
    
    return value;
  }
  
  set(path, value) {
    const keys = path.split('.');
    const lastKey = keys.pop();
    let target = this.state;
    
    for (const key of keys) {
      if (!target[key] || typeof target[key] !== 'object') {
        target[key] = {};
      }
      target = target[key];
    }
    
    target[lastKey] = value;
  }
  
  update(path, updater) {
    const currentValue = this.get(path);
    const newValue = updater(currentValue);
    this.set(path, newValue);
  }
  
  // Conversation methods
  addMessage(role, content, metadata = {}) {
    const message = {
      id: Date.now(),
      role,
      content,
      timestamp: new Date().toISOString(),
      ...metadata
    };
    
    this.state.conversation.messages.push(message);
    this.emit('message:added', message);
    
    return message;
  }
  
  getConversationHistory() {
    return [...this.state.conversation.messages];
  }
  
  clearConversation() {
    this.state.conversation.messages = [];
    this.state.conversation.currentTranscription = null;
    this.state.conversation.currentResponse = null;
    this.emit('conversation:cleared');
  }
  
  // Metrics methods
  updateMetrics(metrics) {
    Object.assign(this.state.metrics.current, metrics);
    
    // Add to history with timestamp
    this.state.metrics.history.push({
      timestamp: Date.now(),
      ...metrics
    });
    
    // Keep only last 100 entries
    if (this.state.metrics.history.length > 100) {
      this.state.metrics.history.shift();
    }
    
    this.emit('metrics:updated', metrics);
  }
  
  getMetricsHistory(limit = 100) {
    const history = this.state.metrics.history;
    return history.slice(-limit);
  }
  
  // Module methods
  updateModuleStatus(moduleName, status) {
    const normalizedName = moduleName.toLowerCase().replace(/\s+/g, '_');
    if (this.state.modules[normalizedName]) {
      Object.assign(this.state.modules[normalizedName], status);
      this.emit('module:updated', normalizedName, status);
    }
  }
  
  // Event processing
  processEvent(event) {
    // Update state based on event type
    switch (event.type) {
      case 'connection_status':
        this.state.connection[event.data.service] = event.data.connected;
        break;
        
      case 'config_loaded':
        Object.assign(this.state.config, event.data);
        break;
        
      case 'module_state':
        this.updateModuleStatus(event.data.name, event.data.state);
        break;
    }
  }
  
  // Export state for debugging
  exportState() {
    return JSON.parse(JSON.stringify(this.state));
  }
  
  // Import state (for testing or recovery)
  importState(newState) {
    Object.assign(this.state, newState);
    this.emit('state:imported', newState);
  }
}