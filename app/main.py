"""Main FastAPI application."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.auth import router as auth_router
from app.routes.mail_agent import router as mail_agent_router
from app.routes.autonomous_agent import router as autonomous_agent_router
from app.routes.langgraph_agent import router as langgraph_agent_router
from app.routes.research import router as research_router
from app.routes.follow_ups import router as follow_ups_router

from app.config.settings import get_settings

# Global SSL disable if configured
_settings = get_settings()
if not _settings.verify_ssl:
    import ssl
    import urllib3
    import os

    # 1. Patch ssl.create_default_context — this is what httpx calls internally.
    _original_create_default_context = ssl.create_default_context

    def _unverified_context(*args, **kwargs):
        ctx = _original_create_default_context(*args, **kwargs)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ssl.create_default_context = _unverified_context

    # 2. Also override _create_default_https_context (covers stdlib urllib)
    ssl._create_default_https_context = ssl._create_unverified_context

    # 3. Suppress warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # 4. Env vars for curl/requests/grpc
    os.environ["CURL_CA_BUNDLE"] = ""
    os.environ["REQUESTS_CA_BUNDLE"] = ""
    os.environ["SSL_CERT_FILE"] = ""
    os.environ["PYTHONHTTPSVERIFY"] = "0"

    print("[WARNING] SSL VERIFICATION IS GLOBALLY DISABLED")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s %(levelname)-8s %(message)s",
)

app = FastAPI(
    title="Mailing Agent API",
    description=(
        "Automated personalised email generation and sending agent. "
        "Fetches company data from Supabase, generates tailored emails via LLM, "
        "creates Gmail drafts, and manages an approval flow before sending."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(mail_agent_router)
app.include_router(autonomous_agent_router)
app.include_router(langgraph_agent_router)
app.include_router(research_router)
app.include_router(follow_ups_router)


@app.get("/health")
def health():
    return {"status": "ok"}
