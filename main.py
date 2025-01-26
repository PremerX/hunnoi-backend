from fastapi import FastAPI, HTTPException
from app.routes.websocket import router as websocket_router
from pydantic import BaseModel
from py_youtube import Data
from fastapi.middleware.cors import CORSMiddleware
import logging

app = FastAPI()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s")
logger = logging.getLogger(__name__)

origins = [
    "http://localhost:5173",
]

app.include_router(websocket_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class URLCheck(BaseModel):
    url: str

@app.get("/hello")
async def hello_world():
    return {"message": "Hello, World!"}

@app.post("/validate")
async def YouTubeUrlValidate(req: URLCheck):
    try:
        yt_data = Data(req.url).data()
        if yt_data["id"] != None:
            return {'id': yt_data['id'],
                    'title': yt_data['title'],
                    'thumbnails': yt_data['thumbnails']}
        else:
            logger.warning(f"Invalid YouTube URL: {req.url}")
            raise HTTPException(status_code=400, detail="This YouTube URL is invalid.")
    except HTTPException as http_err:
        raise http_err
    except ValueError:
        raise HTTPException(status_code=400, detail="The URL is invalid or inaccessible.")
    except Exception as err:
        logger.error(f"Internal server error: {err}, type: {type(err)}")
        raise HTTPException(status_code=500, detail="Internal server error.")