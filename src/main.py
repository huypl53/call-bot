"""
KIAI Assistant - Main Application
Entry point cho FastAPI application
"""

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings
from src.api.routes import router
from src.api.websocket_handler import WebSocketHandler

# Initialize FastAPI app
app = FastAPI(
    title="KIAI Assistant API",
    description="Trợ lý ảo đặt phòng khách sạn sử dụng OpenAI Realtime API",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

# Initialize WebSocket handler
ws_handler = WebSocketHandler()


@app.websocket("/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.

    Args:
        websocket: FastAPI WebSocket connection
    """
    await ws_handler.handle_connection(websocket)


@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    print("=" * 60)
    print("🚀 KIAI Assistant Starting...")
    print("=" * 60)
    print(f"📊 Settings: {settings}")
    print(f"🔧 Available tools: {ws_handler.tool_service.available_tools}")
    print(f"🌐 Server will run on port: {settings.PORT}")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    print("\n" + "=" * 60)
    print("👋 KIAI Assistant Shutting down...")
    print("=" * 60)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
