import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import update

from app.config import get_settings, setup_logging
from app.database import init_db, close_db, get_session_factory
from app.models import BackupJob, BackupJobStatus
from app.routers import inventory, backups, dashboard
from app.routers import schedules as schedules_router
from app.core.scheduler import load_and_start, stop as stop_scheduler

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    logger.info("Initialising database …")
    await init_db(settings)
    logger.info("Database ready")

    # Mark any jobs left in RUNNING state as FAILED — they were orphaned by a restart.
    async with get_session_factory()() as session:
        result = await session.execute(
            update(BackupJob)
            .where(BackupJob.status == BackupJobStatus.RUNNING)
            .values(status=BackupJobStatus.FAILED, completed_at=datetime.utcnow())
            .returning(BackupJob.id)
        )
        orphaned = result.scalars().all()
        await session.commit()
        if orphaned:
            logger.warning("Marked %d orphaned RUNNING job(s) as FAILED: %s", len(orphaned), orphaned)

    # Start APScheduler and load recurring backup schedules
    await load_and_start()

    yield

    logger.info("Shutting down …")
    stop_scheduler()
    await close_db()


app = FastAPI(
    title="Air-Gapped Network Config Fortress",
    description="Backup, version, and monitor network device configurations in air-gapped environments.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.include_router(inventory.router)
app.include_router(backups.router)
app.include_router(dashboard.router)
app.include_router(schedules_router.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "agncf"}


@app.get("/")
async def home():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", {"request": request})


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail_page(request: Request, job_id: int):
    return templates.TemplateResponse("job_detail.html", {"request": request, "job_id": job_id})


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    return templates.TemplateResponse("config_view.html", {"request": request})


@app.get("/diff", response_class=HTMLResponse)
async def diff_page(request: Request):
    return templates.TemplateResponse("diff_view.html", {"request": request})


@app.get("/device-status", response_class=HTMLResponse)
async def device_status_page(request: Request):
    return templates.TemplateResponse("device_status.html", {"request": request})


@app.get("/schedules", response_class=HTMLResponse)
async def schedules_page(request: Request):
    return templates.TemplateResponse("schedules.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
