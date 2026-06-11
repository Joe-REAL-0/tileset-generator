# src/schemas/tileset.py
# Tileset 合成相关的 Pydantic 数据模型
# TilesetRequest:   用户选择 background + surface 纹理 ID 及目标 tile 尺寸
# TilesetResponse:  返回最终 47-tile autotile 图集 URL 及元数据 (含 mask_map)

from pydantic import BaseModel, Field


class TilesetRequest(BaseModel):
    """Autotile 合成请求

    需要指定 1 张 background 和 1 张 surface 纹理, 以及目标 tile 尺寸
    """
    background_image_id: str = Field(
        ...,
        description="背景材质纹理 ID (如泥土)"
    )
    surface_image_id: str = Field(
        ...,
        description="表面材质纹理 ID (如草地, 包裹在泥土周围)"
    )
    tile_size: int = Field(
        32,
        description="目标 tile 尺寸 (16 | 32 | 64 | 128)"
    )


class TilesetResponse(BaseModel):
    """Autotile 合成响应"""
    task_id: str
    status: str
    tileset_url: str | None = None
    metadata: dict | None = None
    # metadata 示例:
    # {
    #     "tile_count": 47,
    #     "tile_size": 32,
    #     "columns": 8, "rows": 6,
    #     "image_size": [256, 192],
    #     "format": "png",
    #     "background": "img_dirt_001",
    #     "surface": "img_grass_001",
    #     "mask_map": {"0x00": 0, "0x01": 1, ...}
    # }
