from pydantic import BaseModel, HttpUrl, Field
from typing import Any

class LoginIn(BaseModel):
    username: str
    password: str

class NodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    region: str = ""
    base_url: str
    api_token: str = Field(min_length=4)
    verify_tls: bool = True
    enabled: bool = True

class NodeUpdate(BaseModel):
    name: str|None = None
    region: str|None = None
    base_url: str|None = None
    api_token: str|None = None
    verify_tls: bool|None = None
    enabled: bool|None = None

class RawSaveIn(BaseModel):
    node_ids: list[int] = Field(min_length=1)
    object: str
    action: str
    data: Any
    initUsers: str|None = None

class NodeActionIn(BaseModel):
    node_ids: list[int] = Field(min_length=1)
