"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import Message, Part, Role

try:
    from a2a.types import (
        AgentCard,
        FilePart,
        TaskArtifactUpdateEvent,
        TextPart,
        TransportProtocol,
    )
except ImportError:
    from a2a.compat.v0_3.types import (
        AgentCard,
        FilePart,
        TaskArtifactUpdateEvent,
        TextPart,
        TransportProtocol,
    )
try:
    from a2a.client import create_client
except ImportError:
    create_client = None

try:
    from google.protobuf.json_format import MessageToDict
except ImportError:
    MessageToDict = None

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/710191965618/locations/us-central1/reasoningEngines/7517153741162676224",
)
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_part(p) -> dict | None:
    """Turn a single A2A response part into structured parts for the chat UI."""
    if MessageToDict is not None and hasattr(p, "DESCRIPTOR"):
        p_dict = MessageToDict(p)
    elif hasattr(p, "root"):
        p_dict = p.root if isinstance(p.root, dict) else getattr(p.root, "__dict__", {})
    elif isinstance(p, dict):
        p_dict = p
    else:
        p_dict = getattr(p, "__dict__", {})

    # Check text
    text = p_dict.get("text")
    if text:
        return {"kind": "text", "text": text}

    # Check data (A2UI)
    data_field = p_dict.get("data")
    if isinstance(data_field, dict):
        meta = data_field.get("metadata") or p_dict.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("mimeType") == _A2UI_MIME:
            inner_data = data_field.get("data", data_field)
            return {"kind": "a2ui", "data": inner_data}
        if "beginRendering" in data_field or "surfaceUpdate" in data_field:
            return {"kind": "a2ui", "data": data_field}

    # Check URL / File
    if p_dict.get("url"):
        return {"kind": "text", "text": p_dict["url"]}
    file_obj = p_dict.get("file")
    if isinstance(file_obj, dict) and file_obj.get("uri"):
        return {"kind": "text", "text": file_obj["uri"]}

    return None


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    req_headers = dict(_auth_headers())
    req_headers.setdefault("x-a2a-version", "1.0")

    async with httpx.AsyncClient(headers=req_headers, timeout=120) as client:
        if create_client is not None:
            try:
                from a2a.types import SendMessageRequest
            except ImportError:
                SendMessageRequest = None

            try:
                config = ClientConfig(
                    httpx_client=client,
                    supported_protocol_bindings=[
                        "JSONRPC",
                        "HTTP+JSON",
                    ],
                )
            except TypeError:
                config = ClientConfig(
                    httpx_client=client,
                    supported_transports=[
                        getattr(TransportProtocol, "jsonrpc", "jsonrpc"),
                        getattr(TransportProtocol, "http_json", "http_json"),
                    ],
                )

            a2a_client = await create_client(A2A_BASE, config)
            user_role = getattr(Role, "ROLE_USER", getattr(Role, "user", 1))
            msg = Message(
                message_id=str(uuid.uuid4()),
                role=user_role,
                parts=[Part(text=message)],
                context_id=_contexts.get(user_id) or "",
            )
            req_obj = SendMessageRequest(message=msg) if SendMessageRequest else msg

            async for chunk in a2a_client.send_message(req_obj):
                for field in ("artifact_update", "status_update", "task", "message"):
                    if chunk.HasField(field) and getattr(chunk, field).context_id:
                        _contexts[user_id] = getattr(chunk, field).context_id

                if chunk.HasField("artifact_update"):
                    for p in chunk.artifact_update.artifact.parts:
                        ext = _extract_part(p)
                        if ext:
                            parts.append(ext)
                elif chunk.HasField("task"):
                    for a in chunk.task.artifacts:
                        for p in a.parts:
                            ext = _extract_part(p)
                            if ext:
                                parts.append(ext)
                elif chunk.HasField("message"):
                    for p in chunk.message.parts:
                        ext = _extract_part(p)
                        if ext:
                            parts.append(ext)
        else:
            card = await _get_card(client)
            factory = ClientFactory(
                ClientConfig(
                    supported_transports=[
                        TransportProtocol.jsonrpc,
                        TransportProtocol.http_json,
                    ],
                    httpx_client=client,
                )
            )
            a2a_client = factory.create(card)
            msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=message))],
                context_id=_contexts.get(user_id),
            )
            last_task = None
            got_artifact_update = False
            async for event in a2a_client.send_message(msg):
                if not isinstance(event, tuple):
                    continue
                task, update = event
                if task is not None:
                    last_task = task
                    if getattr(task, "context_id", None):
                        _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    got_artifact_update = True
                    for p in update.artifact.parts:
                        ext = _extract_part(p)
                        if ext:
                            parts.append(ext)
            if not got_artifact_update and last_task is not None:
                for artifact in getattr(last_task, "artifacts", None) or []:
                    for p in artifact.parts:
                        ext = _extract_part(p)
                        if ext:
                            parts.append(ext)

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


# Serve the chat UI (keep this mount last so /chat wins).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
