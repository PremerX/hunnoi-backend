from fastapi import WebSocket, WebSocketDisconnect
from asyncio import Queue
import uuid

class ConnectionManager:
    def __init__(self, max_connections: int = 5):
        self.queue = Queue()
        self.max_connections = max_connections
        self.current_connections = 0

    async def connect(self, websocket: WebSocket):
        if self.current_connections >= self.max_connections:
            await websocket.close(code=1008)  # 1008 = Policy Violation
            return None
        
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        print(f"Connection ID: {connection_id} connected.")
        await self.queue.put((connection_id, websocket))
        self.current_connections += 1
        return connection_id

    async def disconnect(self, websocket: WebSocket):
        new_queue = Queue()
        while not self.queue.empty():
            conn_id, ws = await self.queue.get()
            if ws != websocket:  # ไม่ลบ WebSocket อื่น
                await new_queue.put((conn_id, ws))
        self.queue = new_queue
        self.current_connections -= 1  # ลดจำนวนการเชื่อมต่อ
        print(self.queue._queue)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def my_queue_positions(self, connection_id: str):
        """ฟังก์ชันดูตำแหน่งคิวสำหรับตัวเอง"""
        try:
            current_queue = list(self.queue._queue)  # ดึง deque ออกมาเป็น list
            # ใช้ next() เพื่อหาตำแหน่ง connection_id
            idx, (_, client_ws) = next(
                (i, item) for i, item in enumerate(current_queue) if item[0] == connection_id
            )
            queue_position = idx + 1
            await client_ws.send_text(f"You are in the queue. Your position: {queue_position}")
        except StopIteration:
            print(f"Connection ID {connection_id} not found in queue.")
            return None
        
    async def update_queue_positions(self):
        """แจ้งตำแหน่งของ WebSocket ในคิวว่าตัวเองอยู่คิวที่เท่าไหร่แล้ว"""
        new_queue = Queue()
        position = 0
        while not self.queue.empty():
            conn_id, websocket = await self.queue.get()
            try:
                await websocket.send_text(f"Now, Your position in the queue: {position}")
                position += 1
                await new_queue.put((conn_id, websocket))  # ใส่ WebSocket กลับเข้าคิว
            except Exception:
                # หาก WebSocket disconnect ไม่ใส่กลับ
                pass
        self.queue = new_queue  # อัปเดตคิวใหม่