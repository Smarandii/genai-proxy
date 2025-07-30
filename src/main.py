"""
Simple proxy service to forward requests targeting multiple AI APIs.

This FastAPI application listens on arbitrary paths under a root prefix and
forwards each request to a configured upstream service (OpenAI, Gemini or
Grok). It preserves the HTTP method, path, query parameters and request body.

To choose the correct upstream, the server expects the incoming request path
to start with one of the configured prefixes (`/openai/`, `/gemini/` or
`/grok/`). Everything after the prefix is forwarded as-is to the target API.
Requests hitting the root `/` will return a simple status message.

The API keys and base URLs for each upstream are provided via environment
variables. Keys and URLs are optional; if a prefix is used without a
corresponding configuration, the request will be rejected with a 502 error.
"""

import os
from typing import Dict

from fastapi import FastAPI, Request, Response, HTTPException
import httpx

app = FastAPI(title="AI API proxy")


class UpstreamConfig:
    """Configuration for an upstream target."""

    def __init__(self, base_url: str | None, api_key: str | None):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    def is_configured(self) -> bool:
        return bool(self.base_url)


def load_upstreams() -> Dict[str, UpstreamConfig]:
    """Load upstream configurations from environment variables."""
    return {
        "openai": UpstreamConfig(
            os.environ.get("OPENAI_BASE_URL"), os.environ.get("OPENAI_API_KEY")
        ),
        "gemini": UpstreamConfig(
            os.environ.get("GEMINI_BASE_URL"), os.environ.get("GEMINI_API_KEY")
        ),
        "grok": UpstreamConfig(
            os.environ.get("GROK_BASE_URL"), os.environ.get("GROK_API_KEY")
        ),
    }


UPSTREAMS = load_upstreams()


@app.get("/")
async def root() -> dict[str, str]:
    """Return a simple health message."""
    return {"message": "AI proxy is running"}


async def forward_request(prefix: str, request: Request) -> Response:
    """
    Forward an incoming request to the appropriate upstream.

    Args:
        prefix: The path prefix (e.g. "openai", "gemini", "grok").
        request: The FastAPI Request object.

    Returns:
        A FastAPI Response returned from the upstream.

    Raises:
        HTTPException: If the upstream for the given prefix isn't configured.
    """
    upstream = load_upstreams().get(prefix)
    header_key = f"{prefix}-api-key"
    request_api_key = None

    headers = dict(request.headers)
    # Remove host header to let httpx set it correctly
    headers.pop("host", None)

    for k, v in headers.items():
        if k.lower() == header_key.lower():
            request_api_key = v
            break

    if not upstream or not upstream.is_configured():
        raise HTTPException(
            status_code=502,
            detail=f"Upstream for prefix '{prefix}' is not configured",
        )

    # Build the new path by stripping the prefix from the original path
    original_path = request.url.path  # e.g. /openai/v1/chat/completions
    # remove leading '/' and prefix and forward the remainder
    forwarded_path = original_path[len(prefix) + 1 :]  # drop '/openai/'
    url = f"{upstream.base_url}/{forwarded_path.lstrip('/')}"

    # Prepare request options
    method = request.method

    api_key_to_use = request_api_key if request_api_key else upstream.api_key

    # If an API key is available and no Authorization header is set, add it.
    if api_key_to_use and "authorization" not in {h.lower() for h in headers}:
        headers["Authorization"] = f"Bearer {api_key_to_use}"

    # Query params
    params = dict(request.query_params)

    # Body
    body = await request.body()

    # Use httpx to make the forwarded request
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                content=body,
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            # Wrap network exceptions in a 502
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Return the upstream response as a new Response
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={k: v for k, v in resp.headers.items() if k.lower() != "content-encoding"},
        media_type=resp.headers.get("Content-Type"),
    )


@app.api_route("/{prefix}/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def catch_all(prefix: str, rest: str, request: Request) -> Response:
    """
    Catch-all route that forwards any request to the configured upstream.

    This route captures the first path component as ``prefix`` and forwards
    the request using ``forward_request``.
    """
    # Normalize prefix to lowercase to match environment keys
    prefix = prefix.lower()
    return await forward_request(prefix, request)
