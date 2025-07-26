// command-palette.js - Command palette for quick actions

import { EventEmitter } from './event-emitter.js';

export class CommandPalette extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.container = null;
    this.input = null;
    this.list = null;
    this.commands = [];
    this.filteredCommands = [];
    this.selectedIndex = 0;
    this.isOpen = false;
  }
  
  async init() {
    this.container = document.getElementById('command-palette');
    this.input = document.getElementById('command-input');
    this.list = document.getElementById('command-list');
    
    // Register default commands
    this.registerDefaults();
    
    // Set up event listeners
    this.setupListeners();
  }
  
  registerDefaults() {
    // Audio commands
    this.register({
      id: 'toggle-audio',
      name: 'Toggle Audio Connection',
      category: 'Audio',
      shortcut: 'Cmd+Shift+A'
    });
    
    // Conversation commands
    this.register({
      id: 'clear-conversation',
      name: 'Clear Conversation',
      category: 'Conversation',
      shortcut: 'Cmd+Shift+C'
    });
    
    this.register({
      id: 'export-conversation',
      name: 'Export Conversation',
      category: 'Conversation',
      shortcut: 'Cmd+E'
    });
    
    // Event commands
    this.register({
      id: 'clear-events',
      name: 'Clear Event Log',
      category: 'Events'
    });
    
    this.register({
      id: 'toggle-event-stream',
      name: 'Pause/Resume Event Stream',
      category: 'Events'
    });
    
    this.register({
      id: 'filter-events-errors',
      name: 'Show Only Errors',
      category: 'Events',
      action: () => this.filterEvents('errors')
    });
    
    this.register({
      id: 'filter-events-transcription',
      name: 'Show Only Transcription Events',
      category: 'Events',
      action: () => this.filterEvents('transcription')
    });
    
    // Configuration commands
    this.register({
      id: 'reload-config',
      name: 'Reload Configuration',
      category: 'Configuration',
      shortcut: 'Cmd+R'
    });
    
    this.register({
      id: 'switch-preset-low-latency',
      name: 'Switch to Low Latency Preset',
      category: 'Configuration',
      value: 'low-latency'
    });
    
    this.register({
      id: 'switch-preset-high-quality',
      name: 'Switch to High Quality Preset',
      category: 'Configuration',
      value: 'high-quality'
    });
    
    this.register({
      id: 'switch-preset-default',
      name: 'Switch to Default Preset',
      category: 'Configuration',
      value: 'default'
    });
    
    // LLM Model commands
    this.register({
      id: 'switch-model-llama-3b',
      name: 'Switch to Llama 3.2 3B',
      category: 'Models',
      action: () => this.switchModel('llama3.2:3b')
    });
    
    this.register({
      id: 'switch-model-llama-7b',
      name: 'Switch to Llama 3.2 7B',
      category: 'Models',
      action: () => this.switchModel('llama3.2:7b')
    });
    
    this.register({
      id: 'switch-model-mistral',
      name: 'Switch to Mistral 7B',
      category: 'Models',
      action: () => this.switchModel('mistral:7b')
    });
    
    // View commands
    this.register({
      id: 'focus-transcription',
      name: 'Focus Transcription Panel',
      category: 'Navigation',
      shortcut: '1'
    });
    
    this.register({
      id: 'focus-performance',
      name: 'Focus Performance Panel',
      category: 'Navigation',
      shortcut: '2'
    });
    
    this.register({
      id: 'focus-conversation',
      name: 'Focus Conversation Panel',
      category: 'Navigation',
      shortcut: '3'
    });
    
    this.register({
      id: 'focus-config',
      name: 'Focus Configuration Panel',
      category: 'Navigation',
      shortcut: '4'
    });
    
    this.register({
      id: 'focus-events',
      name: 'Focus Event Stream',
      category: 'Navigation',
      shortcut: '5'
    });
    
    // Debug commands
    this.register({
      id: 'export-logs',
      name: 'Export Debug Logs',
      category: 'Debug',
      shortcut: 'Cmd+Shift+D'
    });
    
    this.register({
      id: 'export-metrics',
      name: 'Export Performance Metrics',
      category: 'Debug'
    });
    
    this.register({
      id: 'show-state',
      name: 'Show Application State',
      category: 'Debug',
      action: () => console.log(this.state.exportState())
    });
    
    // Theme commands (future)
    this.register({
      id: 'toggle-high-contrast',
      name: 'Toggle High Contrast Mode',
      category: 'Appearance'
    });
  }
  
  register(command) {
    // Ensure command has required fields
    if (!command.id || !command.name) {
      console.error('Command must have id and name:', command);
      return;
    }
    
    // Set default category
    if (!command.category) {
      command.category = 'General';
    }
    
    // Add to commands list
    this.commands.push(command);
    
    // Sort by category and name
    this.commands.sort((a, b) => {
      if (a.category !== b.category) {
        return a.category.localeCompare(b.category);
      }
      return a.name.localeCompare(b.name);
    });
  }
  
  setupListeners() {
    // Input listeners
    this.input.addEventListener('input', (e) => {
      this.filter(e.target.value);
    });
    
    this.input.addEventListener('keydown', (e) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          this.selectNext();
          break;
          
        case 'ArrowUp':
          e.preventDefault();
          this.selectPrevious();
          break;
          
        case 'Enter':
          e.preventDefault();
          this.executeSelected();
          break;
          
        case 'Escape':
          e.preventDefault();
          this.close();
          break;
      }
    });
    
    // Click outside to close
    this.container.addEventListener('click', (e) => {
      if (e.target === this.container || e.target.classList.contains('command-palette-backdrop')) {
        this.close();
      }
    });
  }
  
  open() {
    if (this.isOpen) return;
    
    this.isOpen = true;
    this.container.setAttribute('aria-hidden', 'false');
    this.input.value = '';
    this.filter('');
    this.selectedIndex = 0;
    
    // Focus input
    setTimeout(() => this.input.focus(), 50);
    
    this.emit('opened');
  }
  
  close() {
    if (!this.isOpen) return;
    
    this.isOpen = false;
    this.container.setAttribute('aria-hidden', 'true');
    this.input.blur();
    
    this.emit('closed');
  }
  
  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }
  
  filter(query) {
    const lowerQuery = query.toLowerCase();
    
    if (!query) {
      this.filteredCommands = [...this.commands];
    } else {
      // Fuzzy search
      this.filteredCommands = this.commands.filter(cmd => {
        const searchText = `${cmd.name} ${cmd.category}`.toLowerCase();
        const words = lowerQuery.split(' ');
        return words.every(word => searchText.includes(word));
      });
      
      // Sort by relevance
      this.filteredCommands.sort((a, b) => {
        const aName = a.name.toLowerCase();
        const bName = b.name.toLowerCase();
        const aStartsWith = aName.startsWith(lowerQuery);
        const bStartsWith = bName.startsWith(lowerQuery);
        
        if (aStartsWith && !bStartsWith) return -1;
        if (!aStartsWith && bStartsWith) return 1;
        
        return a.name.localeCompare(b.name);
      });
    }
    
    // Reset selection
    this.selectedIndex = 0;
    
    // Render results
    this.render();
  }
  
  render() {
    this.list.innerHTML = '';
    
    if (this.filteredCommands.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'command-empty';
      empty.textContent = 'No commands found';
      this.list.appendChild(empty);
      return;
    }
    
    let lastCategory = null;
    
    this.filteredCommands.forEach((command, index) => {
      // Add category header
      if (command.category !== lastCategory) {
        const header = document.createElement('div');
        header.className = 'command-category';
        header.textContent = command.category;
        this.list.appendChild(header);
        lastCategory = command.category;
      }
      
      // Add command item
      const item = document.createElement('div');
      item.className = 'command-item';
      if (index === this.selectedIndex) {
        item.classList.add('selected');
      }
      
      const name = document.createElement('span');
      name.className = 'command-name';
      name.textContent = command.name;
      item.appendChild(name);
      
      if (command.shortcut) {
        const shortcut = document.createElement('span');
        shortcut.className = 'command-shortcut';
        shortcut.textContent = command.shortcut;
        item.appendChild(shortcut);
      }
      
      item.addEventListener('click', () => {
        this.selectedIndex = index;
        this.executeSelected();
      });
      
      item.addEventListener('mouseenter', () => {
        this.selectedIndex = index;
        this.updateSelection();
      });
      
      this.list.appendChild(item);
    });
  }
  
  selectNext() {
    if (this.selectedIndex < this.filteredCommands.length - 1) {
      this.selectedIndex++;
      this.updateSelection();
    }
  }
  
  selectPrevious() {
    if (this.selectedIndex > 0) {
      this.selectedIndex--;
      this.updateSelection();
    }
  }
  
  updateSelection() {
    const items = this.list.querySelectorAll('.command-item');
    items.forEach((item, index) => {
      if (index === this.selectedIndex) {
        item.classList.add('selected');
        // Scroll into view
        item.scrollIntoView({ block: 'nearest' });
      } else {
        item.classList.remove('selected');
      }
    });
  }
  
  executeSelected() {
    const command = this.filteredCommands[this.selectedIndex];
    if (!command) return;
    
    this.close();
    
    // Execute custom action if provided
    if (command.action) {
      command.action();
    } else {
      // Emit command event
      this.emit('command', command);
    }
  }
  
  filterEvents(type) {
    const eventFilter = document.getElementById('event-filter');
    if (eventFilter) {
      eventFilter.value = type;
      eventFilter.dispatchEvent(new Event('change'));
    }
  }
  
  switchModel(model) {
    const modelSelect = document.getElementById('llm-model');
    if (modelSelect) {
      modelSelect.value = model;
      modelSelect.dispatchEvent(new Event('change'));
    }
  }
}

// Add command palette styles
const style = document.createElement('style');
style.textContent = `
  .command-empty {
    padding: var(--space-8);
    text-align: center;
    color: var(--color-gray-500);
    font-size: var(--font-size-sm);
  }
  
  .command-category {
    padding: var(--space-2) var(--space-4);
    font-size: var(--font-size-xs);
    font-weight: var(--font-semibold);
    text-transform: uppercase;
    letter-spacing: var(--letter-spacing-wider);
    color: var(--color-gray-500);
    background: var(--color-gray-900);
  }
`;
document.head.appendChild(style);