# tests/test_comfy_client.py
# ComfyUI API 客户端单元测试
# 测试目标: ComfyClient 的各个方法在 mock HTTP 响应下的行为
#   - queue_prompt() 正常返回 prompt_id
#   - get_history() 解析历史记录
#   - get_image() 返回图片 bytes
#   - wait_for_completion() 轮询逻辑
#   - generate() 一站式流程

import pytest
from unittest.mock import AsyncMock, patch
from src.services.comfy_client import ComfyClient


class TestComfyClient:
    """ComfyClient 单元测试 (mock ComfyUI API)"""

    @pytest.mark.asyncio
    async def test_queue_prompt_returns_prompt_id(self):
        """测试: queue_prompt 应返回有效的 prompt_id"""
        # TODO: 实现 mock HTTP 测试
        pass

    @pytest.mark.asyncio
    async def test_get_history_returns_outputs(self):
        """测试: get_history 应正确解析 outputs 和 status"""
        pass

    @pytest.mark.asyncio
    async def test_get_image_returns_bytes(self):
        """测试: get_image 应返回图片二进制数据"""
        pass

    @pytest.mark.asyncio
    async def test_wait_for_completion_polls_until_done(self):
        """测试: wait_for_completion 应轮询直到 history 返回非空"""
        pass

    @pytest.mark.asyncio
    async def test_generate_full_pipeline(self):
        """测试: generate 应完成 提交→等待→下载 全流程"""
        pass
