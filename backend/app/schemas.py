from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal
from urllib.parse import urlsplit

class LoginIn(BaseModel):
    username: str
    password: str

class NodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    region: str = Field(default="", max_length=100)
    base_url: str = Field(min_length=8, max_length=500)
    api_token: str = Field(min_length=4)
    verify_tls: bool = True
    enabled: bool = True
    group_name: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=2000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str):
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be a valid HTTP or HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]):
        if any(not tag.strip() or len(tag) > 30 for tag in value):
            raise ValueError("tags must be 1-30 characters")
        return list(dict.fromkeys(tag.strip() for tag in value))

class NodeUpdate(BaseModel):
    name: str|None = Field(default=None, min_length=1, max_length=100)
    region: str|None = Field(default=None, max_length=100)
    base_url: str|None = Field(default=None, min_length=8, max_length=500)
    api_token: str|None = None
    verify_tls: bool|None = None
    enabled: bool|None = None
    group_name: str|None = Field(default=None, max_length=100)
    tags: list[str]|None = Field(default=None, max_length=20)
    notes: str|None = Field(default=None, max_length=2000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str|None):
        return NodeIn.validate_base_url(value) if value is not None else value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]|None):
        return NodeIn.validate_tags(value) if value is not None else value

class RawSaveIn(BaseModel):
    node_ids: list[int] = Field(min_length=1)
    object: str
    action: str
    data: Any
    initUsers: str|None = None

class NodeActionIn(BaseModel):
    node_ids: list[int] = Field(min_length=1)


class CentralUserIn(BaseModel):
    username: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.@-]+$")
    email: str = Field(default="", max_length=255)
    credential: str|None = Field(default=None, min_length=4, max_length=255)
    enabled: bool = True
    total_gb: float = Field(default=0, ge=0)
    expire_at: datetime|None = None
    limit_ip: int = Field(default=0, ge=0, le=1000)
    notes: str = Field(default="", max_length=2000)


class CentralUserUpdate(BaseModel):
    username: str|None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.@-]+$")
    email: str|None = Field(default=None, max_length=255)
    credential: str|None = Field(default=None, min_length=4, max_length=255)
    enabled: bool|None = None
    total_gb: float|None = Field(default=None, ge=0)
    expire_at: datetime|None = None
    limit_ip: int|None = Field(default=None, ge=0, le=1000)
    notes: str|None = Field(default=None, max_length=2000)


class UserSyncIn(BaseModel):
    node_ids: list[int] = Field(min_length=1)
    action: Literal["add", "edit", "delete"] = "add"
    dry_run: bool = True


class SnapshotIn(BaseModel):
    label: str = Field(default="manual", max_length=200)


class SnapshotRestoreIn(BaseModel):
    objects: list[str] = Field(default_factory=lambda: ["clients", "inbounds", "outbounds", "tls", "services", "endpoints", "config", "settings"])
    dry_run: bool = True


class AlertUpdateIn(BaseModel):
    action: Literal["acknowledge", "resolve", "reopen"]
