from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed
from queue import Queue
from threading import Thread, Lock
from contextlib import asynccontextmanager
from .process.yt_audio import youtube_process_main
from fastapi.middleware.cors import CORSMiddleware
from py_youtube import Data
from pydantic import BaseModel
from dotenv import load_dotenv
import yt_dlp
import os
import asyncio
import uuid
import logging
import traceback

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    print("Application is shutting down... Stopping worker threads.")
    # Signal the worker threads to stop
    for _ in range(max_workers):
        queue.put(None)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)s - %(funcName)20s] - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
DEFAULT_MAX_QUEUE = 5
DEFAULT_MAX_WORKERS = 1
max_queue = int(os.getenv("MAX_QUEUE", DEFAULT_MAX_QUEUE))
max_workers = int(os.getenv("MAX_WORKERS", DEFAULT_MAX_WORKERS))
logger.info(f"Max queue size: {max_queue}, Max workers: {max_workers}")

# Global queue and related data
queue = Queue(maxsize=max_queue)  # Limit queue size to 10
queue_lock = Lock()
clients = {}  # Map WebSocket to its queue position
active_workers = 0  # Track active workers
max_workers = 1  # Limit concurrent active workers

# Get the main event loop
main_event_loop = asyncio.get_event_loop()

# Debounced queue update task
update_task = None

def remove_query_params(url: str):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    filtered_query = {k: v for k, v in query_params.items() if k == 'v'}
    new_query = urlencode(filtered_query, doseq=True)
    return urlunparse(parsed_url._replace(query=new_query))
  
# Function to get the queue position of a specific WebSocket
def get_queue_position(ws):
    with queue_lock:
        try:
            position = list(queue.queue).index(ws) + 1
            return position
        except ValueError:
            return None  # WebSocket not in queue

# Function to manage queue positions (debounced)
def update_queue_positions():
    global update_task

    def send_updates():
        with queue_lock:
            position = 1
            for ws in list(queue.queue):
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json({"status": "Queuing", "queue_position": position}), main_event_loop
                        )
                        position += 1
                except Exception as e:
                    logger.error(f"Error updating queue position: {e}")

    if not update_task or update_task.done():
        update_task = asyncio.run_coroutine_threadsafe(asyncio.to_thread(send_updates), main_event_loop)

# Background worker for consuming tasks from the queue
def worker():
    global active_workers
    while True:
        ws = queue.get()
        if ws is None:  # Graceful shutdown signal
            break
        try:
            with queue_lock:
                active_workers += 1
            if ws.client_state == WebSocketState.CONNECTED:
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({"status": "WaitingUrl"}), main_event_loop
                ).result()

                url = asyncio.run_coroutine_threadsafe(ws.receive_text(), main_event_loop).result()
                url = str(remove_query_params(url))
                tag = str(uuid.uuid4())

                if ws.client_state == WebSocketState.CONNECTED:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({"status": "Processing"}), main_event_loop
                    ).result()

                try:
                    asyncio.run_coroutine_threadsafe(youtube_process_main(url,tag,ws), main_event_loop).result()
                except Exception as e:
                    print(f"Error from during youtube task: {traceback.print_exception(e)}")

                if ws.client_state == WebSocketState.CONNECTED:
                    asyncio.run_coroutine_threadsafe(ws.close(), main_event_loop).result()
        except WebSocketDisconnect:
            print("Client disconnected during task processing")
        except Exception as e:
            print(f"Error during worker processing: {traceback.print_exception(e)}")
        finally:
            with queue_lock:
                active_workers -= 1
            queue.task_done()
            update_queue_positions()

# Start background worker threads
for _ in range(max_workers):
    worker_thread = Thread(target=worker, daemon=True)
    worker_thread.start()

router = APIRouter(prefix="/hunnoi")

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Check if queue is full
    await websocket.accept()
    if queue.full():
        await websocket.send_json({"status": "QueueFull"})
        await websocket.close()
        return
    try:
        # Add client to queue
        with queue_lock:
            queue.put(websocket)
            clients[websocket] = True

        # Notify the specific user of their position
        position = get_queue_position(websocket)
        if position is not None:
            await websocket.send_json({"status": "Queuing", "queue_position": position})

        while True:
            # Keep WebSocket alive
            await asyncio.sleep(1)

    except (WebSocketDisconnect, ConnectionClosed):
        print("Client disconnected")
    finally:
        # Clean up on disconnect
        with queue_lock:
            clients.pop(websocket, None)
            temp_queue = Queue()
            while not queue.empty():
                ws = queue.get()
                if ws != websocket:
                    temp_queue.put(ws)
            while not temp_queue.empty():
                queue.put(temp_queue.get())
        update_queue_positions()


# Endpoint for monitoring/debugging (optional)
@router.get("/queue-status")
async def get_queue_status():
    with queue_lock:
        return {
            "queue_length": queue.qsize(),
            "clients": len(clients),
            "active_workers": active_workers,
            "max_workers": max_workers
        }

class URLCheck(BaseModel):
    url: str

@router.get("/hello")
async def hello_world():
    return {"message": "Hello, World!"}

@router.post("/validate")
async def YouTubeUrlValidate(req: URLCheck):
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "best"
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
        print(info)
    except HTTPException as http_err:
        raise http_err
    except ValueError:
        raise HTTPException(status_code=400, detail="The URL is invalid or inaccessible.")
    except Exception as err:
        logger.error(f"Internal server error: {err}, type: {type(err)}")
        raise HTTPException(status_code=500, detail="Internal server error.")
    
app = FastAPI(lifespan=lifespan)
app.include_router(router)

origins = [
    "https://hunnoi.premerx.tech",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)