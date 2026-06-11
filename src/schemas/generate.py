# src/schemas/generate.py
# 材质生成相关的 Pydantic 数据模型
# GenerateRequest:  用户提交的生成请求 (提示词 + 种子)
# GenerateResponse: 返回异步任务 ID 和 WebSocket 连接地址

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """材质纹理生成请求

    SD 固定生成 512×512 原始纹理, 后续在 autotile 合成阶段缩放到目标尺寸
    """
    prompt: str = Field(
        ...,
        description="正向提示词, 描述要生成的材质 (如 '草地', '沙地', '水面')",
    )
    negative_prompt: str | None = Field(
        None,
        description="反向提示词, 描述不希望出现的元素",
    )
    seed: int | None = Field(
        None,
        description="随机种子 (-1 表示随机)",
    )


class GenerateResponse(BaseModel):
    """材质生成异步任务响应"""
    task_id: str
    status: str = "queued"
    websocket_url: str
