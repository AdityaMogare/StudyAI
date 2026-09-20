#!/usr/bin/env python3
"""Local HTTP runtime — same handlers as Lambda, no AWS required.

Exposes:
  POST /interactions  → resolution.handler (Discord Interactions Endpoint)
  POST /ingestion     → ingestion.handler  (gateway relay)
  GET  /health

Usage:
  set -a && source .env && set +a
  export EMBEDDING_MODE=local
  python local_server/app.py
  # In another terminal: cloudflared tunnel --url http://127.0.0.1:8080
  # Set Discord Interactions URL to https://<tunnel>/interactions
  # export INGESTION_URL=http://127.0.0.1:8080/ingestion
  # export RESOLUTION_URL=http://127.0.0.1:8080/interactions
  # make gateway
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from ingestion.handler import handler as ingestion_handler  # noqa: E402
from resolution.handler import handler as resolution_handler  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studyai.local")

app = FastAPI(title="StudyAI Local Runtime", version="0.1.0")


def _to_apigw_event(request: Request, body: bytes) -> dict:
    """Shape a FastAPI request like API Gateway HTTP API / REST proxy event."""
    headers = {k: v for k, v in request.headers.items()}
    return {
        "resource": request.url.path,
        "path": request.url.path,
        "httpMethod": request.method,
        "headers": headers,
        "multiValueHeaders": {k: [v] for k, v in headers.items()},
        "queryStringParameters": dict(request.query_params) or None,
        "pathParameters": None,
        "stageVariables": None,
        "requestContext": {
            "resourcePath": request.url.path,
            "httpMethod": request.method,
            "path": request.url.path,
            "stage": "local",
            "requestId": "local",
            "identity": {"sourceIp": request.client.host if request.client else "127.0.0.1"},
        },
        "body": body.decode("utf-8") if body else "",
        "isBase64Encoded": False,
    }


def _from_lambda_response(result: dict) -> Response:
    status = int(result.get("statusCode", 200))
    headers = result.get("headers") or {"Content-Type": "application/json"}
    body = result.get("body", "")
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return Response(content=body, status_code=status, media_type=headers.get("Content-Type", "application/json"))


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "mode": "local",
        "embedding_mode": os.environ.get("EMBEDDING_MODE", "auto"),
    }


@app.post("/interactions")
async def interactions(request: Request) -> Response:
    raw = await request.body()
    event = _to_apigw_event(request, raw)
    try:
        result = resolution_handler(event, None)
    except Exception:
        logger.exception("resolution handler failed")
        return JSONResponse({"error": "internal_error"}, status_code=500)
    return _from_lambda_response(result)


@app.post("/ingestion")
async def ingestion(request: Request) -> Response:
    raw = await request.body()
    event = _to_apigw_event(request, raw)
    try:
        result = ingestion_handler(event, None)
    except Exception:
        logger.exception("ingestion handler failed")
        return JSONResponse({"error": "internal_error"}, status_code=500)
    return _from_lambda_response(result)


def main() -> None:
    import uvicorn

    host = os.environ.get("LOCAL_HOST", "127.0.0.1")
    port = int(os.environ.get("LOCAL_PORT", "8080"))
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")
    logger.info("Starting StudyAI local runtime on http://%s:%s", host, port)
    logger.info("Discord Interactions URL should be https://<tunnel>/interactions")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
