from pydantic import BaseModel

class URLCheck(BaseModel):
    url: str