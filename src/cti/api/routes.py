"""
API Routes for KIAI Assistant
"""

import re
from logging import getLogger

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from cti.services.audio_merge_service import AudioMergeService
from cti.services.twilio_service import TwilioService

router = APIRouter()
twilio_service = TwilioService()
audio_merge_service = AudioMergeService()

logger = getLogger(__name__)


@router.get("/", response_class=JSONResponse)
async def index_page():
    """Health check endpoint"""
    return {
        "message": "KIAI Assistant - Twilio Media Stream Server is running!",
        "status": "healthy",
        "version": "2.0.0"
    }


@router.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """
    Handle incoming call and return TwiML response.

    Returns:
        TwiML XML response
    """
    logger.info("Incoming call request: %s", request.url)
    host = request.url.hostname
    websocket_url = f'wss://{host}/media-stream'

    logger.info("Websocket URL: %s", websocket_url)
    twiml = twilio_service.generate_twiml(websocket_url)

    return HTMLResponse(content=twiml, media_type="application/xml")


@router.get("/audio/{connection_id}/download")
async def download_merged_audio(connection_id: str):
    """
    Download merged audio conversation for a connection.

    Args:
        connection_id: UUID of the connection

    Returns:
        WAV file response or error JSON
    """
    # Validate UUID format for security
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    if not re.match(uuid_pattern, connection_id.lower()):
        return JSONResponse(
            status_code=400, content={"error": "Invalid connection ID format"}
        )

    try:
        # Try to get existing merged file or create new one
        merged_path = audio_merge_service.get_merged_file_path(connection_id)
        if not merged_path:
            merged_path = audio_merge_service.merge_audio_files(connection_id)

        if not merged_path:
            return JSONResponse(
                status_code=404, content={"error": "No audio recordings found"}
            )

        return FileResponse(
            path=str(merged_path),
            media_type="audio/wav",
            filename=f"conversation_{connection_id[:8]}.wav",
        )

    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Connection not found"})
    except Exception as e:
        logger.error(f"Error serving audio file: {e}")
        return JSONResponse(
            status_code=500, content={"error": "Failed to generate audio file"}
        )
