// events.js - Event stream management with filtering

import { EventEmitter } from './event-emitter.js';

export class EventManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.container = null;
    this.searchInput = null;
    this.filterSelect = null;
    this.pauseButton = null;
    this.events = [];
    this.filteredEvents = [];
    this.maxEvents = 1000;
    this.isPaused = false;
    this.autoScroll = true;
    this.currentFilter = 'all';
    this.searchQuery = '';
  }
  
  async init() {
    this.container = document.getElementById('event-stream');
    this.searchInput = document.getElementById('event-search');
    this.filterSelect = document.getElementById('event-filter');
    this.pauseButton = document.getElementById('pause-events');
    
    // Set up event listeners
    this.setupListeners();
    
    // Initialize display
    this.render();
  }
  
  setupListeners() {
    // Search input
    if (this.searchInput) {
      this.searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.toLowerCase();
        this.applyFilters();
      });
    }
    
    // Filter select
    if (this.filterSelect) {
      this.filterSelect.addEventListener('change', (e) => {
        this.currentFilter = e.target.value;
        this.applyFilters();
      });
    }
    
    // Pause button
    if (this.pauseButton) {
      this.pauseButton.addEventListener('click', () => {
        this.togglePause();
      });
    }
    
    // Scroll detection for auto-scroll
    if (this.container) {
      this.container.addEventListener('scroll', () => {
        const { scrollTop, scrollHeight, clientHeight } = this.container;
        this.autoScroll = scrollTop + clientHeight >= scrollHeight - 10;
      });
    }
  }
  
  add(event) {
    if (this.isPaused) return;
    
    // Add timestamp if not present
    if (!event.timestamp) {
      event.timestamp = Date.now() / 1000;
    }
    
    // Add to events array
    this.events.push(event);
    
    // Trim old events
    if (this.events.length > this.maxEvents) {
      this.events.shift();
    }
    
    // Apply filters and render
    this.applyFilters();
  }
  
  addBatch(events) {
    if (this.isPaused) return;
    
    events.forEach(event => {
      if (!event.timestamp) {
        event.timestamp = Date.now() / 1000;
      }
      this.events.push(event);
    });
    
    // Trim old events
    while (this.events.length > this.maxEvents) {
      this.events.shift();
    }
    
    this.applyFilters();
  }
  
  applyFilters() {
    let filtered = [...this.events];
    
    // Apply type filter
    if (this.currentFilter !== 'all') {
      filtered = filtered.filter(event => {
        switch (this.currentFilter) {
          case 'transcription':
            return event.type.includes('transcription');
          case 'llm':
            return event.type.includes('llm');
          case 'tts':
            return event.type.includes('tts');
          case 'metrics':
            return event.type === 'metrics_update';
          case 'errors':
            return event.type === 'error' || (event.data && event.data.error);
          default:
            return true;
        }
      });
    }
    
    // Apply search filter
    if (this.searchQuery) {
      filtered = filtered.filter(event => {
        const searchText = `${event.type} ${JSON.stringify(event.data)}`.toLowerCase();
        return searchText.includes(this.searchQuery);
      });
    }
    
    this.filteredEvents = filtered;
    this.render();
  }
  
  render() {
    if (!this.container) return;
    
    // Clear container
    this.container.innerHTML = '';
    
    if (this.filteredEvents.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'event-empty';
      empty.textContent = this.isPaused ? 'Event stream paused' : 'No events';
      this.container.appendChild(empty);
      return;
    }
    
    // Create virtual scrolling for performance
    const fragment = document.createDocumentFragment();
    
    // Show only recent events if too many
    const eventsToShow = this.filteredEvents.slice(-100);
    
    eventsToShow.forEach(event => {
      const eventElement = this.createEventElement(event);
      fragment.appendChild(eventElement);
    });
    
    this.container.appendChild(fragment);
    
    // Auto-scroll to bottom if enabled
    if (this.autoScroll) {
      this.scrollToBottom();
    }
  }
  
  createEventElement(event) {
    const element = document.createElement('div');
    element.className = `event-item ${this.getEventClass(event)}`;
    
    // Timestamp
    const timestamp = document.createElement('span');
    timestamp.className = 'event-timestamp';
    timestamp.textContent = this.formatTimestamp(event.timestamp);
    element.appendChild(timestamp);
    
    // Event type
    const type = document.createElement('span');
    type.className = 'event-type';
    type.textContent = event.type;
    element.appendChild(type);
    
    // Event data
    const data = document.createElement('span');
    data.className = 'event-data';
    data.textContent = this.formatEventData(event.data);
    element.appendChild(data);
    
    // Add click handler for expansion
    element.addEventListener('click', () => {
      this.toggleEventExpansion(element, event);
    });
    
    return element;
  }
  
  getEventClass(event) {
    if (event.type === 'error' || (event.data && event.data.error)) {
      return 'error';
    }
    if (event.type.includes('transcription')) {
      return 'transcription';
    }
    if (event.type.includes('llm')) {
      return 'llm';
    }
    if (event.type.includes('tts')) {
      return 'tts';
    }
    if (event.type === 'metrics_update') {
      return 'metrics';
    }
    return '';
  }
  
  formatTimestamp(timestamp) {
    const date = new Date(timestamp * 1000);
    return date.toLocaleTimeString();
  }
  
  formatEventData(data) {
    if (!data) return '';
    
    // Handle different data types
    if (typeof data === 'string') {
      return data.length > 100 ? data.substring(0, 100) + '...' : data;
    }
    
    if (typeof data === 'object') {
      // Special handling for common event types
      if (data.text) {
        return data.text.length > 100 ? data.text.substring(0, 100) + '...' : data.text;
      }
      
      if (data.message) {
        return data.message;
      }
      
      if (data.latency_ms !== undefined) {
        return `${Math.round(data.latency_ms)}ms`;
      }
      
      // Generic object display
      const str = JSON.stringify(data);
      return str.length > 100 ? str.substring(0, 100) + '...' : str;
    }
    
    return String(data);
  }
  
  toggleEventExpansion(element, event) {
    const expanded = element.querySelector('.event-expanded');
    
    if (expanded) {
      // Collapse
      expanded.remove();
      element.classList.remove('expanded');
    } else {
      // Expand
      const expandedDiv = document.createElement('div');
      expandedDiv.className = 'event-expanded';
      
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(event, null, 2);
      expandedDiv.appendChild(pre);
      
      element.appendChild(expandedDiv);
      element.classList.add('expanded');
    }
  }
  
  togglePause() {
    this.isPaused = !this.isPaused;
    
    if (this.pauseButton) {
      const icon = this.pauseButton.querySelector('svg');
      if (this.isPaused) {
        // Change to play icon
        icon.innerHTML = '<polygon points="5,4 15,8 15,8 5,12" fill="currentColor"/>';
        this.pauseButton.setAttribute('aria-label', 'Resume event stream');
      } else {
        // Change to pause icon
        icon.innerHTML = '<rect x="5" y="4" width="2" height="8" fill="currentColor"/><rect x="9" y="4" width="2" height="8" fill="currentColor"/>';
        this.pauseButton.setAttribute('aria-label', 'Pause event stream');
      }
    }
    
    this.emit('pause_toggled', this.isPaused);
    
    // Re-render to show pause state
    this.render();
  }
  
  clear() {
    this.events = [];
    this.filteredEvents = [];
    this.render();
    this.emit('cleared');
  }
  
  scrollToBottom() {
    if (this.container) {
      this.container.scrollTop = this.container.scrollHeight;
    }
  }
  
  exportEvents() {
    const data = {
      events: this.events,
      filters: {
        type: this.currentFilter,
        search: this.searchQuery
      },
      timestamp: new Date().toISOString()
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `maestrocat-events-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  
  getAll() {
    return [...this.events];
  }
  
  getFiltered() {
    return [...this.filteredEvents];
  }
}

// Add event-specific CSS
const style = document.createElement('style');
style.textContent = `
  .event-empty {
    padding: var(--space-8);
    text-align: center;
    color: var(--color-gray-500);
    font-size: var(--font-size-sm);
    font-style: italic;
  }
  
  .event-item.expanded {
    background-color: var(--color-gray-900);
  }
  
  .event-item.transcription .event-type {
    color: var(--color-accent);
  }
  
  .event-item.llm .event-type {
    color: var(--color-success);
  }
  
  .event-item.tts .event-type {
    color: var(--color-warning);
  }
  
  .event-item.metrics .event-type {
    color: var(--color-gray-400);
  }
  
  .event-expanded {
    grid-column: 1 / -1;
    margin-top: var(--space-2);
    padding: var(--space-3);
    background: var(--color-black);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-gray-800);
  }
  
  .event-expanded pre {
    margin: 0;
    font-size: var(--font-size-xs);
    color: var(--color-gray-300);
    white-space: pre-wrap;
    word-break: break-all;
  }
`;
document.head.appendChild(style);