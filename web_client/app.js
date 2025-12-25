class AudioWebSocketClient {
  constructor() {
    this.ws = null;
    this.audioContext = null;
    this.mediaStream = null;
    this.audioWorkletNode = null;
    this.audioChunks = [];
    this.isRecording = false;
    this.sessionId = null;
    this.visualizerCanvas = null;
    this.visualizerCtx = null;
    this.animationFrame = null;
    this.playbackContext = null;
    this.sendErrorLogged = false;
    this.lastSendTime = 0;
    this.sendInterval = 100; // Minimum 100ms between sends (10 messages per second max)
    this.pendingAudioData = []; // Accumulate audio data between sends
    this.audioQueue = [];
    this.isPlaying = false;
    this.nextPlayTime = 0;
    // Voice Activity Detection (VAD) state
    this.vadThreshold = 0.01; // Threshold for detecting speech (adjust based on testing)
    this.vadSilenceFrames = 0;
    this.vadSilenceThreshold = 10; // Frames of silence before considering speech ended
    this.isUserSpeaking = false;
    this.isAssistantSpeaking = false;
    this.audioSources = []; // Track active audio sources for immediate stop
    this.lastAudioLevel = 0;
    this.targetSampleRate = 24000; // Server-required sample rate
    this.gainMultiplier = 3.0; // Boost client audio volume sent over WebSocket (watch for clipping)
    this.micMonitorDelay = 1.25; // Seconds of delay for mic test playback
    this.micMonitorGain = 3.0; // Boost monitor volume (use headphones to avoid feedback)
    this.isMicMonitorActive = false;
    this.micDelayNode = null;
    this.micGainNode = null;
    this.micSource = null;
    this.micMonitorContext = null;
    this.micMonitorSource = null;
    this.micCompressor = null;
  }

  log(message, type = "info") {
    const timestamp = new Date().toLocaleTimeString();
    const logMessage = `[${timestamp}] ${message}`;

    // Log to console with appropriate level
    const consoleMethod = type === "error"
      ? "error"
      : type === "success"
      ? "log"
      : "info";
    console[consoleMethod](`[${type.toUpperCase()}] ${logMessage}`);

    // Also log to UI
    const logDiv = document.getElementById("log");
    const entry = document.createElement("div");
    entry.className = `log-entry ${type}`;
    entry.textContent = logMessage;
    logDiv.appendChild(entry);
    logDiv.scrollTop = logDiv.scrollHeight;
  }

  updateStatus(status, message) {
    const statusDiv = document.getElementById("status");
    statusDiv.className = `status ${status}`;
    statusDiv.textContent = message;
  }

  async connect(wsUrl, sessionId) {
    try {
      this.updateStatus("connecting", "Connecting...");
      this.log(`Connecting to ${wsUrl}...`, "info");
      console.log("[CONNECT] WebSocket URL:", wsUrl);
      console.log("[CONNECT] Session ID:", sessionId);

      // Store WebSocket URL to derive HTTP URL for downloads
      this.wsUrl = wsUrl;

      // Create WebSocket - match demo.py behavior exactly
      this.ws = new WebSocket(wsUrl);
      // Ensure we send text frames, not binary
      this.ws.binaryType = "arraybuffer"; // Only affects receiving, not sending
      this.sessionId = sessionId;
      this.sendErrorLogged = false;
      this.lastSendTime = 0;
      console.log(
        "[CONNECT] WebSocket created, readyState:",
        this.ws.readyState,
      );

      this.ws.onopen = () => {
        console.log("[WS] WebSocket opened, readyState:", this.ws.readyState);
        this.log("WebSocket connected", "success");
        this.updateStatus("connected", "Connected");
        document.getElementById("connectBtn").disabled = true;
        document.getElementById("disconnectBtn").disabled = false;

        // Send start message immediately after connection (like demo.py)
        this.sendStartMessage();
      };

      // Handle messages - be defensive about what we receive
      this.ws.onmessage = (event) => {
        try {
          let messageData = event.data;
          // console.log('[WS] Message received, type:', typeof messageData, 'isArrayBuffer:', messageData instanceof ArrayBuffer, 'isBlob:', messageData instanceof Blob);

          // Handle different data types the server might send
          if (typeof messageData === "string") {
            // Normal case: text message
            // console.log('[WS] Received string message, length:', messageData.length);
            // console.log('[WS] Raw message (first 200 chars):', messageData.substring(0, 200));
            try {
              const data = JSON.parse(messageData);
              // console.log('[WS] Parsed JSON:', data);
              this.handleMessage(data);
            } catch (parseError) {
              console.error("[WS] Failed to parse JSON:", parseError);
              console.error("[WS] Raw message:", messageData);
              this.log(
                `Failed to parse JSON message: ${parseError.message}`,
                "error",
              );
              this.log(
                `Raw message: ${messageData.substring(0, 100)}...`,
                "error",
              );
            }
          } else if (messageData instanceof ArrayBuffer) {
            // Binary data received - try to decode as text
            console.log(
              "[WS] Received ArrayBuffer, size:",
              messageData.byteLength,
            );
            try {
              const text = new TextDecoder("utf-8", { fatal: false }).decode(
                messageData,
              );
              console.log("[WS] Decoded text:", text.substring(0, 200));
              const data = JSON.parse(text);
              console.log("[WS] Parsed JSON from binary:", data);
              this.handleMessage(data);
            } catch (decodeError) {
              console.error("[WS] Failed to decode binary:", decodeError);
              this.log(
                `Received binary data that cannot be decoded: ${decodeError.message}`,
                "error",
              );
            }
          } else if (messageData instanceof Blob) {
            // Blob received - read as text
            console.log("[WS] Received Blob, size:", messageData.size);
            messageData.text().then((text) => {
              console.log("[WS] Blob text:", text.substring(0, 200));
              try {
                const data = JSON.parse(text);
                console.log("[WS] Parsed JSON from blob:", data);
                this.handleMessage(data);
              } catch (parseError) {
                console.error("[WS] Failed to parse blob JSON:", parseError);
                this.log(
                  `Failed to parse blob message: ${parseError.message}`,
                  "error",
                );
              }
            }).catch((err) => {
              console.error("[WS] Error reading blob:", err);
              this.log(`Error reading blob: ${err.message}`, "error");
            });
          } else {
            console.error(
              "[WS] Unexpected message type:",
              typeof messageData,
              messageData,
            );
            this.log(`Unexpected message type: ${typeof messageData}`, "error");
          }
        } catch (error) {
          console.error("[WS] Error handling message:", error);
          this.log(`Error handling message: ${error.message}`, "error");
        }
      };

      this.ws.onerror = (error) => {
        console.error("[WS] WebSocket error:", error);
        console.error("[WS] Error event:", error);
        this.log(`WebSocket error occurred`, "error");
        this.updateStatus("disconnected", "Connection Error");
      };

      this.ws.onclose = (event) => {
        console.log(
          "[WS] WebSocket closed, code:",
          event.code,
          "reason:",
          event.reason,
          "wasClean:",
          event.wasClean,
        );
        this.log("WebSocket closed", "info");
        this.updateStatus("disconnected", "Disconnected");
        document.getElementById("connectBtn").disabled = false;
        document.getElementById("disconnectBtn").disabled = true;
        this.stopRecording();
      };
    } catch (error) {
      this.log(`Connection error: ${error.message}`, "error");
      this.updateStatus("disconnected", "Connection Failed");
    }
  }

  sendStartMessage() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        // Match demo.py exactly: send JSON string as TEXT frame
        const message = {
          event: "start",
          session_id: String(this.sessionId || "browser_session"),
        };
        const jsonString = JSON.stringify(message);
        console.log("[SEND] Start message:", message);
        console.log("[SEND] JSON string:", jsonString);
        console.log(
          "[SEND] JSON string type:",
          typeof jsonString,
          "length:",
          jsonString.length,
        );
        // Validate JSON is valid before sending
        JSON.parse(jsonString); // Test parse
        // Explicitly send as string to ensure text frame (not binary)
        // In browser WebSocket API, sending a string always creates a text frame
        this.ws.send(jsonString);
        console.log("[SEND] Start message sent successfully as TEXT frame");
        this.log("Sent start message", "info");
        // Start recording after sending start message
        this.startRecording();
      } catch (error) {
        console.error("[SEND] Error sending start message:", error);
        this.log(`Error sending start message: ${error.message}`, "error");
      }
    } else {
      console.warn(
        "[SEND] Cannot send start message, WebSocket not open, readyState:",
        this.ws?.readyState,
      );
    }
  }

  async startRecording() {
    try {
      // Request microphone access with 24kHz sample rate
      // Disable autoGainControl which can lower volume
      if (!this.mediaStream) {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: false,
          },
        });
      }

      this.log("Microphone access granted", "success");

      // Create audio context at native sample rate - we'll resample before sending
      if (!this.audioContext) {
        this.audioContext =
          new (window.AudioContext || window.webkitAudioContext)({
            latencyHint: "interactive",
          });
      }

      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }

      console.log("[AUDIO] Context sample rate:", this.audioContext.sampleRate);

      // Check for AudioWorklet support
      if (!this.audioContext.audioWorklet) {
        throw new Error("AudioWorklet API not supported in this browser.");
      }

      // Load the PCM recorder worklet
      await this.audioContext.audioWorklet.addModule("pcm-recorder.worklet.js");

      // Create source from microphone
      const source = this.audioContext.createMediaStreamSource(
        this.mediaStream,
      );
      this.micSource = source;

      // Create AudioWorkletNode for recording
      this.recorderNode = new AudioWorkletNode(
        this.audioContext,
        "pcm-recorder",
      );

      // Set the gain multiplier
      this.recorderNode.port.postMessage({
        type: "set_gain",
        value: this.gainMultiplier,
      });

      // Handle audio chunks from the worklet
      this.recorderNode.port.onmessage = (event) => {
        if (!this.isRecording) return;
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

        const chunk = event.data instanceof ArrayBuffer
          ? new Int16Array(event.data)
          : event.data;

        if (!chunk || !(chunk instanceof Int16Array) || chunk.length === 0) {
          return;
        }

        // Resample from native sample rate to target 24kHz before sending
        const inputSampleRate = this.audioContext.sampleRate;
        let resampledChunk = chunk;
        if (inputSampleRate !== this.targetSampleRate) {
          // Convert Int16 to Float32 for resampling
          const float32 = new Float32Array(chunk.length);
          for (let i = 0; i < chunk.length; i++) {
            float32[i] = chunk[i] / 32768;
          }
          // Resample
          const resampled = this.resampleFloat32(float32, inputSampleRate, this.targetSampleRate);
          // Convert back to Int16
          resampledChunk = this.floatTo16BitPCM(resampled);
        }

        // Send audio immediately - no throttling needed with AudioWorklet
        try {
          const base64 = this.arrayBufferToBase64(resampledChunk.buffer);
          const message = {
            event: "audio",
            payload: base64,
            timestamp: Date.now(),
            format: "pcm16",
          };
          this.ws.send(JSON.stringify(message));
        } catch (error) {
          if (!this.sendErrorLogged) {
            console.error("[SEND] Error sending audio:", error);
            this.log(`Error sending audio: ${error.message}`, "error");
            this.sendErrorLogged = true;
          }
        }
      };

      source.connect(this.recorderNode);
      // Connect to destination to keep the audio graph active
      this.recorderNode.connect(this.audioContext.destination);

      this.isRecording = true;
      const needsResample = this.audioContext.sampleRate !== this.targetSampleRate;
      this.log(`Recording started (AudioWorklet) at ${this.audioContext.sampleRate}Hz${needsResample ? ` → resampling to ${this.targetSampleRate}Hz` : ""}`, "success");
    } catch (error) {
      console.error("[AUDIO] Failed to start recording:", error);
      this.log(`Failed to start recording: ${error.message}`, "error");
      this.updateStatus("disconnected", "Microphone Access Denied");
    }
  }

  stopRecording() {
    this.isRecording = false;

    // Stop mic monitor before tearing down audio graph
    this.stopMicMonitor();

    if (this.recorderNode) {
      this.recorderNode.port.onmessage = null;
      try {
        this.recorderNode.disconnect();
      } catch (e) {}
      this.recorderNode = null;
    }

    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    this.micSource = null;

    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }

    // Clear pending audio data
    this.pendingAudioData = [];

    this.log("Recording stopped", "info");
  }

  calculateAudioLevel(audioData) {
    // Calculate RMS (Root Mean Square) audio level
    let sum = 0;
    for (let i = 0; i < audioData.length; i++) {
      sum += audioData[i] * audioData[i];
    }
    return Math.sqrt(sum / audioData.length);
  }

  sendStopEvent() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        const message = {
          event: "stop",
        };
        const jsonString = JSON.stringify(message);
        this.ws.send(jsonString);
        console.log("[SEND] Stop event sent to interrupt assistant");
        this.log("Interrupting assistant", "info");
      } catch (error) {
        console.error("[SEND] Error sending stop event:", error);
      }
    }
  }

  floatTo16BitPCM(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    let offset = 0;
    for (let i = 0; i < float32Array.length; i++, offset += 2) {
      let s = Math.max(-1, Math.min(1, float32Array[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Int16Array(buffer);
  }

  resampleFloat32(input, inputSampleRate, targetSampleRate) {
    if (inputSampleRate === targetSampleRate) return input;
    const ratio = inputSampleRate / targetSampleRate;
    const outputLength = Math.floor(input.length / ratio);
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i++) {
      const idx = i * ratio;
      const i0 = Math.floor(idx);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const frac = idx - i0;
      // Linear interpolation for smoother downsampling
      output[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    return output;
  }

  arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  handleMessage(data) {
    // console.log('[HANDLE] Received message:', data);

    // Validate message structure
    if (!data || typeof data !== "object") {
      console.error("[HANDLE] Invalid message format: not an object", data);
      this.log("Invalid message format: not an object", "error");
      return;
    }

    const eventType = data.event;
    if (eventType !== "audio") {
      console.log("[HANDLE] Event type:", eventType);
    }

    if (!eventType) {
      console.error("[HANDLE] Message missing event type", data);
      this.log("Message missing event type", "error");
      return;
    }

    if (eventType === "audio") {
      // console.log('[HANDLE] Processing audio chunk');
      this.isAssistantSpeaking = true;
      this.handleAudioChunk(data);
    } else if (eventType === "response.done") {
      console.log("[HANDLE] Response done");
      this.isAssistantSpeaking = false;
      this.log("Response complete", "success");
      // this.finishAudioPlayback();
    } else if (eventType === "response.cancelled") {
      console.log("[HANDLE] Response cancelled");
      this.isAssistantSpeaking = false;
      this.log("Response cancelled", "info");
      this.stopAudioPlayback();
    } else if (eventType === "error") {
      const errorMsg = data.message || "Unknown server error";
      console.error("[HANDLE] Server error:", errorMsg, data);
      this.log(`Server error: ${errorMsg}`, "error");
    } else if (eventType === "clear") {
      console.log("[HANDLE] Clear event");
      this.log("Clear event received", "info");
      this.isAssistantSpeaking = false;
      this.stopAudioPlayback();
    } else if (eventType === "transcription") {
      const transcript = data.transcript || "";
      if (transcript) {
        this.log(`Transcript: ${transcript}`, "info");
      } else {
        this.log("Received transcription event without transcript", "error");
      }
    } else if (eventType === "session.ended") {
      console.log(
        "[HANDLE] Session ended with audio URL:",
        data.audio_download_url,
      );
      this.handleSessionEnded(data);
    } else {
      console.warn("[HANDLE] Unknown event type:", eventType, data);
      this.log(`Unknown event type: ${eventType}`, "info");
    }
  }

  handleAudioChunk(data) {
    // console.log('[AUDIO] Handling audio chunk, payload type:', typeof data.payload, 'length:', data.payload?.length);
    const payload = data.payload;
    if (payload) {
      try {
        const audioData = this.base64ToArrayBuffer(payload);
        // console.log('[AUDIO] Decoded audio data, size:', audioData.byteLength, 'bytes');
        this.audioChunks.push(audioData);
        // this.log(`Received audio chunk (${audioData.byteLength} bytes)`, 'info');
        // Queue the audio chunk for playback instead of playing immediately
        this.queueAudioChunk(audioData);
      } catch (error) {
        console.error("[AUDIO] Error processing audio chunk:", error);
        this.log(`Error processing audio chunk: ${error.message}`, "error");
      }
    } else {
      console.warn("[AUDIO] Audio chunk missing payload", data);
    }
  }

  stopAudioPlayback() {
    // Clear pending chunks
    this.pendingPlaybackChunks = [];
    this.audioChunks = [];
    this.audioQueue = [];

    // Stop all active audio sources (legacy)
    this.audioSources.forEach((source) => {
      try {
        source.stop();
      } catch (e) {}
    });
    this.audioSources = [];

    // Tell playback worklet to stop
    if (this.playbackNode) {
      try {
        this.playbackNode.port.postMessage({ type: "stop" });
      } catch (e) {}
    }

    this.isPlaying = false;
    this.isPlayingAudio = false;
    this.nextPlayTime = 0;

    console.log("[AUDIO] Playback stopped and cleared");
  }

  async startMicMonitor() {
    if (this.isMicMonitorActive) {
      return;
    }

    try {
      if (!this.mediaStream) {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: false,
          },
        });
        this.log("Microphone access granted for mic test", "success");
      }

      // Clean up any previous monitor graph but keep an existing context alive
      this.stopMicMonitor(true);

      // Use a dedicated monitor context at the device/native rate for fidelity
      if (!this.micMonitorContext) {
        this.micMonitorContext =
          new (window.AudioContext || window.webkitAudioContext)({
            latencyHint: "interactive",
          });
      }

      if (this.micMonitorContext.state === "suspended") {
        await this.micMonitorContext.resume();
      }

      // Clean up any previous monitor graph before wiring a new one
      this.stopMicMonitor(true);

      this.micMonitorSource = this.micMonitorContext.createMediaStreamSource(
        this.mediaStream,
      );

      this.micDelayNode = this.micMonitorContext.createDelay(2.0);
      this.micDelayNode.delayTime.value = this.micMonitorDelay;

      // Gentle compressor to lift perceived loudness without clipping too hard
      this.micCompressor = this.micMonitorContext.createDynamicsCompressor();
      this.micCompressor.threshold.value = -30;
      this.micCompressor.knee.value = 20;
      this.micCompressor.ratio.value = 3;
      this.micCompressor.attack.value = 0.003;
      this.micCompressor.release.value = 0.25;

      this.micGainNode = this.micMonitorContext.createGain();
      this.micGainNode.gain.value = this.micMonitorGain;

      this.micMonitorSource.connect(this.micDelayNode);
      this.micDelayNode.connect(this.micCompressor);
      this.micCompressor.connect(this.micGainNode);
      this.micGainNode.connect(this.micMonitorContext.destination);

      this.isMicMonitorActive = true;
      this.log(
        `Mic test playing with ${
          Math.round(this.micMonitorDelay * 1000)
        }ms delay at ${this.micMonitorContext.sampleRate}Hz`,
        "success",
      );
    } catch (error) {
      console.error("[AUDIO] Failed to start mic monitor:", error);
      this.log(`Failed to start mic test: ${error.message}`, "error");
      this.stopMicMonitor();
    }
  }

  stopMicMonitor(keepContext = false) {
    if (this.micGainNode) {
      try {
        this.micGainNode.disconnect();
      } catch (e) {}
    }

    if (this.micDelayNode) {
      try {
        this.micDelayNode.disconnect();
      } catch (e) {}
    }

    if (this.micMonitorSource) {
      try {
        this.micMonitorSource.disconnect();
      } catch (e) {}
    }

    if (this.micCompressor) {
      try {
        this.micCompressor.disconnect();
      } catch (e) {}
    }

    if (this.micMonitorContext && !keepContext) {
      try {
        this.micMonitorContext.close();
      } catch (e) {}
      this.micMonitorContext = null;
    }

    this.micDelayNode = null;
    this.micGainNode = null;
    this.micMonitorSource = null;
    this.isMicMonitorActive = false;
    this.micCompressor = null;

    // Reset button label if present
    const micTestBtn = document.getElementById("micTestBtn");
    if (micTestBtn) {
      micTestBtn.textContent = "Test Mic (Delay)";
    }
  }

  async ensurePlaybackNode() {
    if (this.playbackNode) {
      return;
    }

    if (!this.playbackInitPromise) {
      this.playbackInitPromise = (async () => {
        if (!this.playbackContext) {
          this.playbackContext =
            new (window.AudioContext || window.webkitAudioContext)({
              sampleRate: 24000,
              latencyHint: "interactive",
            });
        }

        if (this.playbackContext.state === "suspended") {
          await this.playbackContext.resume();
        }

        if (!this.playbackContext.audioWorklet) {
          throw new Error("AudioWorklet API not supported");
        }

        await this.playbackContext.audioWorklet.addModule(
          "pcm-playback.worklet.js",
        );

        this.playbackNode = new AudioWorkletNode(
          this.playbackContext,
          "pcm-playback",
          { outputChannelCount: [1] },
        );

        this.playbackNode.port.onmessage = (event) => {
          const message = event.data;
          if (message && message.type === "drained") {
            this.isPlayingAudio = false;
            this.isAssistantSpeaking = false;
          }
        };

        // Configure fade duration
        const fadeSamples = Math.floor(this.playbackContext.sampleRate * 0.02);
        this.playbackNode.port.postMessage({ type: "config", fadeSamples });

        this.playbackNode.connect(this.playbackContext.destination);
      })().catch((error) => {
        this.playbackInitPromise = null;
        throw error;
      });
    }

    await this.playbackInitPromise;
  }

  async queueAudioChunk(audioData) {
    try {
      const int16Array = new Int16Array(audioData);
      if (!int16Array || int16Array.length === 0) {
        return;
      }

      // Store pending chunks while initializing
      if (!this.pendingPlaybackChunks) {
        this.pendingPlaybackChunks = [];
      }
      this.pendingPlaybackChunks.push(int16Array);

      await this.ensurePlaybackNode();
      this.flushPendingPlaybackChunks();
    } catch (error) {
      console.error("[AUDIO] Failed to queue audio:", error);
      this.pendingPlaybackChunks = [];
    }
  }

  flushPendingPlaybackChunks() {
    if (!this.playbackNode || !this.pendingPlaybackChunks) {
      return;
    }

    while (this.pendingPlaybackChunks.length > 0) {
      const chunk = this.pendingPlaybackChunks.shift();
      if (!chunk || !(chunk instanceof Int16Array) || chunk.length === 0) {
        continue;
      }

      try {
        this.playbackNode.port.postMessage(
          { type: "chunk", payload: chunk.buffer },
          [chunk.buffer],
        );
        this.isPlayingAudio = true;
        this.isPlaying = true;
      } catch (error) {
        console.error("[AUDIO] Failed to send chunk to worklet:", error);
      }
    }
  }

  // Legacy method for compatibility
  processAudioQueue() {
    // Now handled by AudioWorklet
  }

  finishAudioPlayback() {
    if (this.audioChunks.length > 0) {
      this.log(
        `Finished receiving ${this.audioChunks.length} audio chunks`,
        "success",
      );
      this.audioChunks = [];
    }
    // Let the queue finish playing
    console.log("[AUDIO] Response done, queue will finish playing");
  }

  handleSessionEnded(data) {
    if (data.audio_download_url) {
      this.audioDownloadUrl = data.audio_download_url;
      this.log("Session ended. Recording available for download.", "success");
      this.showDownloadLink(data.audio_download_url);
    } else {
      this.log("Session ended", "info");
    }
    // Now close the WebSocket
    this.forceClose();
  }

  showDownloadLink(audioUrl) {
    // Derive HTTP URL from WebSocket URL
    // ws://localhost:5050/audio-stream -> http://localhost:5050
    // wss://example.com/audio-stream -> https://example.com
    let baseUrl = "";
    if (this.wsUrl) {
      try {
        const wsUrlObj = new URL(this.wsUrl);
        const protocol = wsUrlObj.protocol === "wss:" ? "https:" : "http:";
        baseUrl = `${protocol}//${wsUrlObj.host}`;
      } catch (e) {
        console.error("[DOWNLOAD] Failed to parse WebSocket URL:", e);
        baseUrl = `${window.location.protocol}//${window.location.host}`;
      }
    } else {
      baseUrl = `${window.location.protocol}//${window.location.host}`;
    }

    const fullUrl = audioUrl.startsWith("/")
      ? `${baseUrl}${audioUrl}`
      : audioUrl;
    console.log("[DOWNLOAD] Full URL:", fullUrl);

    // Create download link in the log
    const logDiv = document.getElementById("log");
    const entry = document.createElement("div");
    entry.className = "log-entry success";
    entry.innerHTML = `
      <a href="${fullUrl}" download="conversation.wav"
         style="color: #4fc1ff; text-decoration: underline; cursor: pointer;">
         Click here to download your conversation recording
      </a>
    `;
    logDiv.appendChild(entry);
    logDiv.scrollTop = logDiv.scrollHeight;
  }

  initVisualizer() {
    this.visualizerCanvas = document.getElementById("visualizer");
    this.visualizerCtx = this.visualizerCanvas.getContext("2d");
    this.visualizerCanvas.width = this.visualizerCanvas.offsetWidth;
    this.visualizerCanvas.height = this.visualizerCanvas.offsetHeight;
  }

  updateVisualizer(audioData) {
    if (!this.visualizerCtx || !this.visualizerCanvas) return;

    const width = this.visualizerCanvas.width;
    const height = this.visualizerCanvas.height;

    this.visualizerCtx.fillStyle = "#f8f9fa";
    this.visualizerCtx.fillRect(0, 0, width, height);

    this.visualizerCtx.lineWidth = 2;
    this.visualizerCtx.strokeStyle = "#667eea";
    this.visualizerCtx.beginPath();

    const sliceWidth = width / audioData.length;
    let x = 0;

    for (let i = 0; i < audioData.length; i++) {
      const v = audioData[i] * 0.5 + 0.5;
      const y = v * height;

      if (i === 0) {
        this.visualizerCtx.moveTo(x, y);
      } else {
        this.visualizerCtx.lineTo(x, y);
      }

      x += sliceWidth;
    }

    this.visualizerCtx.stroke();
  }

  disconnect() {
    console.log("[DISCONNECT] Disconnecting WebSocket");
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log("[DISCONNECT] Sending disconnect event first");
      // Send disconnect event to server to trigger audio merge and get download URL
      try {
        this.ws.send(JSON.stringify({ event: "disconnect" }));
        this.log("Requesting session end...", "info");
        // Don't close immediately - wait for session.ended event
        // Set a timeout to force close if server doesn't respond
        this.disconnectTimeout = setTimeout(() => {
          console.log(
            "[DISCONNECT] Timeout waiting for session.ended, forcing close",
          );
          this.forceClose();
        }, 5000);
      } catch (error) {
        console.error("[DISCONNECT] Error sending disconnect event:", error);
        this.forceClose();
      }
    } else {
      this.forceClose();
    }
  }

  forceClose() {
    if (this.disconnectTimeout) {
      clearTimeout(this.disconnectTimeout);
      this.disconnectTimeout = null;
    }
    if (this.ws) {
      console.log(
        "[DISCONNECT] Closing WebSocket, readyState:",
        this.ws.readyState,
      );
      this.ws.close();
      this.ws = null;
    }
    this.stopRecording();
    this.stopAudioPlayback();
    // Reset VAD state
    this.isUserSpeaking = false;
    this.isAssistantSpeaking = false;
  }
}

// Initialize client
const client = new AudioWebSocketClient();
client.initVisualizer();

// Event listeners
document.getElementById("connectBtn").addEventListener("click", () => {
  const wsUrl = document.getElementById("wsUrl").value;
  const sessionId = document.getElementById("sessionId").value;
  client.connect(wsUrl, sessionId);
});

document.getElementById("disconnectBtn").addEventListener("click", () => {
  client.disconnect();
});

const micTestBtn = document.getElementById("micTestBtn");
micTestBtn.addEventListener("click", async () => {
  if (client.isMicMonitorActive) {
    client.stopMicMonitor();
    micTestBtn.textContent = "Test Mic (Delay)";
  } else {
    await client.startMicMonitor();
    if (client.isMicMonitorActive) {
      micTestBtn.textContent = "Stop Mic Test";
    }
  }
});
