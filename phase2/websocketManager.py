import asyncio
import traceback
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from phase2.WorkerManager import WorkerManager
from phase2.loggerInstance import logger

class WebsocketManager:
    def __init__(self, max_connections: int = 10, worker_manager: WorkerManager = None):
        self.connections: List[WebSocket] = []
        self.workers_manager = worker_manager
        self.max_connections = max_connections
        self.lock = asyncio.Lock()

    async def service(self, ws: WebSocket):
        if await self.connect(ws):
            try:
                await self.my_queue_position(ws)
                await self.workers_manager.run(ws)
            except WebSocketDisconnect:
                await self.broadcast_queue_positions(ws)
                ws_id = ws.headers.get("sec-websocket-key", "unknown")
                logger.info(f"websocket connection [{ws_id}] dissconnected")
            finally:
                await self.disconnect(ws)


    async def connect(self, ws: WebSocket):
        async with self.lock:
            await ws.accept()
            if self.is_connection_full():
                ws_id = ws.headers.get("sec-websocket-key", "unknown")
                logger.warning(f"Queue is full! Rejecting WebSocket [{ws_id}]")
                await ws.send_json({"status": "QueueFull"})
                await ws.close(code=1001)
                return False
            self.connections.append(ws)
        return True

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.connections:
                self.connections.remove(ws)

    async def close_all(self):
        for ws in self.connections:
            await ws.close()
        self.connections.clear()

    async def my_queue_position(self, ws: WebSocket):
        async with self.lock:
            connection_index = self.connections.index(ws)
        await ws.send_json({"status": "Queuing", "queue_position": connection_index + 1})

    async def broadcast_queue_positions(self, ws: WebSocket):
        async with self.lock:
            connection_index = self.connections.index(ws)
            for position, ws_alive in enumerate(self.connections[connection_index + 1:], start=connection_index + 1):
                try:
                    await ws_alive.send_json({ "status": "Queuing", "queue_position": position })
                except RuntimeError:
                    ws_id = ws_alive.headers.get("sec-websocket-key", "unknown")
                    logger.info(f"During broadcast queue position, connection [{ws_id}] is closed before. Skipping")

    def is_connection_full(self):
        return len(self.connections) >= self.max_connections