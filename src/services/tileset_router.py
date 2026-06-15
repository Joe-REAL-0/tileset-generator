"""
tileset.py
Tileset API 路由

提供前端调用的 RESTful API：
- POST /api/tileset/generate-autotile — 生成 autotile 图集
- GET /api/tileset/list — 列出生成的 tileset
- GET /api/tileset/{filename} — 获取单个 tile 图片
- GET /api/tileset/preview/{prefix} — 获取预览图
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
from typing import List, Optional
import tempfile
import shutil

from services.autotile_engine import AutotileEngine
from services.image_processor import ImageProcessor  # 假设存在

router = APIRouter(prefix="/api/tileset", tags=["tileset"])

# 配置
OUTPUT_DIR = Path("output/autotiles")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ========== 请求模型 ==========

class AutotileGenerateRequest(BaseModel):
    """Autotile 生成请求"""
    prefix: str = "autotile"                    # 材质前缀
    tile_size: int = 32                         # 瓦片尺寸 (16/32/64/128)
    naming_style: str = "compact"               # 命名风格 (full/compact/hybrid)
    background_path: Optional[str] = None       # 背景图路径（如不提供则生成纯色）
    surface_parts_paths: Optional[dict] = None  # surface 子区域路径字典

    class Config:
        schema_extra = {
            "example": {
                "prefix": "grass",
                "tile_size": 32,
                "naming_style": "compact",
                "background_path": "output/backgrounds/grass_bg_32.png",
                "surface_parts_paths": {
                    "TL": "output/surfaces/grass_tl_16.png",
                    "T": "output/surfaces/grass_t_16.png",
                    "TR": "output/surfaces/grass_tr_16.png",
                    "L": "output/surfaces/grass_l_16.png",
                    "R": "output/surfaces/grass_r_16.png",
                    "BL": "output/surfaces/grass_bl_16.png",
                    "B": "output/surfaces/grass_b_16.png",
                    "BR": "output/surfaces/grass_br_16.png"
                }
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

    根据 background 和 surface 子区域，生成全部 16 种 bitmask 变体。
    """
    try:
        # 1. 加载背景图
        if request.background_path and Path(request.background_path).exists():
            from PIL import Image
            bg = Image.open(request.background_path).convert('RGBA')
        else:
            # 默认生成绿色背景
            from PIL import Image
            bg = Image.new('RGBA', (request.tile_size, request.tile_size), (34, 139, 34, 255))

        # 2. 加载 surface 子区域
        surface_parts = {}
        if request.surface_parts_paths:
            from PIL import Image
            for name, path in request.surface_parts_paths.items():
                if Path(path).exists():
                    surface_parts[name] = Image.open(path).convert('RGBA')

        # 如果没有提供 surface，使用默认测试数据
        if not surface_parts:
            from PIL import Image
            sub_size = request.tile_size // 2
            colors = {
                'TL': (139, 69, 19, 200), 'T': (160, 82, 45, 200),
                'TR': (139, 69, 19, 200), 'L': (205, 133, 63, 200),
                'R': (210, 105, 30, 200), 'BL': (205, 133, 63, 200),
                'B': (210, 105, 30, 200), 'BR': (222, 184, 135, 200),
            }
            for name, color in colors.items():
                surface_parts[name] = Image.new('RGBA', (sub_size, sub_size), color)

        # 3. 创建引擎并生成
        engine = AutotileEngine(bg, surface_parts, tile_size=request.tile_size)

        # 4. 保存到输出目录
        output_subdir = OUTPUT_DIR / request.prefix
        files = engine.save_all(str(output_subdir), 
                                prefix=request.prefix,
                                naming_style=request.naming_style)

        # 5. 生成预览图
        preview = engine.generate_preview_sheet(cols=8)
        preview_path = output_subdir / f"{request.prefix}_preview.png"
        preview.save(preview_path)

        # 6. 收集信息
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


@router.get("/{prefix}/info/{bitmask}")
async def get_tile_info(prefix: str, bitmask: int):
    """获取指定 bitmask 的 tile 详细信息"""
    # 这里简化处理，实际应该加载已保存的 tile
    from PIL import Image
    bg = Image.new('RGBA', (32, 32), (0, 128, 0, 255))
    parts = {}
    engine = AutotileEngine(bg, parts, tile_size=32)
    info = engine.get_tile_info(bitmask)
    return info
