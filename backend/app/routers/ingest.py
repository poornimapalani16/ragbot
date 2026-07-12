import os
import uuid

from fastapi import APIRouter, UploadFile, File, Form, Header

from app.config import settings
from app.database import bot_registry
from app.ingestion import ingest_file, ingest_url, validate_file
from app.models import IngestResponse, IngestURLRequest
from app.utils.exceptions import InvalidAPIKeyError
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


def _authenticate(bot_id: str, x_api_key: str | None):
    if not x_api_key:
        raise InvalidAPIKeyError()
    return bot_registry.verify_api_key(bot_id, x_api_key)


@router.post("/file", response_model=IngestResponse)
async def ingest_file_endpoint(
    bot_id: str = Form(...),
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
):
    _authenticate(bot_id, x_api_key)

    contents = await file.read()
    ext = validate_file(file.filename, len(contents))

    tmp_name = f"{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(settings.UPLOAD_DIR, tmp_name)
    try:
        with open(tmp_path, "wb") as f:
            f.write(contents)
        chunks_added = ingest_file(bot_id, tmp_path, file.filename)
    finally:
        # Always clean up temp file, even if ingestion raised.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return IngestResponse(bot_id=bot_id, chunks_added=chunks_added, source=file.filename)


@router.post("/url", response_model=IngestResponse)
async def ingest_url_endpoint(payload: IngestURLRequest, x_api_key: str | None = Header(default=None)):
    _authenticate(payload.bot_id, x_api_key)
    chunks_added = ingest_url(payload.bot_id, str(payload.url))
    return IngestResponse(bot_id=payload.bot_id, chunks_added=chunks_added, source=str(payload.url))
