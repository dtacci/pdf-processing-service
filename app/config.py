"""Runtime configuration, sourced entirely from the environment (12-factor).

Kept dependency-light on purpose: a frozen dataclass over ``os.environ`` so the
container image is self-describing (build metadata is baked in at image-build
time) without pulling a settings library into the runtime layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable view of the process environment."""

    app_version: str  # semantic version of the release
    git_sha: str  # commit the image was built from (baked at build time)
    build_time: str  # ISO-8601 image build timestamp (baked at build time)
    port: int  # port uvicorn binds
    log_level: str  # root log level


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process.

    ``GIT_SHA`` / ``BUILD_TIME`` / ``APP_VERSION`` are populated by the Docker
    build (see the Dockerfile build args); they default to ``*-dev``/``unknown``
    for host-local runs so ``/version`` is always answerable.
    """
    return Settings(
        app_version=os.getenv("APP_VERSION", "0.0.0-dev"),
        git_sha=os.getenv("GIT_SHA", "unknown"),
        build_time=os.getenv("BUILD_TIME", "unknown"),
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
