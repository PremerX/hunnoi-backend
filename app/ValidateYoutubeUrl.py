from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from app.LoggerInstance import logger
from fastapi import HTTPException
from yt_dlp import YoutubeDL
from os import getenv
import traceback

class ValidateYoutubeUrl:
    def __init__(self, url: str):
        self.url = url
        self.remove_query_params()

    def remove_query_params(self):
        parsed_url = urlparse(self.url)
        query_params = parse_qs(parsed_url.query)
        filtered_query = {k: v for k, v in query_params.items() if k == 'v'}
        new_query = urlencode(filtered_query, doseq=True)
        self.url = str(urlunparse(parsed_url._replace(query=new_query)))

    def metadata(self):
        try:
            cookies = getenv("COOKIE_PATH") if getenv("COOKIE_PATH") != '' else None
            ydl_opts = {
                "format": "best",
                "cookiefile": cookies,
                "sleep_interval_requests": 0.4,
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            return {'id': info.get("id"),
                    'title': info.get("title"),
                    'thumbnails': info.get("thumbnail")}
        except HTTPException as http_err:
            raise http_err
        except ValueError:
            raise HTTPException(status_code=400, detail="The URL is invalid or inaccessible.")
        except Exception as err:
            logger.error(f"{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail="Internal server error.")
    
    def result(self):
        return self.url
