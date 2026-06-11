# src/services/comfy_client.py
# ComfyUI API 客户端
# 职责: 封装与 ComfyUI 服务端的 HTTP 通信
#   - queue_prompt():     提交工作流 JSON, 返回 prompt_id
#   - get_history():      根据 prompt_id 查询生成状态与结果
#   - get_image():        下载生成的图片二进制数据
#   - wait_for_completion(): 轮询直到生成完成
#   - generate():         一站式接口: 提交 → 等待 → 下载

import asyncio
import httpx
from typing import Any


class ComfyClient:
    """
    ComfyUI REST API 客户端

    使用 async/await 实现异步非阻塞通信, 配合 httpx 进行 HTTP 请求
    """

    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """延迟初始化 httpx AsyncClient"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self):
        """关闭 HTTP 客户端连接"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """
        提交工作流到 ComfyUI 队列

        Args:
            workflow: ComfyUI API 格式的工作流 dict

        Returns:
            prompt_id: 用于后续查询生成状态
        """
        client = await self._get_client()
        resp = await client.post("/prompt", json={"prompt": workflow})
        resp.raise_for_status()
        data = resp.json()
        return data["prompt_id"]

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        """
        查询指定 prompt_id 的生成历史与状态

        Returns:
            history dict, 包含 outputs 和 status 信息
        """
        client = await self._get_client()
        resp = await client.get(f"/history/{prompt_id}")
        resp.raise_for_status()
        return resp.json().get(prompt_id, {})

    async def get_image(
        self, filename: str, subfolder: str = "", folder_type: str = "output"
    ) -> bytes:
        """
        下载生成的图片

        Args:
            filename:    图片文件名
            subfolder:   子目录
            folder_type: 目录类型 (output/temp/input)

        Returns:
            图片二进制数据
        """
        client = await self._get_client()
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        resp = await client.get("/view", params=params)
        resp.raise_for_status()
        return resp.content

    async def wait_for_completion(
        self, prompt_id: str, poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        """
        轮询等待生成完成

        每隔 poll_interval 秒查询一次 history, 直到生成完成或超时

        Returns:
            包含生成结果图片信息的 dict
        """
        while True:
            history = await self.get_history(prompt_id)
            if history:
                return history
            await asyncio.sleep(poll_interval)

    async def generate(self, workflow: dict[str, Any]) -> list[bytes]:
        """
        一站式生成接口: 提交工作流 → 等待完成 → 下载所有输出图片

        Returns:
            生成图片的二进制数据列表
        """
        prompt_id = await self.queue_prompt(workflow)
        history = await self.wait_for_completion(prompt_id)

        images: list[bytes] = []
        for node_id, node_output in history.get("outputs", {}).items():
            for img_info in node_output.get("images", []):
                img_bytes = await self.get_image(
                    filename=img_info["filename"],
                    subfolder=img_info.get("subfolder", ""),
                    folder_type=img_info.get("type", "output"),
                )
                images.append(img_bytes)

        return images
