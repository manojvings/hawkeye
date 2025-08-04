# app/middleware/compression.py
"""
Request/Response compression middleware for automatic compression
Supports gzip and brotli compression
"""
import gzip
import io
from typing import Callable, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.datastructures import MutableHeaders
from loguru import logger

try:
    import brotli

    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False
    logger.warning("Brotli not available, install with: pip install brotli")


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    Automatic compression middleware for all responses
    """

    def __init__(
            self,
            app,
            minimum_size: int = 1024,  # Don't compress responses smaller than 1KB
            compression_level: int = 6,  # 1-9, where 9 is maximum compression
            exclude_paths: Optional[List[str]] = None,
            exclude_media_types: Optional[List[str]] = None
    ):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compression_level = compression_level
        self.exclude_paths = exclude_paths or ['/metrics', '/health']
        self.exclude_media_types = exclude_media_types or [
            'image/', 'video/', 'audio/', 'font/'
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip compression for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Check Accept-Encoding header
        accept_encoding = request.headers.get('accept-encoding', '').lower()

        # Process the request
        response = await call_next(request)

        # Skip if already compressed
        if 'content-encoding' in response.headers:
            return response

        # Skip based on content type
        content_type = response.headers.get('content-type', '')
        if any(excluded in content_type for excluded in self.exclude_media_types):
            return response

        # Skip if response is too small
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) < self.minimum_size:
            return response

        # Determine compression method
        compression_type = None
        if 'br' in accept_encoding and BROTLI_AVAILABLE:
            compression_type = 'br'
        elif 'gzip' in accept_encoding:
            compression_type = 'gzip'

        if not compression_type:
            return response

        # Handle streaming responses
        if isinstance(response, StreamingResponse):
            return await self._compress_streaming_response(
                response, compression_type
            )

        # Handle regular responses
        return await self._compress_response(response, compression_type)

    async def _compress_response(self, response: Response, compression_type: str) -> Response:
        """Compress a regular response"""
        # Read response body
        body = b''
        async for chunk in response.body_iterator:
            body += chunk

        # Skip if too small after reading
        if len(body) < self.minimum_size:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        # Compress body
        if compression_type == 'gzip':
            compressed_body = gzip.compress(body, compresslevel=self.compression_level)
        elif compression_type == 'br' and BROTLI_AVAILABLE:
            compressor = brotli.Compressor(quality=self.compression_level)
            compressed_body = compressor.process(body) + compressor.finish()
        else:
            return response

        # Update headers
        headers = MutableHeaders(response.headers)
        headers['content-encoding'] = compression_type
        headers['content-length'] = str(len(compressed_body))
        headers.setdefault('vary', 'Accept-Encoding')

        # Log compression ratio
        compression_ratio = (1 - len(compressed_body) / len(body)) * 100
        logger.debug(
            f"Compressed response: {len(body)} -> {len(compressed_body)} bytes "
            f"({compression_ratio:.1f}% reduction) using {compression_type}"
        )

        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=dict(headers),
            media_type=response.media_type
        )

    async def _compress_streaming_response(
            self,
            response: StreamingResponse,
            compression_type: str
    ) -> StreamingResponse:
        """Compress a streaming response"""

        async def compressed_stream():
            if compression_type == 'gzip':
                buffer = io.BytesIO()
                with gzip.GzipFile(mode='wb', fileobj=buffer, compresslevel=self.compression_level) as gz:
                    async for chunk in response.body_iterator:
                        gz.write(chunk)
                        if buffer.tell() > 0:
                            buffer.seek(0)
                            yield buffer.read()
                            buffer.truncate(0)
                            buffer.seek(0)

                    # Flush remaining data
                    gz.flush()
                    buffer.seek(0)
                    remaining = buffer.read()
                    if remaining:
                        yield remaining

            elif compression_type == 'br' and BROTLI_AVAILABLE:
                compressor = brotli.Compressor(quality=self.compression_level)
                async for chunk in response.body_iterator:
                    compressed = compressor.process(chunk)
                    if compressed:
                        yield compressed

                # Finish compression
                remaining = compressor.finish()
                if remaining:
                    yield remaining

        # Update headers
        headers = MutableHeaders(response.headers)
        headers['content-encoding'] = compression_type
        headers.setdefault('vary', 'Accept-Encoding')
        # Remove content-length as it will change
        if 'content-length' in headers:
            del headers['content-length']

        return StreamingResponse(
            compressed_stream(),
            status_code=response.status_code,
            headers=dict(headers),
            media_type=response.media_type
        )