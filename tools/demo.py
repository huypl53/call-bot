"""
Demo script for audio websocket handler
Supports both single message and long conversation modes
"""

import argparse
import asyncio
import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed

from cti.config.settings import settings


class AudioWebSocketClient:
    """Client for connecting to audio websocket handler"""

    def __init__(self, host: str = "localhost", port: int = 5050):
        """
        Initialize the client.

        Args:
            host: Server hostname
            port: Server port
        """
        self.host = host
        self.port = port
        self.websocket_url = f"ws://{host}:{port}/audio-stream"
        self.websocket = None
        self.message_counter = 0
        self.message_id = str(uuid.uuid4())[:8]

    async def connect(self):
        """Connect to the websocket server"""
        if self.websocket is None:
            print(f"Connecting to {self.websocket_url}...")
            self.websocket = await websockets.connect(self.websocket_url)
            print("✓ Connected to audio websocket")
            
            # Send start message
            start_message = {
                "event": "start",
                "session_id": "demo_session"
            }
            await self.websocket.send(json.dumps(start_message))
            print("✓ Sent start message")
            self.message_counter = 0
    
    async def disconnect(self):
        """Disconnect from the websocket server"""
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                # Connection might already be closed, ignore
                pass
            finally:
                self.websocket = None
                print("✓ Disconnected from server")
    
    async def send_text_and_receive_audio(
        self,
        text: str,
        output_file: Optional[str] = None,
        voice: Optional[str] = None,
        format_type: str = "wav",
        save_audio: bool = True
    ) -> Optional[bytes]:
        """
        Send text message and receive audio response.

        Args:
            text: Text to convert to audio
            output_file: Path to save audio file (optional, auto-generated if None)
            voice: Optional voice selection
            format_type: Audio format (pcm16 or wav)
            save_audio: Whether to save audio to file
        
        Returns:
            Audio data as bytes, or None if failed
        """
        # Reconnect if needed
        if self.websocket is None:
            await self.connect()
        
        try:
            # Send text message
            text_message = {
                "event": "text",
                "text": text,
                "format": format_type
            }
            if voice:
                text_message["voice"] = voice
            
            self.message_counter += 1
            print(f"\n[{self.message_counter}] 📤 Sending: '{text}'")
            
            try:
                await self.websocket.send(json.dumps(text_message))
            except (ConnectionClosed, ConnectionError, Exception):
                # Connection lost, try to reconnect
                print("⚠️  Connection lost, reconnecting...")
                await self.connect()
                await self.websocket.send(json.dumps(text_message))
            
            # Collect audio chunks
            audio_chunks = []
            received_audio = False
            initial_timeout = 300  # Timeout for receiving initial response
            chunk_wait_timeout = 10.0  # Wait time after receiving audio for more chunks
            
            print("📥 Waiting for audio response...")
            
            error_occurred = False
            done_event = asyncio.Event()
            last_chunk_time = None
            completion_task = None
            
            async def receive_messages():
                """Receive messages from websocket"""
                nonlocal audio_chunks, received_audio, error_occurred, last_chunk_time, completion_task
                try:
                    async for message in self.websocket:
                        try:
                            data = json.loads(message)
                            event_type = data.get("event")
                            
                            if event_type == "audio":
                                payload = data.get("payload", "")
                                if payload:
                                    # Decode base64 audio data
                                    audio_data = base64.b64decode(payload)
                                    audio_chunks.append(audio_data)
                                    received_audio = True
                                    last_chunk_time = asyncio.get_event_loop().time()
                                    # print(f"  ✓ Received audio chunk ({len(audio_data)} bytes)")
                                    # Server typically sends audio in one message
                                    # Set a timer to mark as done if no more chunks arrive
                                    if completion_task is None or completion_task.done():
                                        completion_task = asyncio.create_task(
                                            self._wait_for_completion(done_event, chunk_wait_timeout)
                                        )
                            elif event_type == "response.done":
                                # Complete audio received (already in correct format)
                                payload = data.get("payload", "")
                                if payload:
                                    audio_data = base64.b64decode(payload)
                                    # Replace chunks with complete audio
                                    audio_chunks.clear()
                                    audio_chunks.append(audio_data)
                                    received_audio = True
                                    print(f"  ✓ Received complete audio ({len(audio_data)} bytes)")
                                    done_event.set()
                                    return
                            
                            elif event_type == "error":
                                error_msg = data.get("message", "Unknown error")
                                print(f"  ❌ Error: {error_msg}")
                                error_occurred = True
                                done_event.set()
                                return
                            
                            elif event_type == "clear":
                                print("  ✓ Response complete (clear event)")
                                done_event.set()
                                return
                        
                        except json.JSONDecodeError as e:
                            print(f"  ⚠️  Failed to parse message: {e}")
                            continue
                except ConnectionClosed:
                    print("  ⚠️  Connection closed by server")
                    done_event.set()
            
            # Start receiving messages
            receive_task = asyncio.create_task(receive_messages())
            
            try:
                # Wait for completion (error, clear, or timeout after audio)
                await asyncio.wait_for(done_event.wait(), timeout=initial_timeout)
            except asyncio.TimeoutError:
                if received_audio:
                    print("  ✓ Response complete (timeout after receiving audio)")
                else:
                    print(f"  ❌ Timeout: No audio received within {initial_timeout} seconds")
            
            # Cancel the receive task
            if not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
            
            if error_occurred:
                return None
            
            if not received_audio:
                print("  ❌ No audio data received")
                return None
            
            # Combine audio chunks
            audio_data = b"".join(audio_chunks)
            total_size = len(audio_data)
            print(f"  ✅ Received {total_size} bytes total")
            
            # Save audio to file if requested
            if save_audio and audio_data:
                # if output_file is None:
                    # Auto-generate filename
                    # If format_type is pcm16, it will be converted to wav before saving
                file_extension = "wav" if format_type == "pcm16" else format_type
                output_file = f"output/{self.message_id}_{self.message_counter:03d}.{file_extension}"
                
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Convert PCM16 to WAV before saving if format_type is pcm16
                if format_type == "pcm16":
                    audio_data = self._pcm_to_wav(audio_data)
                    # Update file extension to .wav
                    output_path = output_path.with_suffix(".wav")
                
                with open(output_path, "wb") as f:
                    f.write(audio_data)
                
                print(f"  💾 Saved to: {output_path}")
            
            return audio_data
        
        except ConnectionRefusedError:
            print(f"❌ Connection refused. Is the server running on {self.host}:{self.port}?")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _wait_for_completion(self, done_event: asyncio.Event, wait_time: float):
        """Wait for a period, then mark as done if not already done"""
        await asyncio.sleep(wait_time)
        if not done_event.is_set():
            done_event.set()
    
    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 24000) -> bytes:
        """
        Convert PCM16 data to WAV format by adding WAV header.

        Args:
            pcm_data: Raw PCM16 audio data
            sample_rate: Sample rate in Hz (OpenAI TTS uses 24000 Hz)

        Returns:
            WAV formatted audio data
        """
        import io
        import wave

        # Use wave module to create proper WAV file
        # Parameters: (nchannels, sampwidth, framerate, nframes, comptype, compname)
        # nchannels=1 for mono, sampwidth=2 for 16-bit (2 bytes per sample)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setparams((1, 2, sample_rate, 0, 'NONE', 'NONE'))
            wav_file.writeframes(pcm_data)
        
        wav_buffer.seek(0)
        return wav_buffer.read()
    
    async def conversation_mode(
        self,
        voice: Optional[str] = None,
        format_type: str = "wav",
        output_dir: str = "output"
    ):
        """
        Run in conversation mode - keep connection open for multiple exchanges.
        
        Args:
            voice: Optional voice selection
            format_type: Audio format (pcm16 or wav)
            output_dir: Directory to save audio files
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print("\n" + "="*60)
        print("🎤 Conversation Mode")
        print("="*60)
        print("Enter text to convert to audio, or commands:")
        print("  - 'exit' or 'quit': End conversation")
        print("  - 'clear': Clear conversation history")
        print("  - Press Enter on empty line to exit")
        print("="*60 + "\n")
        
        await self.connect()
        
        try:
            while True:
                try:
                    # Get input from user
                    text = input("\n💬 You: ").strip()
                    
                    if not text:
                        print("Exiting conversation...")
                        break
                    
                    # Handle commands
                    if text.lower() in ["exit", "quit", "q"]:
                        print("Exiting conversation...")
                        break
                    
                    if text.lower() == "clear":
                        print("✓ Conversation cleared (session continues)")
                        continue
                    
                    # Send text and receive audio
                    # If format_type is pcm16, it will be converted to wav before saving
                    # so we use .wav extension in the filename
                    file_extension = "wav" if format_type == "pcm16" else format_type
                    output_file = output_path / f"response_{self.message_counter:03d}.{file_extension}"
                    await self.send_text_and_receive_audio(
                        text=text,
                        output_file=str(output_file),
                        voice=voice,
                        format_type=format_type,
                        save_audio=True
                    )
                
                except KeyboardInterrupt:
                    print("\n\nInterrupted by user")
                    break
                except EOFError:
                    print("\n\nEnd of input")
                    break
        
        finally:
            await self.disconnect()


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Demo script for audio websocket handler - supports single message or conversation mode"
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Text to convert to audio (if not provided, enters conversation mode)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output audio file path (default: auto-generated in conversation mode)"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server hostname (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Server port (default: {settings.PORT})"
    )
    parser.add_argument(
        "--voice",
        choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        help="Voice selection (default: from settings)"
    )
    parser.add_argument(
        "--format",
        choices=["pcm16", "wav"],
        default="wav",
        help="Audio format (default: wav)"
    )
    parser.add_argument(
        "--conversation",
        action="store_true",
        help="Force conversation mode even if text is provided"
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory for conversation mode (default: output)"
    )
    
    args = parser.parse_args()
    
    # Get port from args or settings
    port = args.port if args.port is not None else settings.PORT
    
    # Create client
    client = AudioWebSocketClient(host=args.host, port=port)
    
    try:
        # Conversation mode if no text provided or --conversation flag
        if args.conversation or not args.text:
            await client.conversation_mode(
                voice=args.voice,
                format_type=args.format,
                output_dir=args.output_dir,
            )
        else:
            # Single message mode
            # If format_type is pcm16, it will be converted to wav before saving
            file_extension = "wav" if args.format == "pcm16" else args.format
            output_file = args.output or f"output.{file_extension}"
            audio_data = await client.send_text_and_receive_audio(
                text=args.text,
                output_file=output_file,
                voice=args.voice,
                format_type=args.format,
                save_audio=True
            )
            
            if audio_data:
                print("\n✅ Demo completed successfully!")
                sys.exit(0)
            else:
                print("\n❌ Demo failed")
                sys.exit(1)
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

