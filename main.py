
from cti.config.settings import settings

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "cti.app:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
