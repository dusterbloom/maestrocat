// transcription.js - Real-time transcription display with character streaming

import { EventEmitter } from './event-emitter.js';

export class TranscriptionManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.container = null;
    this.currentLine = null;
    this.isLive = false;
    this.currentTranscriptionId = null;
    this.partialBuffer = '';
    this.confidenceThreshold = 0.8;
  }
  
  async init() {
    this.container = document.getElementById('transcription-view');
    this.liveIndicator = document.querySelector('.live-indicator');
    
    // Clear placeholder
    this.container.innerHTML = '';
  }
  
  setLive(isLive) {
    this.isLive = isLive;
    if (this.liveIndicator) {
      this.liveIndicator.setAttribute('data-live', isLive.toString());
    }
  }
  
  updatePartial(data) {
    const { text, confidence = 1.0, transcript_id } = data;
    
    // Start new transcription if needed
    if (!this.currentTranscriptionId || this.currentTranscriptionId !== transcript_id) {
      this.startNewTranscription(transcript_id);
    }
    
    // Update the current line with streaming text
    if (this.currentLine) {
      this.animateText(this.currentLine.textElement, text, this.partialBuffer);
      this.partialBuffer = text;
      
      // Update confidence display
      if (this.currentLine.confidenceElement) {
        const confidencePercent = Math.round(confidence * 100);
        this.currentLine.confidenceElement.textContent = `${confidencePercent}%`;
        this.currentLine.confidenceElement.style.opacity = confidence;
      }
      
      // Highlight if low confidence
      if (confidence < this.confidenceThreshold) {
        this.currentLine.element.classList.add('low-confidence');
      } else {
        this.currentLine.element.classList.remove('low-confidence');
      }
    }
  }
  
  finalize(data) {
    const { text, confidence = 1.0, timestamp } = data;
    
    if (this.currentLine) {
      // Set final text
      this.currentLine.textElement.textContent = text;
      
      // Add timestamp
      if (timestamp) {
        const timeElement = document.createElement('span');
        timeElement.className = 'transcription-timestamp';
        timeElement.textContent = new Date(timestamp * 1000).toLocaleTimeString();
        this.currentLine.element.appendChild(timeElement);
      }
      
      // Mark as final
      this.currentLine.element.classList.remove('active');
      this.currentLine.element.classList.add('final');
      
      // Reset current line
      this.currentLine = null;
      this.currentTranscriptionId = null;
      this.partialBuffer = '';
    }
    
    // Scroll to bottom
    this.scrollToBottom();
    
    // Emit event
    this.emit('transcription:final', { text, confidence, timestamp });
  }
  
  startNewTranscription(transcriptId) {
    this.currentTranscriptionId = transcriptId;
    this.partialBuffer = '';
    
    // Create new transcription line
    const lineElement = document.createElement('div');
    lineElement.className = 'transcription-line active';
    lineElement.setAttribute('data-transcript-id', transcriptId);
    
    // Add speaker indicator
    const speakerElement = document.createElement('span');
    speakerElement.className = 'transcription-speaker';
    speakerElement.textContent = 'USER';
    lineElement.appendChild(speakerElement);
    
    // Add text container
    const textElement = document.createElement('span');
    textElement.className = 'transcription-text';
    lineElement.appendChild(textElement);
    
    // Add confidence indicator
    const confidenceElement = document.createElement('span');
    confidenceElement.className = 'transcription-confidence';
    lineElement.appendChild(confidenceElement);
    
    // Add to container
    this.container.appendChild(lineElement);
    
    // Store references
    this.currentLine = {
      element: lineElement,
      textElement,
      confidenceElement
    };
    
    // Remove old transcriptions if too many
    this.pruneOldTranscriptions();
    
    // Scroll to show new line
    this.scrollToBottom();
  }
  
  animateText(element, newText, oldText) {
    // Find the common prefix
    let commonLength = 0;
    const minLength = Math.min(oldText.length, newText.length);
    
    for (let i = 0; i < minLength; i++) {
      if (oldText[i] === newText[i]) {
        commonLength++;
      } else {
        break;
      }
    }
    
    // If text was removed (backspace), clear and retype
    if (newText.length < oldText.length && commonLength < newText.length) {
      element.textContent = newText;
      return;
    }
    
    // Add only the new characters with animation
    if (commonLength < newText.length) {
      const existingText = element.textContent.slice(0, commonLength);
      const newChars = newText.slice(commonLength);
      
      element.textContent = existingText;
      
      // Add each character with a slight delay
      let charIndex = 0;
      const addChar = () => {
        if (charIndex < newChars.length) {
          element.textContent += newChars[charIndex];
          charIndex++;
          requestAnimationFrame(addChar);
        }
      };
      
      requestAnimationFrame(addChar);
    }
  }
  
  handleInterruption() {
    if (this.currentLine) {
      this.currentLine.element.classList.add('interrupted');
      
      // Add interruption marker
      const marker = document.createElement('span');
      marker.className = 'interruption-marker';
      marker.textContent = ' [INTERRUPTED]';
      this.currentLine.element.appendChild(marker);
      
      // Reset current line
      this.currentLine = null;
      this.currentTranscriptionId = null;
      this.partialBuffer = '';
    }
  }
  
  clear() {
    this.container.innerHTML = '';
    this.currentLine = null;
    this.currentTranscriptionId = null;
    this.partialBuffer = '';
  }
  
  pruneOldTranscriptions() {
    const lines = this.container.querySelectorAll('.transcription-line');
    const maxLines = 100;
    
    if (lines.length > maxLines) {
      const toRemove = lines.length - maxLines;
      for (let i = 0; i < toRemove; i++) {
        lines[i].remove();
      }
    }
  }
  
  scrollToBottom() {
    if (this.container) {
      this.container.scrollTop = this.container.scrollHeight;
    }
  }
  
  exportTranscription() {
    const lines = this.container.querySelectorAll('.transcription-line');
    const transcription = Array.from(lines).map(line => {
      const speaker = line.querySelector('.transcription-speaker')?.textContent || '';
      const text = line.querySelector('.transcription-text')?.textContent || '';
      const timestamp = line.querySelector('.transcription-timestamp')?.textContent || '';
      const confidence = line.querySelector('.transcription-confidence')?.textContent || '';
      
      return {
        speaker,
        text,
        timestamp,
        confidence,
        interrupted: line.classList.contains('interrupted')
      };
    });
    
    return transcription;
  }
}

