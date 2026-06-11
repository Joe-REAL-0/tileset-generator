# src/routers/chat.py
# 对话 API 路由
# 职责: 管理对话历史, 提供对话消息的存取接口
#   GET  /api/chat/history  - 获取指定 session 的对话历史
#   POST /api/chat/message  - 发送单条对话消息 (REST 备用方案)
#
# 注: 当前使用内存存储 (dict), Phase 6 后替换为 SQLite 持久化

from fastapi import APIRouter
from src.schemas.chat import ChatMessage

router = APIRouter(prefix="/chat", tags=["chat"])

# 内存对话历史存储: session_id → list[ChatMessage]
_chat_history: dict[str, list[ChatMessage]] = {}


@router.get("/history")
async def get_chat_history(session_id: str):
    """获取指定会话的对话历史"""
    return _chat_history.get(session_id, [])


@router.post("/message")
async def send_message(message: ChatMessage):
    """
    发送对话消息 (REST 备用方案)

    主要用于前端同步消息到服务端。通常对话消息通过 WebSocket 实时传输,
    此端点作为 REST 备用通道。
    """
    # 使用简单 session: 基于时间戳的唯一标识
    session_id = "default"
    if session_id not in _chat_history:
        _chat_history[session_id] = []
    _chat_history[session_id].append(message)
    return {"ok": True}
