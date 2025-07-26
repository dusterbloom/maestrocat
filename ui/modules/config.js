// config.js - Configuration management

import { EventEmitter } from './event-emitter.js';

export class ConfigManager extends EventEmitter {
  constructor(state) {
    super();
    this.state = state;
    this.elements = {};
  }
  
  async init() {
    // Cache form elements
    this.elements = {
      // LLM controls
      llmModel: document.getElementById('llm-model'),
      llmTemperature: document.getElementById('llm-temperature'),
      llmTemperatureValue: document.getElementById('llm-temperature-value'),
      llmMaxTokens: document.getElementById('llm-max-tokens'),
      llmMaxTokensValue: document.getElementById('llm-max-tokens-value'),
      llmTopP: document.getElementById('llm-top-p'),
      llmTopPValue: document.getElementById('llm-top-p-value'),
      
      // TTS controls
      ttsVoice: document.getElementById('tts-voice'),
      ttsSpeed: document.getElementById('tts-speed'),
      ttsSpeedValue: document.getElementById('tts-speed-value'),
      
      // STT controls
      sttLanguage: document.getElementById('stt-language'),
      vadThreshold: document.getElementById('vad-threshold'),
      vadThresholdValue: document.getElementById('vad-threshold-value'),
      
      // Module controls
      moduleMemory: document.getElementById('module-memory'),
      moduleVoiceRecognition: document.getElementById('module-voice-recognition'),
      
      // Preset selector
      presetSelector: document.getElementById('preset-selector')
    };
    
    // Set up event listeners
    this.setupListeners();
  }
  
