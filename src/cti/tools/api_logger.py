"""
Simple API Logger for debugging external API calls
Logs request payloads, responses, and errors for all API calls made by tools
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


class APILogger:
    """Simple logger for API calls that logs request and response details."""

    def __init__(self, log_file: Optional[str] = None):
        """Initialize API logger."""
        if log_file is None:
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            log_file = str(logs_dir / "api_calls.log")

        self.logger = logging.getLogger("api_calls")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()

        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.propagate = False

    def _sanitize_headers(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from headers."""
        sanitized = dict(headers)
        for key in ['authorization', 'api-key', 'x-api-key', 'cookie']:
            if key.lower() in sanitized:
                sanitized[key] = '***REDACTED***'
        return sanitized

    def _format_payload(self, data: Any) -> str:
        """Format payload for logging."""
        if data is None:
            return "None"
        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, indent=2, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(data)
        return str(data)

    def log_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> None:
        """Log API request details."""
        self.logger.info("=" * 80)
        self.logger.info(f"API REQUEST - {method} {url}")
        self.logger.info("-" * 80)

        if timeout:
            self.logger.info(f"Timeout: {timeout}s")
        if params:
            self.logger.info(f"Query Parameters:\n{self._format_payload(params)}")
        if headers:
            sanitized = self._sanitize_headers(headers)
            self.logger.info(f"Headers:\n{self._format_payload(sanitized)}")
        if json_data:
            self.logger.info(f"Request Body (JSON):\n{self._format_payload(json_data)}")
        self.logger.info("-" * 80)

    def log_response(
        self,
        status_code: int,
        headers: Optional[Dict[str, Any]] = None,
        content: Optional[bytes] = None,
        text: Optional[str] = None,
        is_error: bool = False
    ) -> None:
        """Log API response details."""
        level = logging.ERROR if is_error else logging.INFO
        label = "ERROR RESPONSE" if is_error else "API RESPONSE"

        self.logger.log(level, f"{label} - Status Code: {status_code}")
        self.logger.log(level, "-" * 80)

        if headers:
            self.logger.log(level, f"Response Headers:\n{self._format_payload(dict(headers))}")

        response_body = None
        if text:
            response_body = text
        elif content:
            try:
                response_body = content.decode('utf-8')
            except UnicodeDecodeError:
                response_body = f"<binary content, length: {len(content)} bytes>"

        if response_body:
            try:
                parsed = json.loads(response_body)
                response_body = json.dumps(parsed, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

            if len(response_body) > 5000:
                response_body = response_body[:5000] + f"\n... (truncated, total length: {len(response_body)} chars)"

            self.logger.log(level, f"Response Body:\n{response_body}")

        self.logger.log(level, "=" * 80)

    def log_error(self, error: Exception, method: Optional[str] = None, url: Optional[str] = None) -> None:
        """Log API error with full context."""
        self.logger.error("=" * 80)
        self.logger.error(f"API ERROR - {type(error).__name__}")
        if method and url:
            self.logger.error(f"Request: {method} {url}")
        self.logger.error("-" * 80)
        self.logger.error(f"Error Message: {str(error)}")

        if isinstance(error, httpx.HTTPStatusError) and hasattr(error, 'response') and error.response:
            response_text = None
            try:
                if error.response.content:
                    response_text = error.response.text
            except Exception:
                pass

            self.log_response(
                error.response.status_code,
                dict(error.response.headers) if error.response.headers else None,
                error.response.content,
                response_text,
                is_error=True
            )

        self.logger.error("=" * 80)

    async def log_httpx_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Make an httpx request and log request/response details."""
        params = kwargs.get('params')
        headers = kwargs.get('headers')
        json_data = kwargs.get('json')
        timeout = kwargs.get('timeout')

        self.log_request(method, url, params, headers, json_data, timeout)

        try:
            response = await client.request(method, url, **kwargs)

            response_text = None
            try:
                if response.content:
                    response_text = response.text
            except Exception:
                pass

            is_error = response.status_code >= 400
            self.log_response(
                response.status_code,
                dict(response.headers) if response.headers else None,
                response.content,
                response_text,
                is_error=is_error
            )

            return response

        except Exception as e:
            self.log_error(e, method, url)
            raise


# Global API logger instance
_api_logger: Optional[APILogger] = None


def get_api_logger() -> APILogger:
    """Get or create the global API logger instance."""
    global _api_logger
    if _api_logger is None:
        _api_logger = APILogger()
    return _api_logger


async def logged_request(
    method: str,
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    **kwargs
) -> httpx.Response:
    """
    Make a logged HTTP request using httpx.

    Args:
        method: HTTP method (GET, POST, PATCH, etc.)
        url: Request URL
        client: Optional httpx.AsyncClient. If not provided, creates a temporary one.
        **kwargs: Additional arguments to pass to httpx request

    Returns:
        httpx.Response object
    """
    logger = get_api_logger()

    if client is None:
        async with httpx.AsyncClient() as temp_client:
            return await logger.log_httpx_request(temp_client, method, url, **kwargs)
    else:
        return await logger.log_httpx_request(client, method, url, **kwargs)

