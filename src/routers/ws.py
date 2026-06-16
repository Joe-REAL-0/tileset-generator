# src/routers/ws.py
# WebSocket 实时推送路由
# 职责: 前端通过 WebSocket 连接接收 SD 生成和 Autotile 合成的实时进度
#   - 按 task_id 分组推送进度消息
#   - 支持状态: queued → generating → composing → completed | failed
#   - ConnectionManager 类管理活跃连接的注册与广播

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """
    WebSocket 连接管理器

    按 task_id 维护活跃连接, 支持单播推送进度到特定任务的前端订阅者。
    """

    def __init__(self):
        # task_id → set[WebSocket]
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        """接受 WebSocket 连接并注册到 task_id 分组"""
        await websocket.accept()
        if task_id not in self._connections:
            self._connections[task_id] = set()
        self._connections[task_id].add(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket):
        """从 task_id 分组中移除断开的连接"""
        if task_id in self._connections:
            self._connections[task_id].discard(websocket)
            if not self._connections[task_id]:
                del self._connections[task_id]

    async def send_progress(
        self,
        task_id: str,
        status: str,
        progress: int = 0,
        message: str = "",
        image_url: str | None = None,
        error: str | None = None,
    ):
        """
        向订阅了指定 task_id 的所有前端推送进度消息

        消息格式:
        {
            "type": "status",
            "task_id": "...",
            "status": "generating",
            "progress": 45,
            "message": "Sampling...",
            "image_url": null,
            "error": null
        }
        """
        if task_id not in self._connections:
            return

        payload = json.dumps({
            "type": "status",
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "image_url": image_url,
            "error": error,
        })

        dead_connections: list[WebSocket] = []
        for ws in self._connections[task_id]:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(task_id, ws)


# 全局连接管理器实例
manager = ConnectionManager()


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket 端点: 前端连接此端点接收任务进度推送
    """
    await manager.connect(task_id, websocket)
    try:
        from src.routers.tileset import _tileset_store
        from src.routers.generate import _task_store
        info = _tileset_store.get(task_id) or _task_store.get(task_id)
        if info and info.get("status") in ("completed", "failed"):
            await manager.send_progress(
                task_id,
                status=info["status"],
                progress=100 if info["status"] == "completed" else 0,
                message="已完成" if info["status"] == "completed" else "已失败",
                image_url=info.get("tileset_url") or (info.get("image_urls")[0] if info.get("image_urls") else None),
                error=info.get("error")
            )
    except Exception as e:
        print(f"Error checking initial status on ws connect: {e}")

    try:
        # 保持连接活跃, 等待服务端推送消息
        while True:
            # 接收前端发来的心跳 (ping), 也可用于未来扩展双向通信
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(task_id, websocket)
