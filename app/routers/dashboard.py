import logging
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db_session
from app.models import BackupJob, Device, Site
from app.core.backup_engine import progress_queues

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])

# Global progress tracking
progress_queues = {}


async def get_progress_queue(job_id: int):
    """Get or create progress queue for a job."""
    if job_id not in progress_queues:
        progress_queues[job_id] = asyncio.Queue()
    return progress_queues[job_id]


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(session: AsyncSession = Depends(get_db_session)):
    """Render the dashboard HTML page."""
    result = await session.execute(
        select(BackupJob).order_by(desc(BackupJob.triggered_at)).limit(10)
    )
    recent_jobs = result.scalars().all()

    jobs_html = ""
    for job in recent_jobs:
        status_badge = f'<span class="badge badge-{job.status.value}">{job.status.value}</span>'
        jobs_html += f"""
        <tr>
            <td>{job.id}</td>
            <td>{job.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}</td>
            <td>{job.triggered_by}</td>
            <td>{status_badge}</td>
            <td><span class="progress-text">{job.completed_devices}/{job.total_devices}</span></td>
            <td><a href="/job/{job.id}" class="btn btn-sm btn-primary">Details</a></td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AGNCF Dashboard</title>
        <style>
            {get_dashboard_css()}
        </style>
    </head>
    <body>
        <div class="container">
            <header class="header">
                <h1>Network Configuration Backup Dashboard</h1>
                <nav class="nav">
                    <a href="/" class="nav-link active">Dashboard</a>
                    <a href="/inventory" class="nav-link">Inventory</a>
                    <a href="/api/docs" class="nav-link">API Docs</a>
                </nav>
            </header>

            <main class="main">
                <section class="section">
                    <h2>Recent Backup Jobs</h2>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Job ID</th>
                                <th>Triggered At</th>
                                <th>Triggered By</th>
                                <th>Status</th>
                                <th>Progress</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {jobs_html if jobs_html else '<tr><td colspan="6">No jobs found</td></tr>'}
                        </tbody>
                    </table>
                </section>
            </main>

            <footer class="footer">
                <p>&copy; 2025 Air-Gapped Network Config Fortress</p>
            </footer>
        </div>

        <script>
            {get_dashboard_js()}
        </script>
    </body>
    </html>
    """

    return html_content


@router.websocket("/ws/job/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: int):
    """WebSocket endpoint for real-time backup job progress."""
    await websocket.accept()
    queue = await get_progress_queue(job_id)

    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=60)
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                await websocket.send_json({"status": "still_running", "job_id": job_id})
    except WebSocketDisconnect:
        logger.debug(f"Client disconnected from job {job_id} progress stream")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {str(e)}")
        await websocket.close(code=1011, reason=str(e))


def get_dashboard_css() -> str:
    """Return bundled CSS for dashboard."""
    return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }

        .container {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 1rem;
        }

        .nav {
            display: flex;
            gap: 1rem;
        }

        .nav-link {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            transition: background 0.3s ease;
        }

        .nav-link:hover,
        .nav-link.active {
            background: rgba(255,255,255,0.2);
        }

        .main {
            flex: 1;
            padding: 2rem;
        }

        .section {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
        }

        .section h2 {
            margin-bottom: 1rem;
            color: #1e3c72;
        }

        .table {
            width: 100%;
            border-collapse: collapse;
        }

        .table thead {
            background: #f9f9f9;
            border-bottom: 2px solid #ddd;
        }

        .table th {
            padding: 0.75rem;
            text-align: left;
            font-weight: 600;
            color: #555;
        }

        .table td {
            padding: 0.75rem;
            border-bottom: 1px solid #eee;
        }

        .table tbody tr:hover {
            background: #f9f9f9;
        }

        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-running {
            background: #fff3cd;
            color: #856404;
        }

        .badge-complete {
            background: #d4edda;
            color: #155724;
        }

        .badge-failed {
            background: #f8d7da;
            color: #721c24;
        }

        .btn {
            display: inline-block;
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.9rem;
            transition: all 0.3s ease;
        }

        .btn-primary {
            background: #2a5298;
            color: white;
        }

        .btn-primary:hover {
            background: #1e3c72;
        }

        .btn-sm {
            padding: 0.25rem 0.5rem;
            font-size: 0.8rem;
        }

        .progress-text {
            font-family: 'Courier New', monospace;
            font-weight: 500;
        }

        .footer {
            background: #333;
            color: white;
            text-align: center;
            padding: 1rem;
            margin-top: auto;
        }
    """


def get_dashboard_js() -> str:
    """Return bundled JavaScript for dashboard."""
    return """
        document.addEventListener('DOMContentLoaded', function() {
            const jobLinks = document.querySelectorAll('a[href^="/job/"]');
            jobLinks.forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const jobId = this.getAttribute('href').split('/').pop();
                    openJobDetails(jobId);
                });
            });
        });

        function openJobDetails(jobId) {
            window.location.href = `/job/${jobId}`;
        }

        function connectWebSocket(jobId) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${protocol}//${window.location.host}/ws/job/${jobId}`);

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateProgress(data);
            };

            ws.onerror = function(event) {
                console.error('WebSocket error:', event);
            };

            ws.onclose = function(event) {
                if (event.wasClean) {
                    console.log('WebSocket closed');
                } else {
                    console.error('WebSocket connection lost');
                }
            };

            return ws;
        }

        function updateProgress(data) {
            const progressBar = document.getElementById('progress-bar');
            const progressText = document.getElementById('progress-text');

            if (progressBar && progressText) {
                const percentage = (data.completed / data.total) * 100;
                progressBar.style.width = percentage + '%';
                progressText.textContent = `${data.completed}/${data.total} (Status: ${data.status})`;
            }
        }
    """
