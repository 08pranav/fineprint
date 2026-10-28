"""HTTP API and static web UI. Run with:  uvicorn fineprint.api:app --reload"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, service
from .config import get_settings
from .ingest.loader import LoadError, load_upload
from .llm.client import get_llm
from .qa.chat import answer
from .schemas import AnalyzeRequest, AskRequest, Language, Level, LoanContext, RiskFlag

settings = get_settings()
app = FastAPI(title="FinePrint", version=__version__)
app.state.llm = get_llm(settings)

# --- A small per-visitor rate limit, so a public deployment cannot run up the model bill. ---------------
_WINDOW_S, _MAX_CALLS = 600, 40
_calls: dict[str, deque] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    key = request.client.host if request.client else "local"
    now = time.monotonic()
    q = _calls[key]
    while q and now - q[0] > _WINDOW_S:
        q.popleft()
    if len(q) >= _MAX_CALLS:
        raise HTTPException(429, "Too many requests from this device. Wait a few minutes, then try again.")
    q.append(now)


def _bad_input(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


# --- API ------------------------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    llm = app.state.llm
    return {"status": "ok", "version": __version__, "model": getattr(llm, "name", None), "mode": "hybrid" if llm else "rules"}


def _samples_index() -> list[dict]:
    path = settings.samples_dir / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@app.get("/api/samples")
def samples():
    return [{k: s[k] for k in ("id", "title", "doc_type", "description")} for s in _samples_index()]


@app.get("/api/samples/{sample_id}")
def sample(sample_id: str):
    for s in _samples_index():
        if s["id"] == sample_id:
            return {"id": s["id"], "title": s["title"], "text": (settings.samples_dir / s["file"]).read_text(encoding="utf-8")}
    raise HTTPException(404, "That sample does not exist.")


@app.post("/api/extract")
async def extract(request: Request, file: UploadFile | None = File(default=None), text: str | None = Form(default=None)):
    """Step 1: read the upload or pasted text, mask personal data, count clauses, pre-fill numbers."""
    _rate_limit(request)
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"This file is {len(data) / 1048576:.1f} MB. The limit is {settings.max_upload_mb} MB.")
        try:
            text = load_upload(file.filename, data)
        except LoadError as exc:
            raise _bad_input(exc)
    if not text:
        raise HTTPException(400, "Add a document first: upload a PDF or text file, or paste the text.")
    try:
        result = service.prepare(text)
    except service.InputError as exc:
        raise _bad_input(exc)
    result["context"] = result["context"].model_dump()
    return result


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, request: Request):
    _rate_limit(request)
    try:
        return service.analyze(req, app.state.llm)
    except service.InputError as exc:
        raise _bad_input(exc)


class RecalcRequest(BaseModel):
    text: str
    context: LoanContext
    flags: list[RiskFlag]
    level: Level = "standard"


@app.post("/api/recalculate")
def recalculate(req: RecalcRequest):
    try:
        flags, notes = service.recalculate(req.text, req.flags, req.context, req.level)
    except service.InputError as exc:
        raise _bad_input(exc)
    return {"flags": flags, "warnings": notes}


class ExplainRequest(BaseModel):
    context: LoanContext
    flags: list[RiskFlag]
    level: Level = "standard"
    language: Language = "en"


@app.post("/api/explain")
def explain(req: ExplainRequest, request: Request):
    _rate_limit(request)
    flags, warnings, readability = service.re_explain(req.flags, req.context, req.level, req.language, app.state.llm)
    return {"flags": flags, "warnings": warnings, "readability": readability}


@app.post("/api/ask")
def ask(req: AskRequest, request: Request):
    _rate_limit(request)
    q = req.question.strip()
    if len(q) < 3:
        raise HTTPException(400, "Type a question of at least a few words.")
    if len(q) > 500:
        raise HTTPException(400, "Keep the question under 500 characters.")
    try:
        service.check_length(req.text)
    except service.InputError as exc:
        raise _bad_input(exc)
    return answer(q, req.text, llm=app.state.llm, language=req.language)


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": "Something failed on the server while doing this. Try again; if it keeps failing, try a shorter document."})


# --- Web UI ---------------------------------------------------------------------------------------------
if settings.web_dir.exists():
    app.mount("/static", StaticFiles(directory=settings.web_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(settings.web_dir / "index.html")
