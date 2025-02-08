import asyncio
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from phase2.loggerInstance import logger


class WorkerManager:
    def __init__(self, worker_size: int = 1):
        self.process_lock = asyncio.Semaphore(worker_size)

    async def run(self, ws: WebSocket):
        lock_task = asyncio.create_task(self.process_lock.acquire())
        monitor_task = asyncio.create_task(ws.receive_text())
        done, pending = await asyncio.wait(
            [lock_task, monitor_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        if monitor_task in done:
            lock_task.cancel()
            try:
                await monitor_task
            except Exception:
                pass
            raise WebSocketDisconnect
        else:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

        try:
            await ws.send_json({"status": "WaitingUrl"})
            data = await ws.receive_text()
            tag = str(uuid.uuid4())
            await ws.send_json({"status": "Processing", "tag": tag, "data": data})
        except WebSocketDisconnect:
            print("WebSocket disconnected during processing")
        except Exception as e:
            print(f"Worker error: {e}")
        finally:
            self.process_lock.release()
            await ws.close()
