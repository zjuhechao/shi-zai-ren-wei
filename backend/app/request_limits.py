"""Bound incoming bodies before FastAPI/multipart allocates or validates them."""
from __future__ import annotations

from starlette.responses import JSONResponse
from .safety import MAX_IMAGE_BODY_BYTES, MAX_JSON_BODY_BYTES


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        maximum = MAX_IMAGE_BODY_BYTES if scope["path"] == "/api/vision/analyze" else MAX_JSON_BODY_BYTES
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers[b"content-length"]) if b"content-length" in headers else None
            if length is not None and length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "无效的请求长度"}, status_code=400)(scope, receive, send)
        if length is not None and length > maximum:
            return await JSONResponse({"detail": "请求体超过本地原型大小限制"}, status_code=413)(scope, receive, send)
        messages, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > maximum:
                return await JSONResponse({"detail": "请求体超过本地原型大小限制"}, status_code=413)(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break
        async def bounded_receive():
            return messages.pop(0) if messages else await receive()
        return await self.app(scope, bounded_receive, send)
