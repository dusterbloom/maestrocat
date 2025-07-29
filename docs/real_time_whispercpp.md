enable real-time streaming with `whisper.cpp`** inside your `maestrocat` project on macOS M4.


---

## ✅ High-Level Plan

You’ll switch from `whispercpp`'s batch mode to a new streaming STT service that:

* Launches the compiled `./stream` binary
* Pipes audio into stdin
* Parses stdout for tokens
* Emits transcriptions into the Pipecat pipeline

---

## 🧩 Required Changes (with precise references)

---

### **1. Compile the `stream` binary with Metal**

#### 📄 `build_whispercpp_stream.sh`

```bash
#!/bin/bash
set -e

# Clone whisper.cpp if not already present
if [ ! -d whisper.cpp ]; then
  git clone https://github.com/ggerganov/whisper.cpp
fi

cd whisper.cpp
make clean
WHISPER_METAL=1 make stream

# Optional: copy binary into MaestroCat bin directory
mkdir -p ../bin
cp stream ../bin/stream

echo "✅ whisper.cpp streaming binary built and copied to ./bin/stream"
```

Place this script at the root of your project and run it:

```bash
chmod +x build_whispercpp_stream.sh
./build_whispercpp_stream.sh
```

---

### **2. Create new streaming STT processor**

#### 📄 `core/services/whispercpp_streaming_stt.py`

```python
import subprocess
import threading
from pipecat import Frame, FrameProcessor

class WhisperCppStreamingSTT(FrameProcessor):
    def __init__(self, model_path="models/ggml-base.bin", binary="./bin/stream"):
        super().__init__()
        self.binary = binary
        self.proc = subprocess.Popen(
            [self.binary, "-m", model_path, "-t", "6", "-otxt", "-su", "-ml", "1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=1,
            universal_newlines=True
        )
        self.buffer = ""
        self.lock = threading.Lock()
        threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self):
        for line in self.proc.stdout:
            if line.strip():
                with self.lock:
                    self.buffer += line.strip() + " "

    def process(self, frame: Frame):
        with self.lock:
            if self.buffer:
                output = Frame(text=self.buffer.strip())
                self.buffer = ""
                return [output]
        return []

    def write_audio(self, pcm: bytes):
        try:
            self.proc.stdin.write(pcm)
            self.proc.stdin.flush()
        except Exception:
            pass
```

---

### **3. Create mic audio feeder**

#### 📄 `core/transports/macos_stream_transport.py`

```python
import sounddevice as sd

def start_mic_stream(stt_processor, sample_rate=16000, blocksize=512):
    def callback(indata, frames, time, status):
        stt_processor.write_audio(indata.tobytes())

    stream = sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16', blocksize=blocksize, callback=callback)
    stream.start()
```

Install dependency:

```bash
pip install sounddevice
```

---

### **4. Wire it into your macOS agent**

#### 📄 `examples/local_maestrocat_macos.py` (or wherever you initialize your agent)

Replace current STT logic with:

```python
from core.services.whispercpp_streaming_stt import WhisperCppStreamingSTT
from core.transports.macos_stream_transport import start_mic_stream

stt = WhisperCppStreamingSTT(model_path="models/ggml-base.en.bin")
start_mic_stream(stt)

pipeline = Pipeline([
    stt,
    llm,
    tts,
])
```

---

### **5. Optional: Update config to reflect streaming**

#### 📄 `config/maestrocat_macos.yaml`

```yaml
stt:
  service: whispercpp_streaming
  model_path: models/ggml-base.en.bin
  sample_rate: 16000
  blocksize: 512
```

---

## ✅ Summary: Files to Add or Modify

| File                                        | Action                                              |
| ------------------------------------------- | --------------------------------------------------- |
| `build_whispercpp_stream.sh`                | ➕ Add – builds `stream`                             |
| `core/services/whispercpp_streaming_stt.py` | ➕ Add – streaming STT logic                         |
| `core/transports/macos_stream_transport.py` | ➕ Add – real-time mic input                         |
| `examples/local_maestrocat_macos.py`        | ✏️ Modify – replace STT                             |
| `config/maestrocat_macos.yaml`              | ✏️ Modify (optional) – config alias for new service |

---

Would you like a ZIP with these new files prewritten and ready to drop into your repo?
