# src/schemas/chat.py
# 对话消息相关的 Pydantic 数据模型
# ChatMessage: 单条对话消息 (用户/助手/系统), 可携带图片 URL

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """单条对话消息"""
    role: str = Field(
        ...,
        description="消息角色: user | assistant | system",
    )
    content: str = Field(
        ...,
        description="消息文本内容",
    )
    image_url: str | None = Field(
        None,
        description="图片 URL (assistant 消息中携带生成结果)",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 时间戳",
    )
