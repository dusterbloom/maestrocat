// ui.js - UI management and DOM manipulation

import { EventEmitter } from './event-emitter.js';

export class UIManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.elements = {};
    this.currentAssistantMessage = null;
    this.toastQueue = [];
  }
  
  async init() {
    // Cache DOM elements
    this.elements = {
      // Status indicators
      pipelineStatus: document.getElementById('pipeline-status'),
      wsStatus: document.getElementById('ws-status'),
      
      // Conversation
      conversationView: document.getElementById('conversation-view'),
      clearConversation: document.getElementById('clear-conversation'),
      exportConversation: document.getElementById('export-conversation'),
      
      // Audio control
      audioControl: document.getElementById('audio-control'),
      
      // Toast container
      toastContainer: document.getElementById('toast-container')
    };
    
    // Set up event listeners
    this.setupEventListeners();
    
    // Subscribe to state changes
    this.subscribeToStateChanges();
  }
  
  setupEventListeners() {
    // Clear conversation
    this.elements.clearConversation?.addEventListener('click', () => {
      if (confirm('Clear all conversation history?')) {
        this.clearConversation();
        this.emit('conversation:cleared');
      }
    });
    
    // Export conversation
    this.elements.exportConversation?.addEventListener('click', () => {
      this.emit('conversation:export');
    });
  }
  
  subscribeToStateChanges() {
    // Connection status changes
    this.state.on('change:connection.websocket', (connected) => {
      this.updateConnectionStatus('ws', connected);
    });
    
    this.state.on('change:connection.pipeline', (connected) => {
      this.updateConnectionStatus('pipeline', connected);
    });
    
    // Audio control state
    this.state.on('change:connection.audio', (connected) => {
      this.updateAudioButton(connected);
    });
  }
  
  updateConnectionStatus(type, connected) {
    const element = type === 'ws' ? this.elements.wsStatus : this.elements.pipelineStatus;
    if (element) {
      element.setAttribute('data-status', connected ? 'active' : 'inactive');
    }
  }
  
  updateAudioButton(connected) {
    if (this.elements.audioControl) {
      this.elements.audioControl.setAttribute('data-active', connected.toString());
      const textElement = this.elements.audioControl.querySelector('.audio-control-text');
      if (textElement) {
        textElement.textContent = connected ? 'Disconnect Audio' : 'Connect Audio';
      }
    }
  }
  
  addMessage(role, content, metadata = {}) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}`;
    
    // Add content
    const contentElement = document.createElement('div');
    contentElement.className = 'message-content';
    contentElement.textContent = content;
    messageElement.appendChild(contentElement);
    
    // Add timestamp
    const timestampElement = document.createElement('div');
    timestampElement.className = 'message-timestamp';
    timestampElement.textContent = new Date().toLocaleTimeString();
    messageElement.appendChild(timestampElement);
    
    // Add to conversation
    this.elements.conversationView.appendChild(messageElement);
    this.scrollConversationToBottom();
    
    // Update state
    this.state.addMessage(role, content, metadata);
    
    return messageElement;
  }
  
  startAssistantMessage() {
    // Create a new assistant message element
    const messageElement = document.createElement('div');
    messageElement.className = 'message assistant streaming';
    
    // Add content container
    const contentElement = document.createElement('div');
    contentElement.className = 'message-content';
    messageElement.appendChild(contentElement);
    
    // Add streaming indicator
    const indicator = document.createElement('span');
    indicator.className = 'streaming-indicator';
    contentElement.appendChild(indicator);
    
    // Add to conversation
    this.elements.conversationView.appendChild(messageElement);
    this.scrollConversationToBottom();
    
    // Store reference
    this.currentAssistantMessage = {
      element: messageElement,
      contentElement,
      content: ''
    };
  }
  
  updateAssistantMessage(chunk) {
    if (!this.currentAssistantMessage) {
      this.startAssistantMessage();
    }
    
    // Append chunk to content
    this.currentAssistantMessage.content += chunk;
    
    // Update display with typing effect
    const { contentElement } = this.currentAssistantMessage;
    contentElement.textContent = this.currentAssistantMessage.content;
    
    // Keep cursor at end
    const cursor = contentElement.querySelector('.streaming-indicator');
    if (cursor) {
      contentElement.appendChild(cursor);
    }
    
    this.scrollConversationToBottom();
  }
  
  finalizeAssistantMessage(finalText) {
    if (!this.currentAssistantMessage) {
      // If no streaming message, just add the complete message
      this.addMessage('assistant', finalText);
      return;
    }
    
    const { element, contentElement } = this.currentAssistantMessage;
    
    // Set final text
    contentElement.textContent = finalText || this.currentAssistantMessage.content;
    
    // Remove streaming class and indicator
    element.classList.remove('streaming');
    const indicator = contentElement.querySelector('.streaming-indicator');
    if (indicator) {
      indicator.remove();
    }
    
    // Add timestamp
    const timestampElement = document.createElement('div');
    timestampElement.className = 'message-timestamp';
    timestampElement.textContent = new Date().toLocaleTimeString();
    element.appendChild(timestampElement);
    
    // Update state
    this.state.addMessage('assistant', finalText || this.currentAssistantMessage.content);
    
    // Clear reference
    this.currentAssistantMessage = null;
    
    this.scrollConversationToBottom();
  }
  
  clearConversation() {
    this.elements.conversationView.innerHTML = '';
    this.currentAssistantMessage = null;
    this.state.clearConversation();
  }
  
  scrollConversationToBottom() {
    if (this.elements.conversationView) {
      this.elements.conversationView.scrollTop = this.elements.conversationView.scrollHeight;
    }
  }
  
  updateModuleStatus(moduleName, isActive) {
    const normalizedName = moduleName.toLowerCase().replace(/\s+/g, '-');
    const checkbox = document.getElementById(`module-${normalizedName}`);
    
    if (checkbox) {
      checkbox.checked = isActive;
    }
  }
  
  showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type} animate-fade-in`;
    
    const messageElement = document.createElement('div');
    messageElement.className = 'toast-message';
    messageElement.textContent = message;
    toast.appendChild(messageElement);
    
    // Add to container
    this.elements.toastContainer.appendChild(toast);
    
    // Auto remove
    setTimeout(() => {
      toast.style.animation = 'fadeOut 300ms ease-out';
      setTimeout(() => toast.remove(), 300);
    }, duration);
    
    return toast;
  }
  
  showError(error) {
    console.error(error);
    this.showToast(error.message || 'An error occurred', 'error', 5000);
  }
  
  updateMetricDisplay(metricId, value) {
    const element = document.getElementById(metricId);
    if (element) {
      // Animate the change
      element.style.transition = 'none';
      element.style.transform = 'scale(1.1)';
      element.textContent = Math.round(value);
      
      requestAnimationFrame(() => {
        element.style.transition = 'transform 200ms ease-out';
        element.style.transform = 'scale(1)';
      });
    }
  }
  
  // Get element by ID with null check
  getElement(id) {
    return document.getElementById(id);
  }
  
  // Query selector helper
  query(selector) {
    return document.querySelector(selector);
  }
  
  // Query all helper
  queryAll(selector) {
    return document.querySelectorAll(selector);
  }
}

// Add additional CSS for UI components
const style = document.createElement('style');
style.textContent = `
  .message.streaming .message-content {
    position: relative;
  }
  
  .streaming-indicator {
    display: inline-block;
    width: 8px;
    height: 16px;
    background: var(--color-accent);
    animation: blink 1s infinite;
    margin-left: 2px;
    vertical-align: text-bottom;
  }
  
  @keyframes fadeOut {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(100%); }
  }
  
  .message-content {
    word-wrap: break-word;
    white-space: pre-wrap;
  }
  
  /* Smooth transitions for metrics */
  .metric-value {
    transition: transform 200ms ease-out;
  }
`;
document.head.appendChild(style);