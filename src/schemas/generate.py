# src/schemas/generate.py
# 材质生成相关的 Pydantic 数据模型
# GenerateRequest:  用户提交的生成请求 (提示词 + 种子 + 生成类型 + 模型选择)
# GenerateResponse: 返回异步任务 ID 和 WebSocket 连接地址

from typing import Literal
from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """材质纹理生成请求

    SD 固定生成 512×512 原始纹理, 后续在 autotile 合成阶段缩放到目标尺寸

    支持两种生成类型:
      - "background": 纯文生图, 从噪声直接生成背景纹理
      - "surface":    图生图 + 遮罩修补, 以已选背景图为底图生成表面纹理
    """
    prompt: str = Field(
        ...,
        description="正向提示词 (已由前端整合: 系统正向提示词 + 材质提示词)",
    )
    negative_prompt: str | None = Field(
        None,
        description="反向提示词",
    )
    seed: int | None = Field(
        None,
        description="随机种子 (-1 表示随机)",
    )
    generate_type: Literal["background", "surface"] = Field(
        "background",
        description="生成类型: background (背景/文生图) | surface (表面/图生图+遮罩)",
    )
    background_image_id: str | None = Field(
        None,
        description="Surface 生成时使用的背景图 ID (如 gen_9fddf0bd3227), 仅在 generate_type=surface 时有效",
    )
    checkpoint: str | None = Field(
        None,
        description="用户选择的 Checkpoint 文件名 (如 sd3.5_medium.safetensors)",
    )
    lora: str | None = Field(
        None,
        description="用户选择的 LoRA 文件名 (如 PreAlphaWoWTilesetsSDXL.safetensors)",
    )
    surface_background_tolerance: int | None = Field(
        None,
        description="去除背景时的容差值 (0-255)，仅在 generate_type=surface 时有效",
    )


class GenerateResponse(BaseModel):
    """材质生成异步任务响应"""
    task_id: str
    status: str = "queued"
    websocket_url: str


class ModelsListResponse(BaseModel):
    """可用模型列表响应"""
    checkpoints: list[str] = []
    loras: list[str] = []


class PromptsConfigResponse(BaseModel):
    """系统提示词配置响应"""
    system_positive: str = ""
    system_negative: str = ""
    surface_background_tolerance: int = 32


class ReprocessRequest(BaseModel):
    """重新处理 surface 纹理请求"""
    tolerance: int = Field(..., description="新的背景容差值 (0-255)")
