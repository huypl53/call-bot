"""
Demo script for TTSService - Test text-to-speech conversion
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import cti modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from cti.services.tts_service import TTSService


async def main():
    """Demo TTS service with short text"""
    print("🎤 Testing TTS Service...")
    
    service = TTSService()
    test_text = "Hello, this is a test of the text to speech service."
    
    try:
        print(f"📝 Converting text: '{test_text}'")
        print("⏳ Calling text_to_audio...")
        
        # Test PCM16 format
        pcm_data = await service.text_to_audio(test_text, voice="alloy", format="pcm")
        print(f"✅ PCM16 conversion successful! Got {len(pcm_data)} bytes")
        
        # Test WAV format
        print("\n⏳ Converting to WAV format...")
        wav_data = await service.text_to_wav(test_text, voice="alloy")
        print(f"✅ WAV conversion successful! Got {len(wav_data)} bytes")
        
        # Save to files for verification
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        
        pcm_file = output_dir / "test_output.pcm"
        wav_file = output_dir / "test_output.wav"
        
        pcm_file.write_bytes(pcm_data)
        wav_file.write_bytes(wav_data)
        
        print(f"\n💾 Saved audio files:")
        print(f"   - PCM16: {pcm_file}")
        print(f"   - WAV: {wav_file}")
        print("\n✅ Demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

