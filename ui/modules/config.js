// config.js - Configuration management
console.log('🚀 config.js module loading...');

import { EventEmitter } from './event-emitter.js';
console.log('🚀 EventEmitter imported successfully');

export class ConfigManager extends EventEmitter {
  constructor(state) {
    super();
    console.log('🎯 ConfigManager constructor called');
    this.state = state;
    this.elements = {};
    this.kokoroVoices = this.createKokoroVoices();
    console.log('🎯 ConfigManager constructor completed, voices:', this.kokoroVoices.length);
  }
  
  createKokoroVoices() {
    return [
      // English (US)
      { id: 'af_alloy', name: 'Alloy (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_aoede', name: 'Aoede (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_bella', name: 'Bella (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_heart', name: 'Heart (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_jessica', name: 'Jessica (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_kore', name: 'Kore (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_nicole', name: 'Nicole (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_nova', name: 'Nova (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_river', name: 'River (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_sarah', name: 'Sarah (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      { id: 'af_sky', name: 'Sky (Female, US)', lang: 'en', region: 'us', gender: 'female' },
      
      { id: 'am_adam', name: 'Adam (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_echo', name: 'Echo (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_eric', name: 'Eric (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_fenrir', name: 'Fenrir (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_liam', name: 'Liam (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_michael', name: 'Michael (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_onyx', name: 'Onyx (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      { id: 'am_puck', name: 'Puck (Male, US)', lang: 'en', region: 'us', gender: 'male' },
      
      // English (UK)
      { id: 'bf_alice', name: 'Alice (Female, UK)', lang: 'en', region: 'uk', gender: 'female' },
      { id: 'bf_emma', name: 'Emma (Female, UK)', lang: 'en', region: 'uk', gender: 'female' },
      { id: 'bf_isabella', name: 'Isabella (Female, UK)', lang: 'en', region: 'uk', gender: 'female' },
      { id: 'bf_lily', name: 'Lily (Female, UK)', lang: 'en', region: 'uk', gender: 'female' },
      
      { id: 'bm_daniel', name: 'Daniel (Male, UK)', lang: 'en', region: 'uk', gender: 'male' },
      { id: 'bm_fable', name: 'Fable (Male, UK)', lang: 'en', region: 'uk', gender: 'male' },
      { id: 'bm_george', name: 'George (Male, UK)', lang: 'en', region: 'uk', gender: 'male' },
      { id: 'bm_lewis', name: 'Lewis (Male, UK)', lang: 'en', region: 'uk', gender: 'male' },
      
      // Other Languages
      { id: 'ff_siwis', name: 'Siwis (French)', lang: 'fr', region: 'fr', gender: 'female' },
      { id: 'if_sara', name: 'Sara (Italian, Female)', lang: 'it', region: 'it', gender: 'female' },
      { id: 'im_nicola', name: 'Nicola (Italian, Male)', lang: 'it', region: 'it', gender: 'male' },
      { id: 'jf_alpha', name: 'Alpha (Japanese, Female)', lang: 'ja', region: 'jp', gender: 'female' },
      { id: 'jf_gongitsune', name: 'Gongitsune (Japanese, Female)', lang: 'ja', region: 'jp', gender: 'female' },
      { id: 'jf_nezumi', name: 'Nezumi (Japanese, Female)', lang: 'ja', region: 'jp', gender: 'female' },
      { id: 'jf_tebukuro', name: 'Tebukuro (Japanese, Female)', lang: 'ja', region: 'jp', gender: 'female' },
      { id: 'jm_kumo', name: 'Kumo (Japanese, Male)', lang: 'ja', region: 'jp', gender: 'male' },
      { id: 'zf_xiaobei', name: 'Xiaobei (Chinese, Female)', lang: 'zh', region: 'cn', gender: 'female' },
      { id: 'zf_xiaoni', name: 'Xiaoni (Chinese, Female)', lang: 'zh', region: 'cn', gender: 'female' },
      { id: 'zf_xiaoxiao', name: 'Xiaoxiao (Chinese, Female)', lang: 'zh', region: 'cn', gender: 'female' },
      { id: 'zf_xiaoyi', name: 'Xiaoyi (Chinese, Female)', lang: 'zh', region: 'cn', gender: 'female' },
      { id: 'zm_yunjian', name: 'Yunjian (Chinese, Male)', lang: 'zh', region: 'cn', gender: 'male' },
      { id: 'zm_yunxi', name: 'Yunxi (Chinese, Male)', lang: 'zh', region: 'cn', gender: 'male' },
      { id: 'zm_yunxia', name: 'Yunxia (Chinese, Male)', lang: 'zh', region: 'cn', gender: 'male' },
      { id: 'zm_yunyang', name: 'Yunyang (Chinese, Male)', lang: 'zh', region: 'cn', gender: 'male' },
      { id: 'pf_dora', name: 'Dora (Portuguese, Female)', lang: 'pt', region: 'pt', gender: 'female' },
      { id: 'pm_alex', name: 'Alex (Portuguese, Male)', lang: 'pt', region: 'pt', gender: 'male' },
      { id: 'pm_santa', name: 'Santa (Portuguese, Male)', lang: 'pt', region: 'pt', gender: 'male' },
      
      // Spanish
      { id: 'ef_dora', name: 'Dora (Spanish, Female)', lang: 'es', region: 'es', gender: 'female' },
      { id: 'em_alex', name: 'Alex (Spanish, Male)', lang: 'es', region: 'es', gender: 'male' },
      { id: 'em_santa', name: 'Santa (Spanish, Male)', lang: 'es', region: 'es', gender: 'male' }
    ];
  }
  
  async init() {
    console.log('🎯 ConfigManager init() called');
    
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
      
      // Language controls
      userLanguage: document.getElementById('user-language'),
      showAllVoices: document.getElementById('show-all-voices'),
      vadThreshold: document.getElementById('vad-threshold'),
      vadThresholdValue: document.getElementById('vad-threshold-value'),
      
      // Module controls
      moduleMemory: document.getElementById('module-memory'),
      moduleVoiceRecognition: document.getElementById('module-voice-recognition'),
      
      // Preset selector
      presetSelector: document.getElementById('preset-selector')
    };
    
    console.log('🔍 Debugging voice dropdown issue:');
    console.log('1. TTS Voice element:', this.elements.ttsVoice);
    console.log('2. Kokoro voices array length:', this.kokoroVoices.length);
    console.log('3. First few voices:', this.kokoroVoices.slice(0, 3));
    
    // Debug: Check which elements were found
    console.log('ConfigManager elements cached:');
    Object.keys(this.elements).forEach(key => {
      console.log(`  ${key}:`, this.elements[key] ? '✓' : '✗');
    });
    
    // Set up event listeners
    this.setupListeners();
    
    // Initialize voice dropdown with all voices first
    this.populateVoiceDropdown();
    
    // Initialize with English as default language
    const defaultLanguage = this.elements.userLanguage?.value || 'en';
    this.handleLanguageChange(defaultLanguage);
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
    
    // Language configuration
    if (this.elements.userLanguage) {
      this.elements.userLanguage.addEventListener('change', (e) => {
        const language = e.target.value;
        this.handleLanguageChange(language);
      });
    }
    
    // Show all voices toggle
    if (this.elements.showAllVoices) {
      this.elements.showAllVoices.addEventListener('change', (e) => {
        this.handleShowAllVoicesToggle(e.target.checked);
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
  
  populateVoiceDropdown(filterLanguage = null) {
    const voiceSelect = this.elements.ttsVoice;
    if (!voiceSelect) {
      console.error('Voice dropdown element not found!');
      return;
    }
    
    console.log('Populating voice dropdown with filter:', filterLanguage);
    
    // Get current selection to preserve it if possible
    const currentValue = voiceSelect.value;
    
    // Clear existing options
    voiceSelect.innerHTML = '';
    
    // Filter voices by language if specified
    let voicesToShow = this.kokoroVoices;
    if (filterLanguage) {
      voicesToShow = this.kokoroVoices.filter(voice => voice.lang === filterLanguage);
    }
    
    // Group voices by language for better organization
    const voicesByLang = {};
    voicesToShow.forEach(voice => {
      if (!voicesByLang[voice.lang]) {
        voicesByLang[voice.lang] = [];
      }
      voicesByLang[voice.lang].push(voice);
    });
    
    // Add voices organized by language
    Object.keys(voicesByLang).sort().forEach(lang => {
      // Add optgroup for each language if showing multiple languages
      let container = voiceSelect;
      if (!filterLanguage && Object.keys(voicesByLang).length > 1) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = this.getLanguageName(lang);
        voiceSelect.appendChild(optgroup);
        container = optgroup;
      }
      
      // Sort voices within language: females first, then males, alphabetically
      voicesByLang[lang]
        .sort((a, b) => {
          if (a.gender !== b.gender) {
            return a.gender === 'female' ? -1 : 1;
          }
          return a.name.localeCompare(b.name);
        })
        .forEach(voice => {
          const option = document.createElement('option');
          option.value = voice.id;
          option.textContent = voice.name;
          container.appendChild(option);
        });
    });
    
    // Try to preserve current selection, or set default
    if (currentValue && voiceSelect.querySelector(`option[value="${currentValue}"]`)) {
      voiceSelect.value = currentValue;
    } else {
      // Set language-appropriate default
      const defaultVoice = this.getDefaultVoiceForLanguage(filterLanguage || 'en');
      if (defaultVoice && voiceSelect.querySelector(`option[value="${defaultVoice}"]`)) {
        voiceSelect.value = defaultVoice;
      }
    }
    
    console.log('Voice dropdown populated with', voicesToShow.length, 'voices, selected:', voiceSelect.value);
    
    // Update the voice label to show filtering status
    this.updateVoiceLabel(filterLanguage, voicesToShow.length);
  }
  
  updateVoiceLabel(filterLanguage, voiceCount) {
    const labelElement = document.getElementById('voice-label');
    if (!labelElement) return;
    
    if (filterLanguage) {
      const langName = this.getLanguageName(filterLanguage);
      labelElement.textContent = `Voice (${voiceCount} ${langName})`;
    } else {
      labelElement.textContent = `Voice (${voiceCount} total)`;
    }
  }
  
  getLanguageName(langCode) {
    const names = {
      'en': 'English',
      'fr': 'French',
      'it': 'Italian',
      'ja': 'Japanese',
      'zh': 'Chinese',
      'pt': 'Portuguese',
      'es': 'Spanish'
    };
    return names[langCode] || langCode.toUpperCase();
  }
  
  getDefaultVoiceForLanguage(lang) {
    const defaults = {
      'en': 'af_bella',    // Default English voice (matches config)
      'fr': 'ff_siwis',
      'it': 'if_sara',
      'ja': 'jf_alpha',
      'zh': 'zf_xiaobei',
      'pt': 'pf_dora',
      'es': 'ef_dora'      // Spanish female voice
    };
    return defaults[lang] || 'af_bella';
  }

  handleLanguageChange(language) {
    console.log(`🔄 Language changing to: ${language}`);
    
    // Validate language
    if (!language || typeof language !== 'string') {
      console.error('❌ Invalid language provided:', language);
      return;
    }
    
    try {
      // 1. Set STT to auto-detect for non-English languages
      const sttLanguage = language === 'en' ? 'en' : 'auto';
      this.updateConfig('stt', { language: sttLanguage });
      console.log(`📝 STT config updated to: ${sttLanguage}`);
      
      // 2. Update LLM to respond in the selected language
      this.updateConfig('llm', { response_language: language });
      console.log(`🤖 LLM response language updated to: ${language}`);
      
      // 3. Store user language preference separately
      this.updateConfig('user_language', language);
      console.log(`👤 User language preference updated to: ${language}`);
      
      // 4. Filter and update voice dropdown for the selected language (unless showing all)
      if (!this.elements.showAllVoices?.checked) {
        this.populateVoiceDropdown(language);
      }
      
      // NOTE: Automatic voice switching has been REMOVED
      // Voice will only change when user explicitly selects it
      console.log(`🏁 Language change completed: ${language}, STT: ${sttLanguage}`);
      console.log(`🎤 Voice remains: ${this.elements.ttsVoice?.value} (no automatic switching)`);
    } catch (error) {
      console.error('❌ Error handling language change:', error);
    }
  }
  
  handleShowAllVoicesToggle(showAll) {
    if (showAll) {
      // Show all voices grouped by language
      this.populateVoiceDropdown();
    } else {
      // Show only voices for the selected language
      const currentLanguage = this.elements.userLanguage?.value || 'en';
      this.populateVoiceDropdown(currentLanguage);
    }
    
    console.log(`Show all voices: ${showAll}`);
  }


  updateConfig(component, settings) {
    // Update local state
    this.state.set(`config.${component}`, {
      ...this.state.get(`config.${component}`),
      ...settings
    });
    
    // Emit change event
    this.emit('change', component, settings);
    
    console.log(`📤 Config update sent: ${component}`, settings);
    
    // Special logging for TTS voice changes
    if (component === 'tts' && settings.voice) {
      const voiceObj = this.kokoroVoices.find(v => v.id === settings.voice);
      console.log(`🗣️ TTS Voice change:`, {
        voiceId: settings.voice,
        voiceName: voiceObj?.name,
        voiceLang: voiceObj?.lang,
        timestamp: new Date().toISOString()
      });
    }
  }
  
  loadState(config) {
    // Update form values from configuration
    if (config.llm) {
      this.setElementValue('llmModel', config.llm.model);
      this.setSliderValue('llmTemperature', 'llmTemperatureValue', config.llm.temperature);
      this.setSliderValue('llmMaxTokens', 'llmMaxTokensValue', config.llm.max_tokens);
      this.setSliderValue('llmTopP', 'llmTopPValue', config.llm.top_p);
    }
    
    // Load user language preference first (this will trigger voice filtering)
    const userLanguage = config.user_language || config.llm?.response_language || 'en';
    this.setElementValue('userLanguage', userLanguage);
    
    // Update voice dropdown for the selected language
    this.populateVoiceDropdown(userLanguage);
    
    // Then set TTS configuration
    if (config.tts) {
      this.setElementValue('ttsVoice', config.tts.voice);
      this.setSliderValue('ttsSpeed', 'ttsSpeedValue', config.tts.speed);
      
      // NOTE: Automatic voice correction has been REMOVED
      // Voice will keep its configured value regardless of language
      console.log(`🎤 Voice loaded: ${config.tts.voice} (no automatic correction)`);
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
    
    console.log('State loaded, language:', userLanguage, 'voice:', config.tts?.voice);
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
          top_p: 0.9,
          response_language: 'en'
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
        },
        user_language: 'en'
      },
      'low-latency': {
        llm: {
          model: 'llama3.2:3b',
          temperature: 0.3,
          max_tokens: 500,
          top_p: 0.8,
          response_language: 'en'
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
        },
        user_language: 'en'
      },
      'high-quality': {
        llm: {
          model: 'llama3.2:7b',
          temperature: 0.8,
          max_tokens: 2000,
          top_p: 0.95,
          response_language: 'en'
        },
        tts: {
          voice: 'af_sky',
          speed: 0.9
        },
        stt: {
          language: 'en'
        },
        vad: {
          threshold: 0.6
        },
        user_language: 'en'
      },
      'qwen3b': {
        llm: {
          model: 'qwen3:8b',
          temperature: 0.7,
          max_tokens: 1000,
          top_p: 0.9,
          response_language: 'it'
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
        },
        user_language: 'en'
      }
    };
    
    const preset = presets[presetName];
    if (!preset) {
      console.warn('Unknown preset:', presetName);
      return;
    }
    
    // Apply each configuration section
    Object.entries(preset).forEach(([component, settings]) => {
      if (component !== 'user_language') {
        this.updateConfig(component, settings);
      }
    });
    
    // Handle user language separately to trigger proper voice filtering
    if (preset.user_language) {
      this.handleLanguageChange(preset.user_language);
    }
    
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
  
  // NOTE: Automatic language detection has been DISABLED
  // Language will only change when user explicitly selects it
  
  // Auto-detect language from text and update UI if needed (DISABLED)
  autoDetectLanguageFromText(text, source = 'unknown') {
    // This method has been disabled to prevent automatic language switching
    console.log(`📝 Language auto-detection DISABLED for ${source}: "${text.substring(0, 50)}..."`);
    return false;
  }

  // Auto-detect language from LLM response (DISABLED)
  autoDetectLanguageFromResponse(responseText) {
    // This method has been disabled to prevent automatic language switching
    console.log(`🤖 Language auto-detection DISABLED for LLM response`);
    return false;
  }

  // Auto-detect language from user transcription (DISABLED)
  autoDetectLanguageFromTranscription(transcriptionText) {
    // This method has been disabled to prevent automatic language switching
    console.log(`🗣️ Language auto-detection DISABLED for user transcription`);
    return false;
  }

  // Update available voices from TTS service discovery
  updateAvailableVoices(discoveredVoices) {
    if (!Array.isArray(discoveredVoices) || discoveredVoices.length === 0) {
      console.warn('⚠️ No voices provided for update');
      return;
    }
    
    console.log(`🔄 Updating available voices with ${discoveredVoices.length} discovered voices`);
    
    // Update the kokoro voices list with discovered voices
    this.kokoroVoices = discoveredVoices.map(voice => ({
      id: voice.id,
      name: voice.name,
      lang: voice.lang,
      region: voice.lang, // Use language as region for now
      gender: voice.id.startsWith('af_') || voice.id.startsWith('bf_') || 
              voice.id.startsWith('ff_') || voice.id.startsWith('if_') ||
              voice.id.startsWith('jf_') || voice.id.startsWith('zf_') || 
              voice.id.startsWith('pf_') ? 'female' : 'male'
    }));
    
    // Re-populate the voice dropdown with discovered voices
    const currentLanguage = this.elements.userLanguage?.value || 'en';
    if (!this.elements.showAllVoices?.checked) {
      this.populateVoiceDropdown(currentLanguage);
    } else {
      this.populateVoiceDropdown();
    }
    
    console.log(`✅ Voice list updated with ${this.kokoroVoices.length} voices`);
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