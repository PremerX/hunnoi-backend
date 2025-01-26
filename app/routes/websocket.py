from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from app.core.connection_manager import ConnectionManager
import asyncio

router = APIRouter()
manager = ConnectionManager()

# สร้าง Semaphore และ Queue สำหรับการจัดการคิว
semaphore = asyncio.Semaphore(1)  # อนุญาตให้ประมวลผลพร้อมกัน 2 คน
queue = asyncio.Queue()  # คิวของ WebSocket connections

async def update_queue_positions():
    """ฟังก์ชันอัปเดตตำแหน่งคิวสำหรับทุกคนในคิว"""
    current_queue = list(queue._queue)  # ดึงรายการในคิวปัจจุบัน
    for idx, (_, client_ws) in enumerate(current_queue):
        queue_position = idx
        try:
            await client_ws.send_text(f"Now, Your position in the queue: {queue_position}")
        except WebSocketDisconnect:
            # ถ้าผู้ใช้หลุดในระหว่างการอัปเดต ให้ลบออกจากคิว
            await remove_disconnected_client(client_ws)

async def my_queue_positions(connection_id: str):
    """ฟังก์ชันดูตำแหน่งคิวสำหรับตัวเอง"""
    try:
        current_queue = list(queue._queue)  # ดึง deque ออกมาเป็น list
        # ใช้ next() เพื่อหาตำแหน่ง connection_id
        idx, (_, client_ws) = next(
            (i, item) for i, item in enumerate(current_queue) if item[0] == connection_id
        )
        queue_position = idx + 1
        await client_ws.send_text(f"You are in the queue. Your position: {queue_position}")
    except StopIteration:
        print(f"Connection ID {connection_id} not found in queue.")
        return None

async def remove_disconnected_client(disconnected_ws: WebSocket):
    """ลบผู้ใช้ที่หลุดออกจากคิว"""
    queue._queue = asyncio.Queue(
        [item for item in list(queue._queue) if item[1] != disconnected_ws]
    )
    await update_queue_positions()

@router.websocket("/ws/process")
async def websocket_endpoint(websocket: WebSocket):
    connection_id = await manager.connect(websocket)
    if connection_id is None:
        return
    
    await manager.my_queue_positions(connection_id)  # แจ้งตำแหน่งคิวของผู้ใช้
    try:
        while True:
            async with semaphore:
                conn_id, current_ws = await manager.queue.get()
                if current_ws == websocket:
                    # แจ้งผู้ใช้ว่ากำลังเริ่ม process
                    await websocket.send_text("Your process is starting now!")
                    print(f"Processing connection {connection_id}")

                    # ตัวอย่างการทำงาน
                    await websocket.send_text(f"Your connection id: {connection_id}")
                    await websocket.send_text("Hello, Welcome to my ws!")
                    await asyncio.sleep(4)
                    await websocket.send_text("Wait a moment...")
                    await asyncio.sleep(3)
                    await websocket.send_text("This is your data.")
                    await asyncio.sleep(2)
                    await websocket.send_text("Bye")
                    await websocket.close()
                    break  # สิ้นสุดการประมวลผล
                else:
                    # ใส่ WebSocket ที่ยังไม่ถึงคิวกลับไปในคิว
                    await manager.queue.put((conn_id, current_ws))
    except WebSocketDisconnect:
        print(f"Connection {connection_id} force disconnected.")
    finally:
        # ลบการเชื่อมต่อออกจาก manager
        await manager.disconnect(websocket)
        print(f"Connection {connection_id} finished or disconnected.")
        await manager.update_queue_positions()  # อัปเดตตำแหน่งคิวหลังจากเสร็จสิ้น