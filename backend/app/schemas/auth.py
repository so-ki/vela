from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=128)
    organization: Optional[str] = Field(default=None, max_length=255)


class UserRegister(UserBase):
    password: str = Field(min_length=8, max_length=128)
    accept_disclaimer: bool = Field(description="必须勾选同意免责声明")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: int
    role: str
    is_active: bool
    disclaimer_accepted: bool
    disclaimer_accepted_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class AcceptDisclaimerRequest(BaseModel):
    accept: bool = Field(description="必须为 true 方可继续使用平台")


class SsoConfigResponse(BaseModel):
    enabled: bool
    provider_name: str
    allow_password_login: bool
    allow_open_registration: bool
