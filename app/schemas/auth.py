"""Authentication schemas."""

from pydantic import BaseModel, Field


class WechatLoginRequest(BaseModel):
    code: str = Field(min_length=1, description="Demo code or phone:name:role")
    wx_code: str | None = Field(default=None, description="wx.login code")
    phone: str | None = None
    name: str | None = None
    role: str | None = None


class WechatPhoneLoginRequest(BaseModel):
    phone_code: str = Field(min_length=1, description="getPhoneNumber temporary code")
    wx_code: str | None = Field(default=None, description="wx.login code")
    name: str | None = None
    role: str | None = None


class WechatLoginResponse(BaseModel):
    token: str
    user: dict


class ReviewLoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    wx_code: str | None = Field(default=None, description="wx.login code")


class SmsCodeRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)


class SmsLoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=4, max_length=8)
    name: str | None = Field(default=None, max_length=50)
    wx_code: str | None = None
