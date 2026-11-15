from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import jobs

router = APIRouter(prefix="/explore")


class AreaRequest(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    label: str | None = Field(default=None, max_length=60)


def _raise(error: jobs.JobRejected):
    raise HTTPException(status_code=error.status, detail={"code": "screening_rejected" if error.status != 404 else "job_not_found", "message": str(error)}) from None


@router.post("/preflight")
def preflight(area: AreaRequest):
    try:
        return jobs.preflight(area.lat, area.lon)
    except jobs.JobRejected as error:
        _raise(error)


@router.post("/jobs", status_code=202)
def submit(area: AreaRequest, request: Request):
    try:
        return jobs.submit(area.lat, area.lon, area.label, request.client.host if request.client else "unknown")
    except jobs.JobRejected as error:
        _raise(error)


@router.get("/jobs")
def recent():
    return jobs.recent()


@router.get("/jobs/{job_id}")
def status(job_id: str):
    try:
        return jobs.load(job_id)
    except jobs.JobRejected as error:
        _raise(error)


@router.get("/jobs/{job_id}/imagery.png", include_in_schema=False)
def imagery(job_id: str):
    try:
        job = jobs.load(job_id)
    except jobs.JobRejected as error:
        _raise(error)
    path = jobs.WORK_DIR / job["job_id"] / "sentinel.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "imagery_unavailable", "message": "No imagery for this job"})
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
