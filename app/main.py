import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, setup_logging
from app.database import init_db, close_db
from app.routers import inventory, backups, dashboard

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    settings = get_settings()
    setup_logging(settings)

    logger.info("Initializing database...")
    await init_db(settings)
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Closing database connections...")
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Air-Gapped Network Config Fortress",
    description="Backup, version, and monitor network device configurations",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "agncf"}


@app.get("/", response_class=HTMLResponse)
async def root():
    """Render root page with links."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AGNCF - Home</title>
        <style>
            body {
                font-family: sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            h1 { color: #1e3c72; }
            ul { list-style: none; padding: 0; }
            li { margin: 10px 0; }
            a {
                display: inline-block;
                padding: 10px 20px;
                background: #2a5298;
                color: white;
                text-decoration: none;
                border-radius: 4px;
            }
            a:hover { background: #1e3c72; }
        </style>
    </head>
    <body>
        <h1>Air-Gapped Network Config Fortress</h1>
        <p>Backup, version, and monitor configurations from network devices in air-gapped environments.</p>
        <ul>
            <li><a href="/dashboard">Dashboard</a></li>
            <li><a href="/inventory">Inventory</a></li>
            <li><a href="/api/docs">API Documentation</a></li>
        </ul>
    </body>
    </html>
    """


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page():
    """Render inventory management page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AGNCF - Inventory</title>
        <style>
            {css}
        </style>
    </head>
    <body>
        <div class="container">
            <header class="header">
                <h1>Inventory Management</h1>
                <nav class="nav">
                    <a href="/" class="nav-link">Home</a>
                    <a href="/dashboard" class="nav-link">Dashboard</a>
                    <a href="/api/docs" class="nav-link">API</a>
                </nav>
            </header>
            <main class="main">
                <section class="section">
                    <h2>Sites</h2>
                    <div id="sites"></div>
                </section>
                <section class="section">
                    <h2>Devices</h2>
                    <div id="devices"></div>
                </section>
            </main>
        </div>
        <script>
            {js}
        </script>
    </body>
    </html>
    """.format(css=get_inventory_css(), js=get_inventory_js())


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_details_page(job_id: int):
    """Render job details page with live progress."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AGNCF - Job {job_id}</title>
        <style>
            {get_job_css()}
        </style>
    </head>
    <body>
        <div class="container">
            <header class="header">
                <h1>Backup Job {job_id}</h1>
                <nav class="nav">
                    <a href="/" class="nav-link">Home</a>
                    <a href="/dashboard" class="nav-link">Dashboard</a>
                </nav>
            </header>
            <main class="main">
                <section class="section">
                    <h2>Progress</h2>
                    <div class="progress-container">
                        <div id="progress-bar" class="progress-bar"></div>
                    </div>
                    <p id="progress-text">Loading...</p>
                </section>
                <section class="section">
                    <h2>Status</h2>
                    <pre id="status-log"></pre>
                </section>
            </main>
        </div>
        <script>
            const jobId = {job_id};
            {get_job_js()}
        </script>
    </body>
    </html>
    """


# Include routers
app.include_router(inventory.router)
app.include_router(backups.router)
app.include_router(dashboard.router)


def get_inventory_css() -> str:
    """Return bundled CSS for inventory page."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
        }
        .container { min-height: 100vh; display: flex; flex-direction: column; }
        .header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 { font-size: 2rem; margin-bottom: 1rem; }
        .nav { display: flex; gap: 1rem; }
        .nav-link {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
        }
        .nav-link:hover { background: rgba(255,255,255,0.2); }
        .main { flex: 1; padding: 2rem; }
        .section {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
        }
        .section h2 { color: #1e3c72; margin-bottom: 1rem; }
    """


def get_inventory_js() -> str:
    """Return bundled JavaScript for inventory page."""
    return """
        async function loadInventory() {
            try {
                const sitesResponse = await fetch('/api/sites');
                const sites = await sitesResponse.json();
                document.getElementById('sites').innerHTML = sites
                    .map(s => `<div><strong>${s.name}</strong> (${s.code})</div>`)
                    .join('');
            } catch (e) {
                console.error('Failed to load sites:', e);
            }
        }
        document.addEventListener('DOMContentLoaded', loadInventory);
    """


def get_job_css() -> str:
    """Return bundled CSS for job page."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
        }
        .container { min-height: 100vh; display: flex; flex-direction: column; }
        .header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 { font-size: 2rem; margin-bottom: 1rem; }
        .nav { display: flex; gap: 1rem; }
        .nav-link {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
        }
        .nav-link:hover { background: rgba(255,255,255,0.2); }
        .main { flex: 1; padding: 2rem; }
        .section {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
        }
        .section h2 { color: #1e3c72; margin-bottom: 1rem; }
        .progress-container {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 1rem;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #2a5298, #1e3c72);
            width: 0%;
            transition: width 0.3s ease;
        }
        #status-log {
            background: #f0f0f0;
            padding: 1rem;
            border-radius: 4px;
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.9rem;
        }
    """


def get_job_js() -> str:
    """Return bundled JavaScript for job page."""
    return """
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${protocol}//${window.location.host}/ws/job/${jobId}`);

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateProgress(data);
            };

            ws.onerror = function(event) {
                console.error('WebSocket error:', event);
                document.getElementById('progress-text').textContent = 'Connection error';
            };

            ws.onclose = function(event) {
                console.log('WebSocket closed');
                setTimeout(loadJobDetails, 2000);
            };
        }

        function updateProgress(data) {
            const percentage = (data.completed / data.total) * 100;
            document.getElementById('progress-bar').style.width = percentage + '%';
            document.getElementById('progress-text').textContent =
                `${data.completed}/${data.total} complete (${data.failed} failed) - ${data.status}`;
        }

        async function loadJobDetails() {
            try {
                const response = await fetch(`/api/backups/jobs/${jobId}`);
                const job = await response.json();
                updateProgress({
                    completed: job.completed_devices,
                    total: job.total_devices,
                    failed: job.failed_devices,
                    status: job.status
                });
            } catch (e) {
                console.error('Failed to load job details:', e);
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            loadJobDetails();
            connectWebSocket();
        });
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
