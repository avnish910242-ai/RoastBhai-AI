
"""FastAPI application for RoastBhai AI with account authentication."""

import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pwdlib import PasswordHash

from . import ai, database


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = (PROJECT_ROOT / "frontend").resolve()

if not FRONTEND.is_dir():
    raise RuntimeError(f"Frontend directory does not exist: {FRONTEND}")


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://127.0.0.1:8002/auth/google/callback",
).strip()

SESSION_COOKIE = "roastbhai_session"
OAUTH_STATE_COOKIE = "roastbhai_oauth_state"
SESSION_DAYS = 30

password_hash = PasswordHash.recommended()


def cookie_secure() -> bool:
    setting = os.getenv("ROASTBHAI_COOKIE_SECURE", "").lower().strip()

    if setting in {"true", "1", "yes"}:
        return True

    if setting in {"false", "0", "no"}:
        return False

    return GOOGLE_REDIRECT_URI.startswith("https://")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    return expires.strftime("%Y-%m-%d %H:%M:%S")


def create_login_session(response, user_id: int):
    token = secrets.token_urlsafe(48)

    database.create_session(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=session_expiry(),
    )

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_login_session(response, request: Request):
    token = request.cookies.get(SESSION_COOKIE)

    if token:
        database.delete_session(hash_token(token))

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
    )


def require_same_origin(request: Request):
    """Allow local and configured production same-origin requests."""

    origin = request.headers.get("origin")

    if not origin:
        return

    origin = origin.rstrip("/")

    # Allow the actual origin used to open this application.
    allowed_origins = {
        str(request.base_url).rstrip("/"),
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://127.0.0.1:8002",
        "http://localhost:8002",
    }

    # Also allow the configured Google OAuth origin.
    if GOOGLE_REDIRECT_URI:
        parsed = urlparse(GOOGLE_REDIRECT_URI)

        if parsed.scheme and parsed.netloc:
            allowed_origins.add(
                f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            )

    if origin not in allowed_origins:
        raise HTTPException(
            status_code=403,
            detail="Invalid request origin.",
        )


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Please login first.",
        )

    user = database.get_session_user(hash_token(token))

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please login again.",
        )

    return user


@asynccontextmanager
async def lifespan(_app):
    database.init_db()
    database.delete_expired_sessions()
    yield


app = FastAPI(
    title="RoastBhai AI",
    version="1.0.0",
    lifespan=lifespan,
)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: int | None = None


# -------------------------
# Health and authentication
# -------------------------

@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(user=Depends(current_user)):
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }


@app.post("/api/auth/signup")
async def signup(data: SignupRequest, request: Request):
    require_same_origin(request)

    email = data.email.strip().lower()
    name = data.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Please enter your name.",
        )

    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(
            status_code=422,
            detail="Enter a valid email address.",
        )

    if database.get_user_by_email(email):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists. Please login.",
        )

    hashed = password_hash.hash(data.password)

    try:
        user_id = database.create_user(email, name, hashed)
    except Exception:
        raise HTTPException(
            status_code=409,
            detail="Could not create account. This email may already be registered.",
        ) from None

    response = JSONResponse({"ok": True})
    create_login_session(response, user_id)

    return response


@app.post("/api/auth/login")
async def login(data: LoginRequest, request: Request):
    require_same_origin(request)

    user = database.get_user_by_email(data.email.strip().lower())

    if (
        not user
        or not user.get("password_hash")
        or not password_hash.verify(data.password, user["password_hash"])
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

    response = JSONResponse({"ok": True})
    create_login_session(response, user["id"])

    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    require_same_origin(request)

    response = RedirectResponse("/login", status_code=303)
    clear_login_session(response, request)

    return response


# -------------------------
# Google OAuth
# -------------------------

@app.get("/auth/google")
async def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Google Login is not configured on the server.",
        )

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }

    response = RedirectResponse(
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(params),
        status_code=302,
    )

    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=600,
        path="/",
    )

    return response


