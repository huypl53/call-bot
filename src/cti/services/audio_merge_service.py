"""
Audio Merge Service - Merges multiple WAV files into a single conversation recording
"""

import logging
import re
import wave
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class AudioMergeService:
    """Service for merging audio recording files into a single WAV file"""

    AUDIO_RECORDS_BASE = Path("audio_records")
    MERGED_FILENAME = "merged_conversation.wav"

    # Audio format constants (matching connection_context.py)
    SAMPLE_RATE = 24000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit = 2 bytes

    def merge_audio_files(self, connection_id: str) -> Optional[Path]:
        """
        Merge all WAV files in a connection folder into a single file.

        Args:
            connection_id: UUID of the connection

        Returns:
            Path to merged file, or None if no audio files exist

        Raises:
            FileNotFoundError: If connection folder does not exist
        """
        folder = self.AUDIO_RECORDS_BASE / connection_id
        if not folder.exists():
            raise FileNotFoundError(f"Connection folder not found: {folder}")

        # Get all WAV files (exclude counter files and existing merged file)
        wav_files = self._get_sorted_wav_files(folder)
        if not wav_files:
            logger.info(f"No audio files to merge for connection {connection_id}")
            return None

        output_path = folder / self.MERGED_FILENAME
        self._merge_wav_files(wav_files, output_path)

        logger.info(
            f"Merged {len(wav_files)} audio files into {output_path} for connection {connection_id}"
        )
        return output_path

    def _get_sorted_wav_files(self, folder: Path) -> List[Path]:
        """Get all WAV files sorted chronologically"""
        wav_files = [
            f
            for f in folder.glob("*.wav")
            if not f.name.startswith(".") and f.name != self.MERGED_FILENAME
        ]

        # Sort by parsed timestamp from filename
        return sorted(wav_files, key=self._parse_timestamp_from_filename)

    def _parse_timestamp_from_filename(self, filepath: Path) -> Tuple[datetime, int]:
        """
        Parse timestamp from filename for sorting.
        Pattern: YYYY-MM-DD_HH-MM-SS_mmm_source_counter.wav
        Returns (datetime, counter) for stable sorting
        """
        filename = filepath.stem
        # Pattern: 2025-12-22_09-25-37_877_openai_0001
        pattern = r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_(\d{3})_\w+_(\d{4})"
        match = re.match(pattern, filename)

        if match:
            date_str = match.group(1)
            time_str = match.group(2).replace("-", ":")
            millis = int(match.group(3))
            counter = int(match.group(4))

            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(microsecond=millis * 1000)
            return (dt, counter)

        # Fallback: use file modification time
        return (datetime.fromtimestamp(filepath.stat().st_mtime), 0)

    def _merge_wav_files(self, wav_files: List[Path], output_path: Path):
        """Merge multiple WAV files into one"""
        with wave.open(str(output_path), "wb") as output_wav:
            output_wav.setparams(
                (self.CHANNELS, self.SAMPLE_WIDTH, self.SAMPLE_RATE, 0, "NONE", "NONE")
            )

            for wav_file in wav_files:
                try:
                    with wave.open(str(wav_file), "rb") as input_wav:
                        output_wav.writeframes(
                            input_wav.readframes(input_wav.getnframes())
                        )
                except Exception as e:
                    logger.warning(f"Failed to read {wav_file}: {e}")

    def get_merged_file_path(self, connection_id: str) -> Optional[Path]:
        """Get path to merged file if it exists"""
        path = self.AUDIO_RECORDS_BASE / connection_id / self.MERGED_FILENAME
        return path if path.exists() else None
