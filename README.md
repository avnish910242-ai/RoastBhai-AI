# RoastBhai AI

A standalone Hinglish AI chat app built with a plain HTML/CSS/JavaScript frontend, FastAPI, SQLite, and the Google Gemini API.

## Requirements

- Python 3.10 or newer
- A Google AI Studio Gemini API key

## Run on Windows PowerShell

```powershell
Set-Location 'C:\Users\Avnish kumar\OneDrive\Desktop\RoastBhai-AI'
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Set `GEMINI_API_KEY` in the root `.env` file. The default `GEMINI_MODEL` is `gemini-3.5-flash-lite`. Keep `.env` private and never place the key in frontend files.

Open **http://127.0.0.1:8001**. Conversations are stored in `backend/roastbhai.sqlite3` by default. Set `ROASTBHAI_DB_PATH` to move the database.

## API

- `POST /api/chat` — `{ "message": "...", "conversation_id": 1 }` (conversation ID is optional)
- `GET /api/conversations` — list saved chats
- `GET /api/conversations/{id}` — read a saved chat
- `DELETE /api/conversations/{id}` — delete one chat
- `DELETE /api/conversations` — clear all chats
- `GET /api/health` — health check

Roasts are intended to stay playful and friendly. Attachments are not implemented in this version.
