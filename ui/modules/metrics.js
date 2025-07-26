// metrics.js - Performance metrics visualization with charts

import { EventEmitter } from './event-emitter.js';

export class MetricsManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.canvas = null;
    this.ctx = null;
    this.chart = null;
    this.maxDataPoints = 60; // 60 seconds of data
    this.updateInterval = null;
    this.metricSelector = null;
    this.currentView = 'latency';
  }
  
  async init() {
    // Get canvas element
    this.canvas = document.getElementById('performance-canvas');
    if (this.canvas) {
      this.ctx = this.canvas.getContext('2d');
      this.setupCanvas();
    }
    
    // Get metric selector
    this.metricSelector = document.getElementById('metric-selector');
    if (this.metricSelector) {
      this.metricSelector.addEventListener('change', (e) => {
        this.currentView = e.target.value;
        this.render();
      });
    }
    
    // Subscribe to state changes
    this.state.on('metrics:updated', (metrics) => {
      this.updateDisplays(metrics);
      this.render();
    });
    
    // Start render loop
    this.startRenderLoop();
  }
  
  setupCanvas() {
    // Set canvas size
    const container = this.canvas.parentElement;
    const rect = container.getBoundingClientRect();
    this.canvas.width = rect.width - 24; // Account for padding
    this.canvas.height = rect.height - 24;
    
    // Set up high DPI support
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width *= dpr;
    this.canvas.height *= dpr;
    this.canvas.style.width = `${rect.width - 24}px`;
    this.canvas.style.height = `${rect.height - 24}px`;
    this.ctx.scale(dpr, dpr);
    
    // Set default styles
    this.ctx.font = '11px SF Mono, Monaco, Consolas, monospace';
    this.ctx.textAlign = 'left';
    this.ctx.textBaseline = 'middle';
  }
  
  update(metrics) {
    this.state.updateMetrics(metrics);
  }
  
  updateDisplays(metrics) {
    // Update metric cards
    const updates = [
      { id: 'stt-latency', value: metrics.stt_latency_ms },
      { id: 'llm-latency', value: metrics.llm_latency_ms },
      { id: 'tts-latency', value: metrics.tts_latency_ms },
      { id: 'total-latency', value: metrics.total_latency_ms }
    ];
    
    updates.forEach(({ id, value }) => {
      const element = document.getElementById(id);
      if (element && value !== undefined) {
        const rounded = Math.round(value);
        if (element.textContent !== rounded.toString()) {
          element.textContent = rounded;
          // Add pulse animation for changes
          element.style.animation = 'pulse 300ms ease-out';
          setTimeout(() => {
            element.style.animation = '';
          }, 300);
        }
      }
    });
  }
  
  render() {
    if (!this.ctx || !this.canvas) return;
    
    // Clear canvas
    const width = this.canvas.width / (window.devicePixelRatio || 1);
    const height = this.canvas.height / (window.devicePixelRatio || 1);
    this.ctx.clearRect(0, 0, width, height);
    
    switch (this.currentView) {
      case 'latency':
        this.renderLatencyChart(width, height);
        break;
      case 'throughput':
        this.renderThroughputChart(width, height);
        break;
      case 'percentiles':
        this.renderPercentilesChart(width, height);
        break;
    }
  }
  
  renderLatencyChart(width, height) {
    const history = this.state.getMetricsHistory(this.maxDataPoints);
    if (history.length < 2) return;
    
    const padding = { top: 20, right: 40, bottom: 30, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    
    // Find max value for scaling
    let maxValue = 0;
    history.forEach(entry => {
      maxValue = Math.max(maxValue, 
        entry.stt_latency_ms || 0,
        entry.llm_latency_ms || 0,
        entry.tts_latency_ms || 0,
        entry.total_latency_ms || 0
      );
    });
    maxValue = Math.ceil(maxValue / 100) * 100; // Round up to nearest 100
    
    // Draw axes
    this.ctx.strokeStyle = '#404040';
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(padding.left, padding.top);
    this.ctx.lineTo(padding.left, height - padding.bottom);
    this.ctx.lineTo(width - padding.right, height - padding.bottom);
    this.ctx.stroke();
    
    // Draw grid lines
    this.ctx.strokeStyle = '#262626';
    this.ctx.lineWidth = 0.5;
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight * i / 5);
      this.ctx.beginPath();
      this.ctx.moveTo(padding.left, y);
      this.ctx.lineTo(width - padding.right, y);
      this.ctx.stroke();
      
      // Y-axis labels
      this.ctx.fillStyle = '#737373';
      this.ctx.textAlign = 'right';
      const value = Math.round(maxValue * (1 - i / 5));
      this.ctx.fillText(`${value}ms`, padding.left - 10, y);
    }
    
    // Draw data lines
    const metrics = [
      { key: 'stt_latency_ms', color: '#FFB300', label: 'STT' },
      { key: 'llm_latency_ms', color: '#00C851', label: 'LLM' },
      { key: 'tts_latency_ms', color: '#0066FF', label: 'TTS' },
      { key: 'total_latency_ms', color: '#FFFFFF', label: 'Total' }
    ];
    
    metrics.forEach(({ key, color, label }) => {
      this.ctx.strokeStyle = color;
      this.ctx.lineWidth = key === 'total_latency_ms' ? 2 : 1.5;
      this.ctx.beginPath();
      
      history.forEach((entry, index) => {
        const x = padding.left + (index / (this.maxDataPoints - 1)) * chartWidth;
        const value = entry[key] || 0;
        const y = padding.top + chartHeight * (1 - value / maxValue);
        
        if (index === 0) {
          this.ctx.moveTo(x, y);
        } else {
          this.ctx.lineTo(x, y);
        }
      });
      
      this.ctx.stroke();
    });
    
    // Draw legend
    this.ctx.textAlign = 'left';
    metrics.forEach(({ color, label }, index) => {
      const x = width - padding.right - 80;
      const y = padding.top + (index * 20);
      
      // Color indicator
      this.ctx.fillStyle = color;
      this.ctx.fillRect(x, y - 4, 12, 8);
      
      // Label
      this.ctx.fillStyle = '#A3A3A3';
      this.ctx.fillText(label, x + 18, y);
    });
    
    // Time axis label
    this.ctx.fillStyle = '#737373';
    this.ctx.textAlign = 'center';
    this.ctx.fillText('Last 60 seconds', width / 2, height - 5);
  }
  
  renderThroughputChart(width, height) {
    // Calculate requests per second from event history
    const history = this.state.getMetricsHistory(this.maxDataPoints);
    const throughputData = this.calculateThroughput(history);
    
    const padding = { top: 20, right: 40, bottom: 30, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    
    // Draw axes
    this.ctx.strokeStyle = '#404040';
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(padding.left, padding.top);
    this.ctx.lineTo(padding.left, height - padding.bottom);
    this.ctx.lineTo(width - padding.right, height - padding.bottom);
    this.ctx.stroke();
    
    // Bar chart
    const barWidth = chartWidth / throughputData.length - 2;
    this.ctx.fillStyle = '#0066FF';
    
    throughputData.forEach((value, index) => {
      const x = padding.left + (index * (barWidth + 2)) + 1;
      const barHeight = (value / 10) * chartHeight; // Assume max 10 req/s
      const y = height - padding.bottom - barHeight;
      
      this.ctx.fillRect(x, y, barWidth, barHeight);
    });
    
    // Labels
    this.ctx.fillStyle = '#737373';
    this.ctx.textAlign = 'center';
    this.ctx.fillText('Requests per second', width / 2, height - 5);
  }
  
  renderPercentilesChart(width, height) {
    const history = this.state.getMetricsHistory(this.maxDataPoints);
    const percentiles = this.calculatePercentiles(history);
    
    const padding = { top: 40, right: 40, bottom: 40, left: 60 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    
    // Draw percentile boxes
    const metrics = ['stt', 'llm', 'tts', 'total'];
    const boxWidth = chartWidth / metrics.length - 20;
    
    metrics.forEach((metric, index) => {
      const x = padding.left + (index * (boxWidth + 20)) + 10;
      const data = percentiles[metric] || { p50: 0, p95: 0, p99: 0 };
      
      // Draw box
      this.ctx.strokeStyle = '#404040';
      this.ctx.lineWidth = 1;
      this.ctx.strokeRect(x, padding.top, boxWidth, chartHeight);
      
      // Draw percentile lines
      const maxValue = Math.max(data.p99, 500);
      const y50 = padding.top + chartHeight * (1 - data.p50 / maxValue);
      const y95 = padding.top + chartHeight * (1 - data.p95 / maxValue);
      const y99 = padding.top + chartHeight * (1 - data.p99 / maxValue);
      
      // P50 (median)
      this.ctx.strokeStyle = '#00C851';
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.moveTo(x, y50);
      this.ctx.lineTo(x + boxWidth, y50);
      this.ctx.stroke();
      
      // P95
      this.ctx.strokeStyle = '#FFB300';
      this.ctx.lineWidth = 1.5;
      this.ctx.beginPath();
      this.ctx.moveTo(x, y95);
      this.ctx.lineTo(x + boxWidth, y95);
      this.ctx.stroke();
      
      // P99
      this.ctx.strokeStyle = '#FF3B30';
      this.ctx.lineWidth = 1;
      this.ctx.setLineDash([2, 2]);
      this.ctx.beginPath();
      this.ctx.moveTo(x, y99);
      this.ctx.lineTo(x + boxWidth, y99);
      this.ctx.stroke();
      this.ctx.setLineDash([]);
      
      // Labels
      this.ctx.fillStyle = '#A3A3A3';
      this.ctx.textAlign = 'center';
      this.ctx.fillText(metric.toUpperCase(), x + boxWidth / 2, height - padding.bottom + 20);
      
      // Values
      this.ctx.font = '10px SF Mono, Monaco, Consolas, monospace';
      this.ctx.fillStyle = '#737373';
      this.ctx.textAlign = 'right';
      this.ctx.fillText(`${Math.round(data.p50)}`, x - 5, y50);
      this.ctx.fillText(`${Math.round(data.p95)}`, x - 5, y95);
      this.ctx.fillText(`${Math.round(data.p99)}`, x - 5, y99);
      this.ctx.font = '11px SF Mono, Monaco, Consolas, monospace';
    });
    
    // Legend
    const legendY = padding.top - 25;
    this.ctx.textAlign = 'left';
    
    // P50
    this.ctx.fillStyle = '#00C851';
    this.ctx.fillRect(width - 150, legendY, 12, 2);
    this.ctx.fillStyle = '#A3A3A3';
    this.ctx.fillText('P50', width - 130, legendY + 1);
    
    // P95
    this.ctx.fillStyle = '#FFB300';
    this.ctx.fillRect(width - 100, legendY, 12, 2);
    this.ctx.fillStyle = '#A3A3A3';
    this.ctx.fillText('P95', width - 80, legendY + 1);
    
    // P99
    this.ctx.strokeStyle = '#FF3B30';
    this.ctx.lineWidth = 1;
    this.ctx.setLineDash([2, 2]);
    this.ctx.beginPath();
    this.ctx.moveTo(width - 50, legendY);
    this.ctx.lineTo(width - 38, legendY);
    this.ctx.stroke();
    this.ctx.setLineDash([]);
    this.ctx.fillStyle = '#A3A3A3';
    this.ctx.fillText('P99', width - 30, legendY + 1);
  }
  
  calculateThroughput(history) {
    // Group by second and count requests
    const throughput = new Array(60).fill(0);
    const now = Date.now();
    
    history.forEach(entry => {
      const secondsAgo = Math.floor((now - entry.timestamp) / 1000);
      if (secondsAgo >= 0 && secondsAgo < 60) {
        throughput[59 - secondsAgo]++;
      }
    });
    
    return throughput;
  }
  
  calculatePercentiles(history) {
    const metrics = {
      stt: [],
      llm: [],
      tts: [],
      total: []
    };
    
    history.forEach(entry => {
      if (entry.stt_latency_ms) metrics.stt.push(entry.stt_latency_ms);
      if (entry.llm_latency_ms) metrics.llm.push(entry.llm_latency_ms);
      if (entry.tts_latency_ms) metrics.tts.push(entry.tts_latency_ms);
      if (entry.total_latency_ms) metrics.total.push(entry.total_latency_ms);
    });
    
    const result = {};
    
    Object.entries(metrics).forEach(([key, values]) => {
      if (values.length === 0) {
        result[key] = { p50: 0, p95: 0, p99: 0 };
        return;
      }
      
      values.sort((a, b) => a - b);
      result[key] = {
        p50: this.percentile(values, 0.5),
        p95: this.percentile(values, 0.95),
        p99: this.percentile(values, 0.99)
      };
    });
    
    return result;
  }
  
  percentile(arr, p) {
    if (arr.length === 0) return 0;
    const index = Math.ceil(arr.length * p) - 1;
    return arr[Math.max(0, Math.min(index, arr.length - 1))];
  }
  
  startRenderLoop() {
    // Render every second
    this.updateInterval = setInterval(() => {
      this.render();
    }, 1000);
  }
  
  destroy() {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
    }
  }
  
  getHistory() {
    return this.state.getMetricsHistory();
  }
}

// Add CSS for metric animations
const style = document.createElement('style');
style.textContent = `
  @keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
  }
  
  #performance-canvas {
    width: 100%;
    height: 100%;
  }
`;
document.head.appendChild(style);