  setupListeners() {
    // LLM configuration
    if (this.elements.llmModel) {
      this.elements.llmModel.addEventListener('change', (e) => {
        this.updateConfig('llm', { model: e.target.value });
      });
    }
    
    if (this.elements.llmTemperature) {
      this.elements.llmTemperature.addEventListener('input', (e) => {
        const value = parseFloat(e.target.value);
        this.elements.llmTemperatureValue.textContent = value.toFixed(1);
        this.updateConfig('llm', { temperature: value });
      });
    }
    
    if (this.elements.llmMaxTokens) {
      this.elements.llmMaxTokens.addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        this.elements.llmMaxTokensValue.textContent = value;
        this.updateConfig('llm', { max_tokens: value });
      });
    }
    
    if (this.elements.llmTopP) {
      this.elements.llmTopP.addEventListener('input', (e) => {
        const value = parseFloat(e.target.value);
        this.elements.llmTopPValue.textContent = value.toFixed(2);
        this.updateConfig('llm', { top_p: value });
      });
    }
    
    // TTS configuration
    if (this.elements.ttsVoice) {
      this.elements.ttsVoice.addEventListener('change', (e) => {
        this.updateConfig('tts', { voice: e.target.value });
      });
    }
    
    if (this.elements.ttsSpeed) {
      this.elements.ttsSpeed.addEventListener('input', (e) => {
        const value = parseFloat(e.target.value);
        this.elements.ttsSpeedValue.textContent = value.toFixed(1);
        this.updateConfig('tts', { speed: value });
      });
    }
    
    // STT configuration
    if (this.elements.sttLanguage) {
      this.elements.sttLanguage.addEventListener('change', (e) => {
        this.updateConfig('stt', { language: e.target.value });
      });
    }
    
    if (this.elements.vadThreshold) {
      this.elements.vadThreshold.addEventListener('input', (e) => {
        const value = parseFloat(e.target.value);
        this.elements.vadThresholdValue.textContent = value.toFixed(2);
        this.updateConfig('vad', { threshold: value });
      });
    }
    
    // Module toggles
    if (this.elements.moduleMemory) {
      this.elements.moduleMemory.addEventListener('change', (e) => {
        this.updateConfig('modules.memory', { enabled: e.target.checked });
      });
    }
    
    if (this.elements.moduleVoiceRecognition) {
      this.elements.moduleVoiceRecognition.addEventListener('change', (e) => {
        this.updateConfig('modules.voice_recognition', { enabled: e.target.checked });
      });
    }
    
    // Preset selector
    if (this.elements.presetSelector) {
      this.elements.presetSelector.addEventListener('change', (e) => {
        this.applyPreset(e.target.value);
      });
    }
  }
  
  updateConfig(component, settings) {
    // Update local state
    this.state.set(`config.${component}`, {
      ...this.state.get(`config.${component}`),
      ...settings
    });
    
    // Emit change event
    this.emit('change', component, settings);
    
    console.log(`Config updated: ${component}`, settings);
  }
  
  loadState(config) {
    // Update form values from configuration
    if (config.llm) {
      this.setElementValue('llmModel', config.llm.model);
      this.setSliderValue('llmTemperature', 'llmTemperatureValue', config.llm.temperature);
      this.setSliderValue('llmMaxTokens', 'llmMaxTokensValue', config.llm.max_tokens);
      this.setSliderValue('llmTopP', 'llmTopPValue', config.llm.top_p);
    }
    
    if (config.tts) {
      this.setElementValue('ttsVoice', config.tts.voice);
      this.setSliderValue('ttsSpeed', 'ttsSpeedValue', config.tts.speed);
    }
    
    if (config.stt) {
      this.setElementValue('sttLanguage', config.stt.language);
    }
    
    if (config.vad) {
      this.setSliderValue('vadThreshold', 'vadThresholdValue', config.vad.threshold);
    }
    
    if (config.modules) {
      this.setCheckboxValue('moduleMemory', config.modules.memory?.enabled);
      this.setCheckboxValue('moduleVoiceRecognition', config.modules.voice_recognition?.enabled);
    }
    
    // Update state
    this.state.set('config', config);
  }
  
  setElementValue(elementKey, value) {
    const element = this.elements[elementKey];
    if (element && value !== undefined) {
      element.value = value;
    }
  }
  
  setSliderValue(sliderKey, valueKey, value) {
    const slider = this.elements[sliderKey];
    const valueElement = this.elements[valueKey];
    
    if (slider && value !== undefined) {
      slider.value = value;
    }
    
    if (valueElement && value !== undefined) {
      // Format value based on type
      if (Number.isInteger(value)) {
        valueElement.textContent = value.toString();
      } else {
        valueElement.textContent = value.toFixed(value < 1 ? 2 : 1);
      }
    }
  }
  
  setCheckboxValue(elementKey, value) {
    const element = this.elements[elementKey];
    if (element && value !== undefined) {
      element.checked = value;
    }
  }
  
  applyPreset(presetName) {
    const presets = {
      'default': {
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
          language: 'en'
        },
        vad: {
          threshold: 0.5
        }
      },
      'low-latency': {
        llm: {
          model: 'llama3.2:3b',
          temperature: 0.3,
          max_tokens: 500,
          top_p: 0.8
        },
        tts: {
          voice: 'af_bella',
          speed: 1.2
        },
        stt: {
          language: 'en'
        },
        vad: {
          threshold: 0.3
        }
      },
      'high-quality': {
        llm: {
          model: 'llama3.2:7b',
          temperature: 0.8,
          max_tokens: 2000,
          top_p: 0.95
        },
        tts: {
          voice: 'af_sky',
          speed: 0.9
        },
        stt: {
          language: 'auto'
        },
        vad: {
          threshold: 0.6
        }
      }
    };
    
    const preset = presets[presetName];
    if (!preset) {
      console.warn('Unknown preset:', presetName);
      return;
    }
    
    // Apply each configuration section
    Object.entries(preset).forEach(([component, settings]) => {
      this.updateConfig(component, settings);
    });
    
    // Update UI to reflect new values
    this.loadState(preset);
    
    console.log('Applied preset:', presetName);
  }
  
  switchPreset(presetName) {
    if (this.elements.presetSelector) {
      this.elements.presetSelector.value = presetName;
      this.applyPreset(presetName);
    }
  }
  
  reload() {
    // Request fresh configuration from server
    this.emit('reload_requested');
  }
  
  getState() {
    return this.state.get('config');
  }
  
  exportConfig() {
    const config = this.getState();
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `maestrocat-config-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  
  async importConfig(file) {
    try {
      const text = await file.text();
      const config = JSON.parse(text);
      this.loadState(config);
      
      // Apply all settings
      Object.entries(config).forEach(([component, settings]) => {
        this.updateConfig(component, settings);
      });
      
      console.log('Imported configuration from file');
    } catch (error) {
      console.error('Failed to import configuration:', error);
      throw error;
    }
  }
}