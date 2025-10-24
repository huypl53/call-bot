"""
API Routes for KIAI Assistant
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from src.services.twilio_service import TwilioService

router = APIRouter()
twilio_service = TwilioService()


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
    host = request.url.hostname
    websocket_url = f'wss://{host}/media-stream'

    twiml = twilio_service.generate_twiml(websocket_url)

    return HTMLResponse(content=twiml, media_type="application/xml")
