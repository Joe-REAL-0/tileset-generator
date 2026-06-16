# src/routers/tileset.py
# Tileset 合成 API 路由
# 职责: 处理 "生成 Autotile" 按钮的请求
#   POST /api/tileset              - 提交 autotile 合成任务 (bg + surface → 47 tiles)
#   GET  /api/tileset/{tileset_id} - 查询合成状态
#   GET  /api/tilesets             - 列出所有已生成的 tileset
#   GET  /api/tilesets/{id}/download - 下载 tileset 文件
#
# 完整管线:
#   1. 加载 background + surface 纹理
#   2. AutotileEngine(bg, sf) → 内部完成缩放 + 旋转复用拆分
#   3. engine.generate_all() → 生成 47 个 tile 并保存到 services/image/
#   4. TilesetBuilder → 拼接为 autotile 图集 + 元数据

import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from src.schemas.tileset import TilesetRequest, TilesetResponse
from src.services.image_processor import ImageProcessor
from src.services.autotile_engine import AutotileEngine
from src.services.tileset_builder import TilesetBuilder
from src.routers.ws import manager
from PIL import Image

router = APIRouter(tags=["tileset"])

# 输出目录
TEXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "textures"
TILESETS_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "tilesets"
TILESETS_DIR.mkdir(parents=True, exist_ok=True)

# 简易任务状态存储
_tileset_store: dict[str, dict] = {}


def _load_texture(image_id: str) -> Image.Image:
    """
    根据 image_id 加载纹理图片
    """
    from src.routers.generate import _find_background_file
    file_path = _find_background_file(image_id)
    if file_path and file_path.exists():
        return Image.open(file_path).convert("RGBA")

    # 尝试匹配文件 (可能有 _0, _1 等后缀)
    for filepath in TEXTURES_DIR.glob(f"{image_id}*.png"):
        return Image.open(filepath).convert("RGBA")

    raise FileNotFoundError(
        f"纹理图片未找到: {image_id} (在 {TEXTURES_DIR} 中搜索)"
    )


async def _run_autotile_pipeline(
    task_id: str,
    bg_id: str,
    sf_id: str,
    tile_size: int,
):
    """后台执行 autotile 合成管线, 并通过 WebSocket 推送进度"""
    try:
        _tileset_store[task_id]["status"] = "loading"
        await manager.send_progress(
            task_id, "loading", 5, "加载纹理..."
        )

        # 1. 加载纹理
        bg_image = _load_texture(bg_id)
        sf_image = _load_texture(sf_id)

        await manager.send_progress(
            task_id, "processing", 15, "初始化 AutotileEngine..."
        )

        # 2. 创建引擎（内部自动完成缩放 + 旋转复用拆分 surface）
        engine = AutotileEngine(bg_image, sf_image, tile_size=tile_size)

        await manager.send_progress(
            task_id, "composing", 30, "合成 47 个 tile 变体..."
        )

        # 3. 生成 47 个 tile 并保存到 services/image/
        engine.generate_all()

        await manager.send_progress(
            task_id, "composing", 60, "拼接 autotile 图集..."
        )

        # 4. 用 TilesetBuilder 拼接图集
        builder = TilesetBuilder(tile_size)
        for mask in engine.valid_masks:
            tile_img = engine.compose_tile(mask)
            binary_str = engine.mask_to_binary(mask)
            builder.add_tile(binary_str, tile_img)

        atlas, metadata = builder.build_with_metadata()

        # 5. 保存图集
        tileset_filename = f"{task_id}.png"
        tileset_path = TILESETS_DIR / tileset_filename
        builder.save(tileset_path)

        metadata["background"] = bg_id
        metadata["surface"] = sf_id

        tileset_url = f"/api/tilesets/{task_id}/download"

        _tileset_store[task_id].update({
            "status": "completed",
            "tileset_url": tileset_url,
            "metadata": metadata,
            "filepath": str(tileset_path),
        })

        await manager.send_progress(
            task_id,
            "completed",
            100,
            f"Autotile 合成完成! {metadata['tile_count']} tiles, "
            f"{metadata['tile_size']}×{metadata['tile_size']} px",
            image_url=tileset_url,
        )

    except Exception as e:
        _tileset_store[task_id].update({
            "status": "failed",
            "error": str(e),
        })
        await manager.send_progress(
            task_id, "failed", 0, error=str(e),
        )


@router.post("/tileset", response_model=TilesetResponse)
async def build_tileset(request: TilesetRequest, background_tasks: BackgroundTasks):
    """
    提交 Autotile 合成任务 (按钮2: 生成 Autotile)

    处理管线:
      background + surface 纹理 → 缩放 → nine_slice → AutotileEngine ×47
      → TilesetBuilder 拼接 → 47-tile autotile 图集
    """
    # 校验 tile_size
    if request.tile_size not in ImageProcessor.VALID_TILE_SIZES:
        raise HTTPException(
            status_code=400,
            detail=f"tile_size 必须为 {ImageProcessor.VALID_TILE_SIZES} 之一",
        )

    # 校验纹理文件存在
    try:
        _load_texture(request.background_image_id)
        _load_texture(request.surface_image_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    task_id = f"ts_{uuid.uuid4().hex[:12]}"

    _tileset_store[task_id] = {
        "status": "queued",
        "tileset_url": None,
        "metadata": None,
        "error": None,
    }

    background_tasks.add_task(
        _run_autotile_pipeline,
        task_id,
        request.background_image_id,
        request.surface_image_id,
        request.tile_size,
    )

    return TilesetResponse(
        task_id=task_id,
        status="queued",
    )


@router.get("/tileset/{tileset_id}")
async def get_tileset_status(tileset_id: str):
    """查询 autotile 合成任务的状态"""
    if tileset_id not in _tileset_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _tileset_store[tileset_id]


@router.get("/tilesets")
async def list_tilesets():
    """列出所有已生成的 tileset (读取 output/tilesets)"""
    tilesets = []
    if TILESETS_DIR.exists():
        for f in sorted(TILESETS_DIR.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
            tilesets.append({
                "tileset_id": f.stem,
                "status": "completed",
                "tileset_url": f"/output/tilesets/{f.name}",
                "filename": f.name
            })
    return tilesets


@router.get("/tilesets/{tileset_id}/download")
async def download_tileset(tileset_id: str):
    """下载 tileset 文件"""
    if tileset_id not in _tileset_store:
        raise HTTPException(status_code=404, detail="Tileset 不存在")

    info = _tileset_store[tileset_id]
    if info["status"] != "completed":
        raise HTTPException(status_code=400, detail="Tileset 尚未完成合成")

    filepath = info.get("filepath")
    if not filepath or not Path(filepath).exists():
        raise HTTPException(status_code=404, detail="Tileset 文件未找到")

    return FileResponse(
        filepath,
        media_type="image/png",
        filename=f"autotile_{tileset_id}.png",
    )
