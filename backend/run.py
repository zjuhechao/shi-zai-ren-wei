from __future__ import annotations

import ipaddress
import os
import sys

import uvicorn

from app.config import get_settings


def validate_bind_host(host: str, *, platform: str = sys.platform,
                       allow_container_bind: str | None = None) -> None:
    """Default local entry point must not accidentally expose an unauthenticated app."""
    normalized = host.strip().lower()
    if normalized == "localhost":
        return
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            return
    except ValueError:
        pass
    explicit_container = (allow_container_bind if allow_container_bind is not None
                          else os.environ.get("APP_ALLOW_CONTAINER_BIND", ""))
    if platform.startswith("linux") and normalized == "0.0.0.0" and explicit_container == "true":
        return
    raise ValueError("仅支持回环地址启动。容器内部通配监听须显式启用，且宿主端口仅发布到127.0.0.1；此原型没有公网鉴权。")


if __name__ == "__main__":
    settings = get_settings()
    validate_bind_host(settings.app_host)
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)
