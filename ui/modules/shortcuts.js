// shortcuts.js - Keyboard shortcuts management

import { EventEmitter } from './event-emitter.js';

export class ShortcutsManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.shortcuts = new Map();
    this.activeKeys = new Set();
    this.enabled = true;
  }
  
  async init() {
    // Define default shortcuts
    this.registerDefaults();
    
    // Set up keyboard listeners
    this.setupListeners();
    
    // Add help text to UI
    this.addHelpText();
  }
  
  registerDefaults() {
    // Command palette
    this.register(['cmd+k', 'ctrl+k'], 'command-palette', 'Open command palette');
    
    // Audio control
    this.register(['cmd+shift+a', 'ctrl+shift+a'], 'toggle-audio', 'Toggle audio connection');
    
    // Conversation
    this.register(['cmd+shift+c', 'ctrl+shift+c'], 'clear-conversation', 'Clear conversation');
    this.register(['cmd+e', 'ctrl+e'], 'export-conversation', 'Export conversation');
    
    // Events
    this.register(['cmd+shift+e', 'ctrl+shift+e'], 'clear-events', 'Clear event log');
    this.register(['cmd+/', 'ctrl+/'], 'toggle-events', 'Pause/resume events');
    this.register(['cmd+f', 'ctrl+f'], 'search-events', 'Search events');
    
    // Navigation
    this.register(['1'], 'focus-transcription', 'Focus transcription panel');
    this.register(['2'], 'focus-performance', 'Focus performance panel');
    this.register(['3'], 'focus-conversation', 'Focus conversation panel');
    this.register(['4'], 'focus-config', 'Focus configuration panel');
    this.register(['5'], 'focus-events', 'Focus event stream');
    
    // Debug
    this.register(['cmd+shift+d', 'ctrl+shift+d'], 'export-logs', 'Export debug logs');
    this.register(['cmd+r', 'ctrl+r'], 'reload-config', 'Reload configuration');
    
    // Help
    this.register(['?', 'cmd+?', 'ctrl+?'], 'show-help', 'Show keyboard shortcuts');
  }
  
  register(keys, action, description) {
    // Normalize keys to handle different platforms
    const normalizedKeys = Array.isArray(keys) ? keys : [keys];
    
    normalizedKeys.forEach(key => {
      const normalized = this.normalizeKey(key);
      this.shortcuts.set(normalized, { action, description, key });
    });
  }
  
  normalizeKey(key) {
    // Normalize modifier keys for cross-platform compatibility
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    
    return key
      .toLowerCase()
      .replace('cmd', isMac ? 'meta' : 'ctrl')
      .replace('command', isMac ? 'meta' : 'ctrl')
      .split('+')
      .sort()
      .join('+');
  }
  
  setupListeners() {
    // Keydown handler
    document.addEventListener('keydown', (e) => {
      if (!this.enabled) return;
      
      // Don't trigger shortcuts when typing in inputs
      const target = e.target;
      const isInput = target.tagName === 'INPUT' || 
                     target.tagName === 'TEXTAREA' || 
                     target.tagName === 'SELECT' ||
                     target.contentEditable === 'true';
      
      // Allow some shortcuts even in inputs
      const allowedInInput = ['cmd+k', 'ctrl+k', 'escape'];
      const keyCombo = this.getKeyCombo(e);
      
      if (isInput && !allowedInInput.includes(keyCombo)) {
        return;
      }
      
      // Check if this matches a shortcut
      const normalized = this.normalizeKey(keyCombo);
      const shortcut = this.shortcuts.get(normalized);
      
      if (shortcut) {
        e.preventDefault();
        e.stopPropagation();
        this.emit('shortcut', shortcut.action, e);
      }
      
      // Track active keys
      this.activeKeys.add(e.key.toLowerCase());
    });
    
    // Keyup handler
    document.addEventListener('keyup', (e) => {
      this.activeKeys.delete(e.key.toLowerCase());
    });
    
    // Clear keys on blur
    window.addEventListener('blur', () => {
      this.activeKeys.clear();
    });
  }
  
  getKeyCombo(event) {
    const parts = [];
    
    if (event.metaKey) parts.push('meta');
    if (event.ctrlKey) parts.push('ctrl');
    if (event.altKey) parts.push('alt');
    if (event.shiftKey) parts.push('shift');
    
    // Add the actual key
    let key = event.key.toLowerCase();
    
    // Normalize special keys
    if (key === ' ') key = 'space';
    if (key === 'arrowup') key = 'up';
    if (key === 'arrowdown') key = 'down';
    if (key === 'arrowleft') key = 'left';
    if (key === 'arrowright') key = 'right';
    
    // Only add the key if it's not a modifier
    if (!['meta', 'ctrl', 'alt', 'shift', 'control', 'command', 'option'].includes(key)) {
      parts.push(key);
    }
    
    return parts.join('+');
  }
  
  addHelpText() {
    // Add help text to footer or status bar
    const helpHint = document.createElement('div');
    helpHint.className = 'keyboard-hint';
    helpHint.innerHTML = 'Press <kbd>?</kbd> for keyboard shortcuts';
    helpHint.style.cssText = `
      position: fixed;
      bottom: 10px;
      right: 10px;
      font-size: var(--font-size-xs);
      color: var(--color-gray-500);
      z-index: 100;
    `;
    document.body.appendChild(helpHint);
  }
  
  showHelp() {
    // Group shortcuts by category
    const categories = {
      'General': ['command-palette', 'show-help'],
      'Audio': ['toggle-audio'],
      'Conversation': ['clear-conversation', 'export-conversation'],
      'Events': ['clear-events', 'toggle-events', 'search-events'],
      'Navigation': ['focus-transcription', 'focus-performance', 'focus-conversation', 'focus-config', 'focus-events'],
      'Debug': ['export-logs', 'reload-config']
    };
    
    // Build help modal content
    let helpContent = '<div class="shortcuts-help">';
    helpContent += '<h2>Keyboard Shortcuts</h2>';
    
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    
    Object.entries(categories).forEach(([category, actions]) => {
      helpContent += `<div class="shortcuts-category">`;
      helpContent += `<h3>${category}</h3>`;
      helpContent += '<table class="shortcuts-table">';
      
      actions.forEach(action => {
        const shortcuts = Array.from(this.shortcuts.entries())
          .filter(([_, shortcut]) => shortcut.action === action);
        
        if (shortcuts.length > 0) {
          const [key, shortcut] = shortcuts[0];
          const displayKey = shortcut.key
            .replace('cmd', '⌘')
            .replace('ctrl', isMac ? '⌃' : 'Ctrl')
            .replace('shift', '⇧')
            .replace('alt', isMac ? '⌥' : 'Alt')
            .replace('+', ' ');
          
          helpContent += `
            <tr>
              <td class="shortcut-key"><kbd>${displayKey}</kbd></td>
              <td class="shortcut-description">${shortcut.description}</td>
            </tr>
          `;
        }
      });
      
      helpContent += '</table></div>';
    });
    
    helpContent += '</div>';
    
    // Create and show modal
    this.createHelpModal(helpContent);
  }
  
  createHelpModal(content) {
    // Remove existing modal if any
    const existing = document.getElementById('shortcuts-modal');
    if (existing) existing.remove();
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'shortcuts-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-content">
        <button class="modal-close" aria-label="Close">&times;</button>
        ${content}
      </div>
    `;
    
    // Add styles
    const style = document.createElement('style');
    style.textContent = `
      .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: var(--z-modal);
        animation: fadeIn 200ms ease-out;
      }
      
      .modal-content {
        background: var(--color-gray-950);
        border: 1px solid var(--color-gray-800);
        border-radius: var(--radius-lg);
        padding: var(--space-6);
        max-width: 600px;
        max-height: 80vh;
        overflow-y: auto;
        position: relative;
      }
      
      .modal-close {
        position: absolute;
        top: var(--space-4);
        right: var(--space-4);
        background: none;
        border: none;
        color: var(--color-gray-500);
        font-size: 24px;
        cursor: pointer;
        padding: 0;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-md);
        transition: all var(--transition-fast);
      }
      
      .modal-close:hover {
        background: var(--color-gray-900);
        color: var(--color-white);
      }
      
      .shortcuts-help h2 {
        margin-bottom: var(--space-6);
        color: var(--color-white);
      }
      
      .shortcuts-category {
        margin-bottom: var(--space-6);
      }
      
      .shortcuts-category h3 {
        font-size: var(--font-size-sm);
        text-transform: uppercase;
        letter-spacing: var(--letter-spacing-wider);
        color: var(--color-gray-400);
        margin-bottom: var(--space-3);
      }
      
      .shortcuts-table {
        width: 100%;
        border-collapse: collapse;
      }
      
      .shortcuts-table tr {
        border-bottom: 1px solid var(--color-gray-900);
      }
      
      .shortcuts-table td {
        padding: var(--space-2) 0;
      }
      
      .shortcut-key {
        width: 150px;
        font-family: var(--font-mono);
      }
      
      .shortcut-key kbd {
        display: inline-block;
        padding: var(--space-1) var(--space-2);
        background: var(--color-gray-900);
        border: 1px solid var(--color-gray-800);
        border-radius: var(--radius-sm);
        font-size: var(--font-size-xs);
        color: var(--color-white);
      }
      
      .shortcut-description {
        color: var(--color-gray-300);
        font-size: var(--font-size-sm);
      }
      
      @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
    `;
    
    document.head.appendChild(style);
    document.body.appendChild(modal);
    
    // Close handlers
    const closeModal = () => {
      modal.remove();
      style.remove();
    };
    
    modal.querySelector('.modal-close').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
    
    // ESC to close
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        closeModal();
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);
  }
  
  enable() {
    this.enabled = true;
  }
  
  disable() {
    this.enabled = false;
  }
  
  getShortcuts() {
    return Array.from(this.shortcuts.entries()).map(([key, shortcut]) => ({
      key,
      ...shortcut
    }));
  }
}