import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings, setup_logging
from app.database import init_db, close_db
from app.routers import inventory, backups, dashboard

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    logger.info("Initialising database …")
    await init_db(settings)
    logger.info("Database ready")
    yield
    logger.info("Shutting down …")
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "agncf"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("base.html", {
        "request": request,
        "page": "home",
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", {"request": request})


@app.get("/diff", response_class=HTMLResponse)
async def diff_page(request: Request):
    return templates.TemplateResponse("diff_view.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
