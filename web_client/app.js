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
        this.sendInterval = 100; // Minimum 100ms between sends (10 messages per second max) - more conservative
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
    }

    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logMessage = `[${timestamp}] ${message}`;
        
        // Log to console with appropriate level
        const consoleMethod = type === 'error' ? 'error' : type === 'success' ? 'log' : 'info';
        console[consoleMethod](`[${type.toUpperCase()}] ${logMessage}`);
        
        // Also log to UI
        const logDiv = document.getElementById('log');
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        entry.textContent = logMessage;
        logDiv.appendChild(entry);
        logDiv.scrollTop = logDiv.scrollHeight;
    }

    updateStatus(status, message) {
        const statusDiv = document.getElementById('status');
        statusDiv.className = `status ${status}`;
        statusDiv.textContent = message;
    }

    async connect(wsUrl, sessionId) {
        try {
            this.updateStatus('connecting', 'Connecting...');
            this.log(`Connecting to ${wsUrl}...`, 'info');
            console.log('[CONNECT] WebSocket URL:', wsUrl);
            console.log('[CONNECT] Session ID:', sessionId);

            // Create WebSocket - match demo.py behavior exactly
            this.ws = new WebSocket(wsUrl);
            // Ensure we send text frames, not binary
            this.ws.binaryType = 'arraybuffer'; // Only affects receiving, not sending
            this.sessionId = sessionId;
            this.sendErrorLogged = false;
            this.lastSendTime = 0;
            console.log('[CONNECT] WebSocket created, readyState:', this.ws.readyState);

            this.ws.onopen = () => {
                console.log('[WS] WebSocket opened, readyState:', this.ws.readyState);
                this.log('WebSocket connected', 'success');
                this.updateStatus('connected', 'Connected');
                document.getElementById('connectBtn').disabled = true;
                document.getElementById('disconnectBtn').disabled = false;

                // Send start message immediately after connection (like demo.py)
                this.sendStartMessage();
            };

            // Handle messages - be defensive about what we receive
            this.ws.onmessage = (event) => {
                try {
                    let messageData = event.data;
                    console.log('[WS] Message received, type:', typeof messageData, 'isArrayBuffer:', messageData instanceof ArrayBuffer, 'isBlob:', messageData instanceof Blob);
                    
                    // Handle different data types the server might send
                    if (typeof messageData === 'string') {
                        // Normal case: text message
                        console.log('[WS] Received string message, length:', messageData.length);
                        console.log('[WS] Raw message (first 200 chars):', messageData.substring(0, 200));
                        try {
                            const data = JSON.parse(messageData);
                            console.log('[WS] Parsed JSON:', data);
                            this.handleMessage(data);
                        } catch (parseError) {
                            console.error('[WS] Failed to parse JSON:', parseError);
                            console.error('[WS] Raw message:', messageData);
                            this.log(`Failed to parse JSON message: ${parseError.message}`, 'error');
                            this.log(`Raw message: ${messageData.substring(0, 100)}...`, 'error');
                        }
                    } else if (messageData instanceof ArrayBuffer) {
                        // Binary data received - try to decode as text
                        console.log('[WS] Received ArrayBuffer, size:', messageData.byteLength);
                        try {
                            const text = new TextDecoder('utf-8', { fatal: false }).decode(messageData);
                            console.log('[WS] Decoded text:', text.substring(0, 200));
                            const data = JSON.parse(text);
                            console.log('[WS] Parsed JSON from binary:', data);
                            this.handleMessage(data);
                        } catch (decodeError) {
                            console.error('[WS] Failed to decode binary:', decodeError);
                            this.log(`Received binary data that cannot be decoded: ${decodeError.message}`, 'error');
                        }
                    } else if (messageData instanceof Blob) {
                        // Blob received - read as text
                        console.log('[WS] Received Blob, size:', messageData.size);
                        messageData.text().then(text => {
                            console.log('[WS] Blob text:', text.substring(0, 200));
                            try {
                                const data = JSON.parse(text);
                                console.log('[WS] Parsed JSON from blob:', data);
                                this.handleMessage(data);
                            } catch (parseError) {
                                console.error('[WS] Failed to parse blob JSON:', parseError);
                                this.log(`Failed to parse blob message: ${parseError.message}`, 'error');
                            }
                        }).catch(err => {
                            console.error('[WS] Error reading blob:', err);
                            this.log(`Error reading blob: ${err.message}`, 'error');
                        });
                    } else {
                        console.error('[WS] Unexpected message type:', typeof messageData, messageData);
                        this.log(`Unexpected message type: ${typeof messageData}`, 'error');
                    }
                } catch (error) {
                    console.error('[WS] Error handling message:', error);
                    this.log(`Error handling message: ${error.message}`, 'error');
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WS] WebSocket error:', error);
                console.error('[WS] Error event:', error);
                this.log(`WebSocket error occurred`, 'error');
                this.updateStatus('disconnected', 'Connection Error');
            };

            this.ws.onclose = (event) => {
                console.log('[WS] WebSocket closed, code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);
                this.log('WebSocket closed', 'info');
                this.updateStatus('disconnected', 'Disconnected');
                document.getElementById('connectBtn').disabled = false;
                document.getElementById('disconnectBtn').disabled = true;
                this.stopRecording();
            };

        } catch (error) {
            this.log(`Connection error: ${error.message}`, 'error');
            this.updateStatus('disconnected', 'Connection Failed');
        }
    }

    sendStartMessage() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                // Match demo.py exactly: send JSON string as TEXT frame
                const message = {
                    event: 'start',
                    session_id: String(this.sessionId || 'browser_session')
                };
                const jsonString = JSON.stringify(message);
                console.log('[SEND] Start message:', message);
                console.log('[SEND] JSON string:', jsonString);
                console.log('[SEND] JSON string type:', typeof jsonString, 'length:', jsonString.length);
                // Validate JSON is valid before sending
                JSON.parse(jsonString); // Test parse
                // Explicitly send as string to ensure text frame (not binary)
                // In browser WebSocket API, sending a string always creates a text frame
                this.ws.send(jsonString);
                console.log('[SEND] Start message sent successfully as TEXT frame');
                this.log('Sent start message', 'info');
                // Start recording after sending start message
                this.startRecording();
            } catch (error) {
                console.error('[SEND] Error sending start message:', error);
                this.log(`Error sending start message: ${error.message}`, 'error');
            }
        } else {
            console.warn('[SEND] Cannot send start message, WebSocket not open, readyState:', this.ws?.readyState);
        }
    }

    async startRecording() {
        try {
            // Request microphone access
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 24000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            this.log('Microphone access granted', 'success');

            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 24000
            });

            // Create source from microphone
            const source = this.audioContext.createMediaStreamSource(this.mediaStream);

            // Create script processor for audio processing
            const bufferSize = 4096;
            const processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

            processor.onaudioprocess = (e) => {
                if (!this.isRecording) return;

                const inputData = e.inputBuffer.getChannelData(0);
                
                // Voice Activity Detection (VAD)
                const audioLevel = this.calculateAudioLevel(inputData);
                this.lastAudioLevel = audioLevel;
                const wasUserSpeaking = this.isUserSpeaking;
                
                if (audioLevel > this.vadThreshold) {
                    this.vadSilenceFrames = 0;
                    this.isUserSpeaking = true;
                    
                    // If user starts speaking while assistant is speaking, interrupt
                    if (!wasUserSpeaking && this.isAssistantSpeaking) {
                        console.log('[VAD] User started speaking, interrupting assistant');
                        this.sendStopEvent();
                    }
                } else {
                    this.vadSilenceFrames++;
                    if (this.vadSilenceFrames > this.vadSilenceThreshold) {
                        this.isUserSpeaking = false;
                    }
                }
                
                const pcm16 = this.floatTo16BitPCM(inputData);
                const base64 = this.arrayBufferToBase64(pcm16.buffer);

                // Send audio chunk - match server's expected format exactly
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    const now = Date.now();
                    // Throttle sends to avoid overwhelming the server
                    if (now - this.lastSendTime >= this.sendInterval) {
                        try {
                            // Match server's AudioMessage format exactly
                            const message = {
                                event: 'audio',
                                payload: String(base64),  // Ensure it's a string
                                timestamp: Number(now),   // Ensure it's a number
                                format: 'pcm16'           // format string
                            };
                            // Validate and send as JSON string (like demo.py)
                            // IMPORTANT: Must be a string to send as TEXT frame, not binary
                            const jsonString = JSON.stringify(message);
                            // Test parse to ensure it's valid JSON
                            JSON.parse(jsonString);
                            console.log('[SEND] Audio chunk, payload length:', base64.length, 'timestamp:', now);
                            console.log('[SEND] JSON string type:', typeof jsonString, 'length:', jsonString.length);
                            // Explicitly send as string to ensure text frame (not binary)
                            // In browser WebSocket API, sending a string always creates a text frame
                            this.ws.send(jsonString);
                            console.log('[SEND] Audio chunk sent as TEXT frame');
                            this.lastSendTime = now;
                        } catch (error) {
                            // Log errors to console
                            if (!this.sendErrorLogged) {
                                console.error('[SEND] Error sending audio:', error);
                                this.log(`Error sending audio: ${error.message}`, 'error');
                                this.sendErrorLogged = true;
                            }
                        }
                    }
                }

                // Update visualizer
                this.updateVisualizer(inputData);
            };

            source.connect(processor);
            processor.connect(this.audioContext.destination);

            this.processor = processor;
            this.isRecording = true;
            this.log('Recording started', 'success');

        } catch (error) {
            this.log(`Failed to start recording: ${error.message}`, 'error');
            this.updateStatus('disconnected', 'Microphone Access Denied');
        }
    }

    stopRecording() {
        this.isRecording = false;

        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }

        this.log('Recording stopped', 'info');
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
                    event: 'stop'
                };
                const jsonString = JSON.stringify(message);
                this.ws.send(jsonString);
                console.log('[SEND] Stop event sent to interrupt assistant');
                this.log('Interrupting assistant', 'info');
            } catch (error) {
                console.error('[SEND] Error sending stop event:', error);
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

    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
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
        console.log('[HANDLE] Received message:', data);
        
        // Validate message structure
        if (!data || typeof data !== 'object') {
            console.error('[HANDLE] Invalid message format: not an object', data);
            this.log('Invalid message format: not an object', 'error');
            return;
        }

        const eventType = data.event;
        console.log('[HANDLE] Event type:', eventType);

        if (!eventType) {
            console.error('[HANDLE] Message missing event type', data);
            this.log('Message missing event type', 'error');
            return;
        }

        if (eventType === 'audio') {
            console.log('[HANDLE] Processing audio chunk');
            this.isAssistantSpeaking = true;
            this.handleAudioChunk(data);
        } else if (eventType === 'response.done') {
            console.log('[HANDLE] Response done');
            this.isAssistantSpeaking = false;
            this.log('Response complete', 'success');
            this.finishAudioPlayback();
        } else if (eventType === 'response.cancelled') {
            console.log('[HANDLE] Response cancelled');
            this.isAssistantSpeaking = false;
            this.log('Response cancelled', 'info');
            this.stopAudioPlayback();
        } else if (eventType === 'error') {
            const errorMsg = data.message || 'Unknown server error';
            console.error('[HANDLE] Server error:', errorMsg, data);
            this.log(`Server error: ${errorMsg}`, 'error');
        } else if (eventType === 'clear') {
            console.log('[HANDLE] Clear event');
            this.log('Clear event received', 'info');
            this.isAssistantSpeaking = false;
            this.stopAudioPlayback();
        } else {
            console.warn('[HANDLE] Unknown event type:', eventType, data);
            this.log(`Unknown event type: ${eventType}`, 'info');
        }
    }

    handleAudioChunk(data) {
        console.log('[AUDIO] Handling audio chunk, payload type:', typeof data.payload, 'length:', data.payload?.length);
        const payload = data.payload;
        if (payload) {
            try {
                const audioData = this.base64ToArrayBuffer(payload);
                console.log('[AUDIO] Decoded audio data, size:', audioData.byteLength, 'bytes');
                this.audioChunks.push(audioData);
                // this.log(`Received audio chunk (${audioData.byteLength} bytes)`, 'info');
                // Queue the audio chunk for playback instead of playing immediately
                this.queueAudioChunk(audioData);
            } catch (error) {
                console.error('[AUDIO] Error processing audio chunk:', error);
                this.log(`Error processing audio chunk: ${error.message}`, 'error');
            }
        } else {
            console.warn('[AUDIO] Audio chunk missing payload', data);
        }
    }

    stopAudioPlayback() {
        // Stop all active audio sources immediately
        this.audioSources.forEach(source => {
            try {
                source.stop();
            } catch (e) {
                // Source may already be stopped
            }
        });
        this.audioSources = [];
        
        // Clear audio queue and reset playback
        this.audioChunks = [];
        this.audioQueue = [];
        this.isPlaying = false;
        this.nextPlayTime = 0;
        
        // Optionally close and recreate playback context for clean state
        if (this.playbackContext) {
            this.playbackContext.close();
            this.playbackContext = null;
        }
        
        console.log('[AUDIO] Playback stopped and cleared');
    }

    queueAudioChunk(audioData) {
        // Add to queue
        this.audioQueue.push(audioData);
        console.log('[AUDIO] Queued audio chunk, queue length:', this.audioQueue.length);
        
        // Start playing if not already playing
        if (!this.isPlaying) {
            this.processAudioQueue();
        }
    }

    processAudioQueue() {
        if (this.audioQueue.length === 0) {
            this.isPlaying = false;
            return;
        }

        // Create or reuse playback context
        if (!this.playbackContext) {
            this.playbackContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 24000
            });
            this.nextPlayTime = this.playbackContext.currentTime;
        }

        // Process one chunk at a time
        const audioData = this.audioQueue.shift();
        
        try {
            // Convert PCM16 to Float32
            const pcm16 = new Int16Array(audioData);
            const float32 = new Float32Array(pcm16.length);
            for (let i = 0; i < pcm16.length; i++) {
                float32[i] = pcm16[i] / 32768.0;
            }

            // Create buffer
            const buffer = this.playbackContext.createBuffer(1, float32.length, 24000);
            buffer.getChannelData(0).set(float32);

            // Calculate duration
            const duration = buffer.duration;

            // Create source and schedule playback
            const source = this.playbackContext.createBufferSource();
            source.buffer = buffer;
            source.connect(this.playbackContext.destination);
            
            // Track this source so we can stop it if interrupted
            this.audioSources.push(source);
            
            // Schedule playback at the correct time to avoid gaps
            const currentTime = this.playbackContext.currentTime;
            const startTime = Math.max(currentTime, this.nextPlayTime);
            source.start(startTime);
            console.log('[AUDIO] Scheduled audio chunk, duration:', duration.toFixed(3), 's, startTime:', startTime.toFixed(3), 'currentTime:', currentTime.toFixed(3));
            
            // Update next play time for seamless playback
            this.nextPlayTime = startTime + duration;

            // Handle source end - process next chunk in queue
            source.onended = () => {
                // Remove from active sources
                const index = this.audioSources.indexOf(source);
                if (index > -1) {
                    this.audioSources.splice(index, 1);
                }
                
                console.log('[AUDIO] Audio chunk finished playing, queue length:', this.audioQueue.length);
                // Continue processing queue
                if (this.audioQueue.length > 0) {
                    this.processAudioQueue();
                } else {
                    this.isPlaying = false;
                    this.isAssistantSpeaking = false;
                    console.log('[AUDIO] Audio queue empty, playback finished');
                }
            };

        } catch (error) {
            console.error('[AUDIO] Error playing audio chunk:', error);
            this.log(`Failed to play audio chunk: ${error.message}`, 'error');
            // Continue with next chunk even if this one failed
            if (this.audioQueue.length > 0) {
                this.processAudioQueue();
            } else {
                this.isPlaying = false;
            }
        }
    }

    finishAudioPlayback() {
        if (this.audioChunks.length > 0) {
            this.log(`Finished receiving ${this.audioChunks.length} audio chunks`, 'success');
            this.audioChunks = [];
        }
        // Let the queue finish playing
        console.log('[AUDIO] Response done, queue will finish playing');
    }

    initVisualizer() {
        this.visualizerCanvas = document.getElementById('visualizer');
        this.visualizerCtx = this.visualizerCanvas.getContext('2d');
        this.visualizerCanvas.width = this.visualizerCanvas.offsetWidth;
        this.visualizerCanvas.height = this.visualizerCanvas.offsetHeight;
    }

    updateVisualizer(audioData) {
        if (!this.visualizerCtx || !this.visualizerCanvas) return;

        const width = this.visualizerCanvas.width;
        const height = this.visualizerCanvas.height;

        this.visualizerCtx.fillStyle = '#f8f9fa';
        this.visualizerCtx.fillRect(0, 0, width, height);

        this.visualizerCtx.lineWidth = 2;
        this.visualizerCtx.strokeStyle = '#667eea';
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
        console.log('[DISCONNECT] Disconnecting WebSocket');
        if (this.ws) {
            console.log('[DISCONNECT] Closing WebSocket, readyState:', this.ws.readyState);
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
document.getElementById('connectBtn').addEventListener('click', () => {
    const wsUrl = document.getElementById('wsUrl').value;
    const sessionId = document.getElementById('sessionId').value;
    client.connect(wsUrl, sessionId);
});

document.getElementById('disconnectBtn').addEventListener('click', () => {
    client.disconnect();
});

