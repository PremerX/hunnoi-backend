import gc

from fastapi import WebSocket, WebSocketDisconnect
from app.ValidateYoutubeUrl import ValidateYoutubeUrl
from app.PlaylistSplitter import PlaylistSplitter
from app.ProcessEnum import ProcessEnum
from app.LoggerInstance import logger
import traceback
import asyncio
import uuid


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
            # Cancel lock when websocket recieve Disconnect Signal
            lock_task.cancel()
            try:
                await monitor_task
            except Exception as e:
                logger.info(f"{type(e).__name__}")
            # Force disconnection when monitor succeed task before recieve lock
            raise WebSocketDisconnect
        else:
            # Recieve Lock to process, stop monitor disconnect signal
            # Sent cancel signal to monitor task
            monitor_task.cancel()
            try:
                # when await monitor task with cancel tag, exception CancelledError should be raise
                await monitor_task
            except asyncio.CancelledError:
                pass

        try:
            await ws.send_json({"status": ProcessEnum.WAITING.value})
            data = await ws.receive_text()
            data = ValidateYoutubeUrl(data).result()
            tag = str(uuid.uuid4())
            splitter = PlaylistSplitter(data, tag, ws)
            await splitter.run()
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during processing")
        except Exception as e:
            logger.error(f"Worker error: {traceback.format_exc()}")
            await ws.send_json({"status": ProcessEnum.ERROR.value})
        finally:
            await ws.close()
            del splitter
            self.process_lock.release()
