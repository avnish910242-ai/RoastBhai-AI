
"""FastAPI app and API routes for RoastBhai AI."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, database


FRONTEND = (Path(__file__).resolve().parent.parent / "frontend").resolve()

if not FRONTEND.is_dir():
    raise RuntimeError(f"Frontend directory does not exist: {FRONTEND}")


@asynccontextmanager
async def lifespan(_app):
    database.init_db()
    yield


app = FastAPI(
    title="RoastBhai AI",
    version="1.0.0",
    lifespan=lifespan
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: int | None = None


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/conversations")
async def conversations():
    return database.list_conversations()


@app.get("/api/conversations/{conversation_id}")
async def conversation(conversation_id: int):
    item = database.get_conversation(conversation_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    return item


@app.delete("/api/conversations")
async def clear_conversations():
    database.delete_all_conversations()
    return {"deleted": True}


@app.delete("/api/conversations/{conversation_id}")
async def remove_conversation(conversation_id: int):
    if not database.delete_conversation(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    return {"deleted": True}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Please enter a message."
        )

    conversation_id = request.conversation_id

    if conversation_id is None:
        title = message.replace("\n", " ")[:48]
        if len(message) > 48:
            title += "…"

        conversation_id = database.create_conversation(title)

    existing = database.get_conversation(conversation_id)

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found. Start a new chat."
        )

    # Keep a bounded recent context window.
    context = [
        {"role": m["role"], "content": m["content"]}
        for m in existing["messages"][-20:]
    ]

    database.add_message(conversation_id, "user", message)

    context.append({
        "role": "user",
        "content": message
    })

    try:
        reply = await ai.generate_reply(context)

    except ai.AIConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
            headers={"X-Conversation-Id": str(conversation_id)}
        ) from exc

    except ai.AIServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
            headers={"X-Conversation-Id": str(conversation_id)}
        ) from exc

    database.add_message(conversation_id, "assistant", reply)

    return {
        "conversation_id": conversation_id,
        "reply": reply
    }


# Main Chat Page
@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


# Login Page
@app.get("/login")
async def login():
    return FileResponse(FRONTEND / "login.html")


# Static files: CSS, JavaScript and other frontend assets.
# Keep this mount last.
app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND), html=True),
    name="frontend"
)