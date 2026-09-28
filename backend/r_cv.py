import io
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from pypdf import PdfReader
from docx import Document
from core import (db, iso, uid, NOID, get_current_user, inc_usage, put_file, get_file, audit, logger,
                   get_plan, usage_of)
from ai import llm_json

router = APIRouter(prefix="/api")
MAX_SIZE = 8 * 1024 * 1024


def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        d = Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    raise HTTPException(400, "Only PDF or DOCX files are supported")


async def get_master(user_id):
    return await db.cv_versions.find_one({"user_id": user_id, "is_master": True}, NOID)


async def parse_allowance(user):
    """Return (allowed, message) for spending an AI parse on this user's CV.

    The plan limit meters the expensive AI parse, not the upload itself. The master CV feeds
    every AI review and tailored CV, so a user who is out of parses must still be able to
    upload, keep the file, and fill the profile in by hand.
    """
    plan = await get_plan(user)
    limit = plan["limits"].get("cvs", -1)
    if limit < 0:
        return True, None
    used = (await usage_of(user["user_id"]))["parses"]
    if used < limit:
        return True, None
    return False, (f"You've used all {limit} AI CV parses in the {plan['name']} plan this month. "
                   "Your file was saved — fill the details in by hand, or upgrade from Plan & usage.")


@router.post("/cv/upload")
async def upload_cv(file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "File too large (max 8 MB)")
    text = extract_text(data, file.filename or "")
    if len(text.strip()) < 80:
        raise HTTPException(400, "Could not read text from this file. Try a text-based PDF or DOCX.")
    # Store the file before parsing. The master CV gates every AI feature in the app, so a
    # provider outage or an exhausted allowance must not turn an upload into a total loss --
    # the user keeps the file, fills the profile in by hand, and can retry parsing later.
    f = await put_file(user["user_id"], data, file.filename, file.content_type or "application/octet-stream", kind="cv")
    parsed, meta, parse_error = None, None, None
    allowed, limit_note = await parse_allowance(user)
    if not allowed:
        parse_error = limit_note
    else:
        try:
            parsed, meta = await llm_json("parse_cv", text[:30000], user["user_id"])
            await inc_usage(user["user_id"], "parses")
        except Exception as e:
            # Surface something the admin can act on rather than a raw upstream payload.
            parse_error = f"AI parsing unavailable ({str(e)[:120]}). Your file was saved — fill the details in by hand, or retry parsing later."
            logger.warning(f"CV parse failed for {user['user_id']}: {e}")
    await audit(user["user_id"], "cv_uploaded", {"file_id": f["file_id"], "parsed": parsed is not None})
    return {"file_id": f["file_id"], "filename": f["filename"], "parsed": parsed, "ai": meta, "parse_error": parse_error}


class ParseIn(BaseModel):
    file_id: str


@router.post("/cv/parse")
async def reparse_cv(body: ParseIn, user=Depends(get_current_user)):
    """Re-run AI parsing on an already-uploaded file, without uploading it again."""
    doc = await db.files.find_one({"file_id": body.file_id, "user_id": user["user_id"], "is_deleted": False}, NOID)
    if not doc:
        raise HTTPException(404, "File not found")
    allowed, limit_note = await parse_allowance(user)
    if not allowed:
        raise HTTPException(402, limit_note)
    data, _ = await get_file(body.file_id, user["user_id"])
    try:
        text = extract_text(data, doc.get("filename") or "")
    except HTTPException:
        raise
    if len(text.strip()) < 80:
        raise HTTPException(400, "Could not read text from this file. Try a text-based PDF or DOCX.")
    try:
        parsed, meta = await llm_json("parse_cv", text[:30000], user["user_id"])
    except Exception as e:
        raise HTTPException(502, f"AI parsing failed: {str(e)[:150]}")
    await inc_usage(user["user_id"], "parses")
    return {"file_id": body.file_id, "parsed": parsed, "ai": meta}


class VersionIn(BaseModel):
    data: dict
    file_id: Optional[str] = None
    note: str = ""


@router.post("/cv/versions")
async def save_version(body: VersionIn, user=Depends(get_current_user)):
    last = await db.cv_versions.find_one({"user_id": user["user_id"]}, NOID, sort=[("version", -1)])
    v = (last or {}).get("version", 0) + 1
    await db.cv_versions.update_many({"user_id": user["user_id"]}, {"$set": {"is_master": False}})
    doc = {"cv_version_id": uid("cv_"), "user_id": user["user_id"], "version": v, "data": body.data,
           "file_id": body.file_id or (last or {}).get("file_id"), "note": body.note[:200], "is_master": True, "created_at": iso()}
    await db.cv_versions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/cv")
async def get_cv(user=Depends(get_current_user)):
    versions = await db.cv_versions.find({"user_id": user["user_id"]}, {"_id": 0, "data": 0}).sort("version", -1).to_list(100)
    return {"master": await get_master(user["user_id"]), "versions": versions}


@router.get("/cv/versions/{vid}")
async def get_version(vid: str, user=Depends(get_current_user)):
    v = await db.cv_versions.find_one({"cv_version_id": vid, "user_id": user["user_id"]}, NOID)
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@router.post("/cv/versions/{vid}/restore")
async def restore(vid: str, user=Depends(get_current_user)):
    v = await get_version(vid, user)
    return await save_version(VersionIn(data=v["data"], file_id=v.get("file_id"), note=f"Restored from v{v['version']}"), user)


@router.get("/files/{file_id}")
async def download(file_id: str, user=Depends(get_current_user)):
    data, doc = await get_file(file_id, user["user_id"])
    return Response(content=data, media_type=doc["content_type"], headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'})