// Add CSS for transcription animations
const style = document.createElement('style');
style.textContent = `
  .transcription-line {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    padding: var(--space-2) 0;
    opacity: 0.7;
    transition: opacity var(--transition-base);
  }
  
  .transcription-line.active {
    opacity: 1;
  }
  
  .transcription-line.final {
    opacity: 0.9;
  }
  
  .transcription-line.interrupted {
    color: var(--color-warning);
  }
  
  .transcription-line.low-confidence {
    color: var(--color-gray-500);
  }
  
  .transcription-speaker {
    font-size: var(--font-size-xs);
    font-weight: var(--font-semibold);
    text-transform: uppercase;
    letter-spacing: var(--letter-spacing-wider);
    color: var(--color-gray-500);
    min-width: 60px;
  }
  
  .transcription-text {
    flex: 1;
    font-family: var(--font-mono);
    font-size: var(--font-size-base);
    line-height: var(--line-height-relaxed);
  }
  
  .transcription-confidence {
    font-size: var(--font-size-xs);
    color: var(--color-gray-600);
    font-family: var(--font-mono);
  }
  
  .transcription-timestamp {
    font-size: var(--font-size-xs);
    color: var(--color-gray-600);
    font-family: var(--font-mono);
    margin-left: var(--space-3);
  }
  
  .interruption-marker {
    font-size: var(--font-size-xs);
    color: var(--color-warning);
    text-transform: uppercase;
    letter-spacing: var(--letter-spacing-wider);
  }
  
  /* Cursor animation for active transcription */
  .transcription-line.active .transcription-text::after {
    content: '|';
    animation: blink 1s infinite;
    color: var(--color-accent);
    font-weight: var(--font-bold);
  }
  
  @keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
  }
`;
document.head.appendChild(style);