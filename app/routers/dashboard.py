import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Import the single shared progress-queue registry from the backup engine.
# Do NOT rebind this name — that would disconnect the WebSocket from the engine.
from app.core.backup_engine import progress_queues

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


@router.websocket("/ws/job/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: int) -> None:
    """
    Stream JSON progress messages for a running backup job.

    Sends {"completed": N, "total": M, "failed": F, "status": "...", "job_id": J}
    until the job completes or the client disconnects.
    """
    await websocket.accept()

    # Ensure a queue exists for this job (idempotent).
    if job_id not in progress_queues:
        progress_queues[job_id] = asyncio.Queue()
    queue: asyncio.Queue = progress_queues[job_id]

    try:
        while True:
            try:
                # Wait up to 30 s for the next event; send a keepalive if idle.
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(message)

                # Stop streaming once the job reaches a terminal state.
                if message.get("status") in ("complete", "failed"):
                    break
            except asyncio.TimeoutError:
                await websocket.send_json({"status": "heartbeat", "job_id": job_id})
    except WebSocketDisconnect:
        logger.debug("Client disconnected from job %d progress stream", job_id)
    except Exception as exc:
        logger.error("WebSocket error for job %d: %s", job_id, exc)
        try:
            await websocket.close(code=1011, reason=str(exc))
        except Exception:
            pass
    finally:
        # Clean up the queue once no client is listening.
        progress_queues.pop(job_id, None)
