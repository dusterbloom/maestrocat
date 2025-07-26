// websocket.js - WebSocket connection management

import { EventEmitter } from './event-emitter.js';

export class WebSocketManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000;
    this.reconnectTimer = null;
  }
  
  async connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }
    
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const port = 8080; // Debug UI port
      
      this.ws = new WebSocket(`${protocol}//${host}:${port}/ws`);
      
      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.emit('connected');
      };
      
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.emit('message', data);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };
      
      this.ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        this.emit('disconnected');
        this.scheduleReconnect();
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.emit('error', error);
      };
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      this.emit('error', error);
      this.scheduleReconnect();
    }
  }
  
  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
  
  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.emit('reconnect_failed');
      return;
    }
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    
    this.reconnectAttempts++;
    console.log(`Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);
    
    // Exponential backoff with max delay of 30 seconds
    this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30000);
  }
  
  send(data) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not connected');
      return false;
    }
    
    try {
      this.ws.send(JSON.stringify(data));
      return true;
    } catch (error) {
      console.error('Failed to send WebSocket message:', error);
      return false;
    }
  }
  
  sendConfigUpdate(component, settings) {
    return this.send({
      type: 'config_update',
      component,
      settings
    });
  }
  
  sendCommand(command, params = {}) {
    return this.send({
      type: 'command',
      command,
      params
    });
  }
  
  requestEvents(since = 0) {
    return this.send({
      type: 'get_events',
      since
    });
  }
  
  getState() {
    return {
      connected: this.ws && this.ws.readyState === WebSocket.OPEN,
      reconnectAttempts: this.reconnectAttempts
    };
  }
}