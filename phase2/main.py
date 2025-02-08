from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from request_arg import URLCheck
from dotenv import load_dotenv
from phase2.websocketManager import WebsocketManager
from phase2.QueueManager import QueueManager
from phase2.WorkerManager import WorkerManager
from project.validate import ValidateYoutubeUrl

load_dotenv()

router = APIRouter(prefix="/hunnoi")

worker_manager = WorkerManager()
ws_manager = WebsocketManager(worker_manager=worker_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    print("Application is shutting down... Stopping worker threads.")
    # Signal the worker threads to stop
    # await worker_manager.shutdown()
    await ws_manager.close_all()

@router.get("/ping")
async def hello_world():
    return {"message": "Pong, Hunnoi!"}

@router.post("/validate")
async def youtube_validate(req: URLCheck):
    return ValidateYoutubeUrl(req.url).metadata()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.service(websocket)

app = FastAPI(lifespan=lifespan)
app.include_router(router)

origins = [
    "https://hunnoi.premerx.tech",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)