@app.get("/auth/google/callback")
async def google_callback(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Google Login is not configured.",
        )

    returned_state = request.query_params.get("state", "")
    saved_state = request.cookies.get(OAUTH_STATE_COOKIE, "")

    if (
        not returned_state
        or not saved_state
        or not secrets.compare_digest(returned_state, saved_state)
    ):
        raise HTTPException(
            status_code=400,
            detail="Google login state check failed.",
        )

    code = request.query_params.get("code")

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Google did not return an authorization code.",
        )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            token_response.raise_for_status()
            token_data = token_response.json()

            access_token = token_data.get("access_token")

            if not access_token:
                raise HTTPException(
                    status_code=502,
                    detail="Google did not return an access token.",
                )

            profile_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
            )

            profile_response.raise_for_status()
            profile = profile_response.json()

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Google sign-in failed. Please try again.",
        ) from None

    email = str(profile.get("email", "")).strip().lower()
    google_sub = str(profile.get("sub", "")).strip()
    name = str(profile.get("name", "")).strip()
    email_verified = profile.get("email_verified") is True

    if not email or not google_sub or not email_verified:
        raise HTTPException(
            status_code=400,
            detail="Google account email could not be verified.",
        )

    user_id = database.get_or_create_google_user(
        google_sub=google_sub,
        email=email,
        name=name or email.split("@")[0],
    )

    response = RedirectResponse("/", status_code=303)

    response.delete_cookie(
        OAUTH_STATE_COOKIE,
        path="/",
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
    )

    create_login_session(response, user_id)

    return response


# -------------------------
# User-owned chat history
# -------------------------

@app.get("/api/conversations")
async def conversations(user=Depends(current_user)):
    return database.list_conversations(user["id"])


@app.get("/api/conversations/{conversation_id}")
async def conversation(
    conversation_id: int,
    user=Depends(current_user),
):
    item = database.get_conversation(
        conversation_id,
        user["id"],
    )

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    return item


@app.delete("/api/conversations")
async def clear_conversations(
    request: Request,
    user=Depends(current_user),
):
    require_same_origin(request)

    database.delete_all_conversations(user["id"])

    return {"deleted": True}


@app.delete("/api/conversations/{conversation_id}")
async def remove_conversation(
    conversation_id: int,
    request: Request,
    user=Depends(current_user),
):
    require_same_origin(request)

    if not database.delete_conversation(
        conversation_id,
        user["id"],
    ):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    return {"deleted": True}


# -------------------------
# Gemini chat
# -------------------------

@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    http_request: Request,
    user=Depends(current_user),
):
    require_same_origin(http_request)

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Please enter a message.",
        )

    user_id = user["id"]
    conversation_id = request.conversation_id

    if conversation_id is None:
        title = message.replace("\n", " ")[:48]

        if len(message) > 48:
            title += "…"

        conversation_id = database.create_conversation(
            user_id,
            title,
        )

    existing = database.get_conversation(
        conversation_id,
        user_id,
    )

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found. Start a new chat.",
        )

    context = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in existing["messages"][-20:]
    ]

    database.add_message(
        conversation_id,
        user_id,
        "user",
        message,
    )

    context.append({
        "role": "user",
        "content": message,
    })

    try:
        reply = await ai.generate_reply(context)

    except ai.AIConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
            headers={
                "X-Conversation-Id": str(conversation_id)
            },
        ) from exc

    except ai.AIServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
            headers={
                "X-Conversation-Id": str(conversation_id)
            },
        ) from exc

    database.add_message(
        conversation_id,
        user_id,
        "assistant",
        reply,
    )

    return {
        "conversation_id": conversation_id,
        "reply": reply,
    }


# -------------------------
# Frontend pages
# -------------------------

@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/login")
async def login_page():
    return FileResponse(FRONTEND / "login.html")


app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND), html=True),
    name="frontend",
)
