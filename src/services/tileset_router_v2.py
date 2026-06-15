"""
tileset.py
Tileset API 路由

提供前端调用的 RESTful API：
- POST /api/tileset/generate-autotile — 生成 autotile 图集
- GET /api/tileset/list — 列出生成的 tileset
- GET /api/tileset/{filename} — 获取单个 tile 图片
- GET /api/tileset/preview/{prefix} — 获取预览图

集成 ImageProcessor 进行图像预处理：
- 自动 downscale background 到目标尺寸
- 自动 nine_slice surface 为 8 个子区域
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List, Optional, Dict
import tempfile
import shutil

from services.autotile_engine import AutotileEngine
from services.image_processor import ImageProcessor

router = APIRouter(prefix="/api/tileset", tags=["tileset"])

# 配置
OUTPUT_DIR = Path("output/autotiles")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ========== 请求模型 ==========

class AutotileGenerateRequest(BaseModel):
    """Autotile 生成请求"""
    prefix: str = Field(default="autotile", description="材质前缀，如 grass/dirt/stone")
    tile_size: int = Field(default=32, ge=16, le=128, description="瓦片尺寸 (16/32/64/128)")
    naming_style: str = Field(default="compact", description="命名风格: full/compact/hybrid")

    # 原始图像路径（由 ImageProcessor 自动处理）
    background_path: Optional[str] = Field(
        default=None, 
        description="background 大图路径（SD 原始输出，任意尺寸）"
    )
    surface_path: Optional[str] = Field(
        default=None,
        description="surface 大图路径（方形，会被 nine_slice 切割）"
    )

    # 已处理的图像路径（直接传入，跳过预处理）
    processed_background_path: Optional[str] = Field(
        default=None,
        description="已处理好的 background 路径（tile_size x tile_size）"
    )
    processed_surface_paths: Optional[Dict[str, str]] = Field(
        default=None,
        description="已切割好的 surface 子区域路径字典"
    )

    class Config:
        schema_extra = {
            "example": {
                "prefix": "grass",
                "tile_size": 32,
                "naming_style": "compact",
                "background_path": "output/backgrounds/grass_bg_512.png",
                "surface_path": "output/surfaces/grass_surface_96.png"
            }
        }


class TileInfoResponse(BaseModel):
    """Tile 信息响应"""
    filename: str
    bitmask: int
    binary: str
    regions_shown: List[str]
    regions_hidden: List[str]
    description: str
    url: str


# ========== API 端点 ==========

@router.post("/generate-autotile", response_model=dict)
async def generate_autotile(request: AutotileGenerateRequest):
    """
    生成 autotile 图集

    支持两种输入方式：
    1. 传入原始大图（background_path + surface_path）→ 自动 downscale + nine_slice
    2. 传入已处理图像（processed_background_path + processed_surface_paths）→ 直接使用
    """
    try:
        engine = None

        # 方式1：从原始大图创建（推荐）
        if request.background_path and request.surface_path:
            from PIL import Image

            # 加载原始图像
            bg_raw = Image.open(request.background_path)
            surf_raw = Image.open(request.surface_path)

            # 使用 from_raw_images 自动完成预处理
            engine = AutotileEngine.from_raw_images(
                raw_background=bg_raw,
                raw_surface=surf_raw,
                tile_size=request.tile_size
            )

        # 方式2：从已处理图像创建
        elif request.processed_background_path and request.processed_surface_paths:
            from PIL import Image

            bg = Image.open(request.processed_background_path)

            surface_parts = {}
            for name, path in request.processed_surface_paths.items():
                if Path(path).exists():
                    surface_parts[name] = Image.open(path)

            engine = AutotileEngine(bg, surface_parts, tile_size=request.tile_size)

        else:
            raise HTTPException(
                status_code=400, 
                detail="请提供 background_path + surface_path（原始大图）"
                      "或 processed_background_path + processed_surface_paths（已处理）"
            )

        # 生成并保存
        output_subdir = OUTPUT_DIR / request.prefix
        files = engine.save_all(
            str(output_subdir),
            prefix=request.prefix,
            naming_style=request.naming_style
        )

        # 生成预览图
        preview = engine.generate_preview_sheet(cols=8)
        preview_path = output_subdir / f"{request.prefix}_preview.png"
        preview.save(preview_path)

        # 收集信息
        tile_infos = []
        for bitmask, _ in engine.generate_all():
            info = engine.get_tile_info(bitmask)
            filename = engine._generate_filename(bitmask, request.prefix, request.naming_style)
            tile_infos.append(TileInfoResponse(
                filename=filename,
                bitmask=info['bitmask'],
                binary=info['binary'],
                regions_shown=info['regions_shown'],
                regions_hidden=info['regions_hidden'],
                description=info['description'],
                url=f"/api/tileset/{request.prefix}/{filename}"
            ))

        return {
            "success": True,
            "prefix": request.prefix,
            "tile_size": request.tile_size,
            "naming_style": request.naming_style,
            "output_dir": str(output_subdir),
            "total_tiles": len(files),
            "preview_url": f"/api/tileset/{request.prefix}/preview",
            "tiles": [t.dict() for t in tile_infos]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-image", response_model=dict)
async def process_image(image_path: str, target_size: int = 32):
    """
    图像预处理接口（独立调用）

    对单张图片进行 downscale 或 nine_slice 处理
    """
    try:
        from PIL import Image

        img = Image.open(image_path)

        # downscale
        if target_size in ImageProcessor.VALID_SIZES:
            result = ImageProcessor.downscale(img, target_size)
            output_path = OUTPUT_DIR / "processed" / f"downscaled_{target_size}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(output_path)
            return {
                "success": True,
                "operation": "downscale",
                "input_size": img.size,
                "output_size": result.size,
                "output_path": str(output_path)
            }

        # nine_slice（如果尺寸能被 3 整除）
        elif img.size[0] == img.size[1] and img.size[0] % 3 == 0:
            parts = ImageProcessor.nine_slice(img)
            output_paths = {}
            for name, part in parts.items():
                part_path = OUTPUT_DIR / "processed" / f"slice_{name}.png"
                part_path.parent.mkdir(parents=True, exist_ok=True)
                part.save(part_path)
                output_paths[name] = str(part_path)
            return {
                "success": True,
                "operation": "nine_slice",
                "input_size": img.size,
                "parts": output_paths
            }

        else:
            raise HTTPException(status_code=400, detail="无法处理：尺寸不符合要求")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_tilesets():
    """列出生成的所有 tileset"""
    tilesets = []
    if OUTPUT_DIR.exists():
        for subdir in OUTPUT_DIR.iterdir():
            if subdir.is_dir():
                tiles = list(subdir.glob("*.png"))
                tilesets.append({
                    "prefix": subdir.name,
                    "tile_count": len(tiles),
                    "path": str(subdir)
                })
    return {"tilesets": tilesets}


@router.get("/{prefix}/{filename}")
async def get_tile(prefix: str, filename: str):
    """获取单个 tile 图片"""
    file_path = OUTPUT_DIR / prefix / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Tile not found")
    return FileResponse(file_path)


@router.get("/{prefix}/preview")
async def get_preview(prefix: str):
    """获取 tileset 预览图"""
    preview_path = OUTPUT_DIR / prefix / f"{prefix}_preview.png"
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path)
