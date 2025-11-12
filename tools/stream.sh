#!/bin/bash

# Script to monitor a folder for WAV files and play them using ffplay

set -euo pipefail

# Default input folder
INPUT_FOLDER="${1:-./input}"

# Check if input folder exists
if [ ! -d "$INPUT_FOLDER" ]; then
    echo "Error: Input folder '$INPUT_FOLDER' does not exist" >&2
    exit 1
fi

# Check if ffplay is available
if ! command -v ffplay &> /dev/null; then
    echo "Error: ffplay is not installed or not in PATH" >&2
    exit 1
fi

# Check if inotifywait is available
if ! command -v inotifywait &> /dev/null; then
    echo "Error: inotifywait is not installed. Please install inotify-tools package" >&2
    exit 1
fi

echo "Monitoring folder: $INPUT_FOLDER"
echo "Press Ctrl+C to stop"
echo ""

# Track processed files to avoid replaying
declare -A processed_files

# Function to play a WAV file
play_wav() {
    local file="$1"
    local full_path="$INPUT_FOLDER/$file"
    
    # Skip if already processed
    if [ -n "${processed_files[$file]:-}" ]; then
        return
    fi
    
    # Wait a bit to ensure file is fully written
    sleep 0.5
    
    # Check if file still exists and is readable
    if [ -f "$full_path" ] && [ -r "$full_path" ]; then
        echo "Playing: $file"
        ffplay -nodisp -autoexit "$full_path" 2>/dev/null || true
        processed_files[$file]=1
    fi
}

# Process existing WAV files first
for file in "$INPUT_FOLDER"/*.wav "$INPUT_FOLDER"/*.WAV; do
    if [ -f "$file" ]; then
        play_wav "$(basename "$file")"
    fi
done

# Monitor for new files
inotifywait -m "$INPUT_FOLDER" -e create,moved_to --format '%f' 2>/dev/null | while read -r file; do
    # Check if it's a WAV file
    if [[ "$file" =~ \.(wav|WAV)$ ]]; then
        play_wav "$file"
    fi
done

