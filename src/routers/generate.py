# src/routers/generate.py
# 材质生成 API 路由
# 职责: 处理 "生成Background纹理" 和 "生成Surface纹理" 的请求
#   POST /api/generate           - 提交材质纹理生成任务
#   GET  /api/generate/{task_id} - 查询任务状态
#   GET  /api/models                      - 列出可用 Checkpoint / LoRA
#   GET  /api/materials/list              - 列出已生成的材质
#   GET  /api/config/prompts              - 返回系统提示词配置
#   GET  /api/comfy-outputs               - 列出 ComfyUI output 目录中的图片
#   POST /api/comfy-outputs/upload        - 上传图片到 ComfyUI output 目录
#
# 流程图:
#   Background: 提示词(系统+材质) → WorkflowEditor("background") → ComfyUI → 输出
#   Surface:    提示词(系统+材质) + 背景图 → 复制背景图到 ComfyUI input/
#              → WorkflowEditor("surface") → ComfyUI → 输出
#   前端通过 WebSocket 获取实时进度推送

import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from src.schemas.generate import (
    GenerateRequest, GenerateResponse,
    ModelsListResponse, PromptsConfigResponse,
)
from src.services.workflow_editor import WorkflowEditor
from src.services.comfy_client import ComfyClient
from src.config import load_config
from src.routers.ws import manager

router = APIRouter(prefix="/generate", tags=["generate"])

# 简易任务状态存储 (后续替换为 SQLite)
_task_store: dict[str, dict] = {}

# 输出目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "textures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 静态文件 URL 前缀 (对应 main.py 中 output 目录的 StaticFiles mount)
OUTPUT_URL_PREFIX = "/output/textures"

# ── 系统提示词默认值 ─────────────────────────────────────────────

SYSTEM_PROMPT_POSITIVE = (
    "(flat design:1.3), (2D pixel art:1.2), (no decorations:1.2), "
    "pure flat base texture, uniform pattern, featureless, "
    "seamless texture, top-down view, simple color, massive pixel, "
    "video game asset, no shadow, no lighting gradient, clean shapes"
)

SYSTEM_PROMPT_NEGATIVE = (
    "(white background:1.5), realistic, 3d, render, photorealistic, "
    "gradient, smooth, detailed, high resolution, soft lighting, "
    "shadow, isometric, blur, noisy, dither, dithering, decorations, "
    "repetitive elements, outliers"
)


def _resolve_comfy_input_dir() -> Path | None:
    """解析 ComfyUI input 目录路径, 用于复制背景图供 LoadImage 节点加载"""
    config = load_config()
    input_dir = config.comfyui.input_dir.strip()
    if input_dir:
        return Path(input_dir)
    return None


def _resolve_comfy_model_dir() -> Path | None:
    """解析模型目录路径 (comfy_file_path/models/)"""
    config = load_config()
    model_path = config.comfyui.model_path.strip()
    if model_path:
        return Path(model_path)
    return None


def _resolve_comfy_output_dir() -> Path | None:
    """解析 ComfyUI output 目录路径 (comfy_file_path/output/)"""
    config = load_config()
    output_dir = config.comfyui.output_dir.strip()
    if output_dir:
        return Path(output_dir)
    return None


def _find_background_file(bg_id: str) -> Path | None:
    """
    根据 background_image_id (文件名或任务ID) 查找对应的图片文件
    优先在 ComfyUI output 目录查找，其次在本地 OUTPUT_DIR 查找。

    Args:
        bg_id: 材质 ID 或文件名 (如 "gen_9fddf0bd3227" 或 "tgen-background_123.png")

    Returns:
        匹配的文件路径, 未找到时返回 None
    """
    # 优先在 ComfyUI output 目录查找
    comfy_output_dir = _resolve_comfy_output_dir()
    if comfy_output_dir and comfy_output_dir.exists():
        # 如果传入的是完整文件名
        direct_path = comfy_output_dir / bg_id
        if direct_path.is_file():
            return direct_path
        # 按前缀查找
        for filepath in comfy_output_dir.glob(f"{bg_id}*"):
            if filepath.is_file() and filepath.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                return filepath

    # 兼容查找项目 output/textures/
    for filepath in OUTPUT_DIR.glob(f"{bg_id}*.png"):
        return filepath
    return None


def _build_comfy_prompt(
    user_prompt: str,
    negative_prompt: str | None,
    seed: int | None,
    generate_type: str,
    background_filename: str | None = None,
    checkpoint: str | None = None,
    lora: str | None = None,
):
    """
    构建 ComfyUI 工作流: 根据 generate_type 加载不同模板 → 注入用户参数

    Args:
        user_prompt:         正向提示词 (已由前端整合系统提示词 + 材质提示词)
        negative_prompt:     反向提示词
        seed:                随机种子
        generate_type:       "background" | "surface"
        background_filename:  ComfyUI input/ 目录下的背景图文件名 (仅 surface)
        checkpoint:           用户选择的 Checkpoint 文件名
        lora:                 用户选择的 LoRA 文件名
    """
    config = load_config()

    if generate_type == "background":
        editor = WorkflowEditor("background")
        editor.set_resolution(512, 512)
    elif generate_type == "surface":
        editor = WorkflowEditor("surface")
        if background_filename:
            editor.set_background_image(background_filename)
    else:
        raise ValueError(f"不支持的生成类型: '{generate_type}'")

    # 使用默认反向提示词 (如果用户未提供)
    default_negative = SYSTEM_PROMPT_NEGATIVE

    editor.set_prompt(
        positive=user_prompt,
        negative=negative_prompt if negative_prompt else default_negative,
    )
    editor.set_seed(seed)
    editor.set_sampler_params(
        steps=config.generation.default_steps,
        cfg=config.generation.default_cfg,
        sampler=config.generation.default_sampler,
        scheduler=config.generation.default_scheduler,
    )
    prefix = "tgen-background" if generate_type == "background" else "tgen-surface"
    editor.set_filename_prefix(prefix)

    # 应用用户选择的 Checkpoint / LoRA
    if checkpoint:
        editor.set_checkpoint(checkpoint)
    if lora:
        editor.set_lora(lora)

    return editor.get_workflow()


async def _run_generation(task_id: str, workflow: dict, generate_type: str):
    """后台异步执行 SD 生成任务, 并更新 _task_store, 通过 WebSocket 推送进度"""
    config = load_config()
    client = ComfyClient(
        base_url=config.comfyui.base_url,
        timeout=config.comfyui.timeout,
    )

    try:
        _task_store[task_id]["status"] = "generating"
        type_label = "Background" if generate_type == "background" else "Surface"
        await manager.send_progress(
            task_id=task_id, status="generating", progress=10,
            message=f"已提交 ComfyUI {type_label} 生成任务...",
        )

        async def on_progress(pct: int):
            # pct is 0-100 for the current node, map it to overall 10-95%
            overall_pct = 10 + int(pct * 0.85)
            await manager.send_progress(
                task_id=task_id, status="generating", progress=overall_pct,
                message=f"SD 采样中... {pct}%"
            )

        images = await client.generate_with_progress(workflow, progress_callback=on_progress)

        image_urls: list[str] = []
        for i, img_bytes in enumerate(images):
            filename = f"{task_id}_{i}.png"
            filepath = OUTPUT_DIR / filename
            filepath.write_bytes(img_bytes)
            image_urls.append(f"{OUTPUT_URL_PREFIX}/{filename}")

        _task_store[task_id].update({
            "status": "completed",
            "image_urls": image_urls,
        })

        await manager.send_progress(
            task_id=task_id, status="completed", progress=100,
            message=f"{type_label} 生成完成!",
            image_url=image_urls[0] if image_urls else None,
        )
    except Exception as e:
        _task_store[task_id].update({
            "status": "failed",
            "error": str(e),
        })
        await manager.send_progress(
            task_id=task_id, status="failed",
            error=str(e),
        )
    finally:
        await client.close()


# ── API 端点 ─────────────────────────────────────────────────────


@router.post("", response_model=GenerateResponse)
async def generate_texture(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    提交材质纹理生成任务

    支持两种生成类型:
      - generate_type="background": 纯文生图, 从噪声生成背景纹理
      - generate_type="surface":    图生图+遮罩修补, 以已选背景图为底图生成表面纹理
        (需要同时提供 background_image_id)

    SD 固定生成 512×512 原始纹理, 后续在 autotile 合成阶段缩放到目标尺寸
    """
    task_id = f"gen_{uuid.uuid4().hex[:12]}"

    bg_filename: str | None = None
    if request.generate_type == "surface":
        if not request.background_image_id:
            raise HTTPException(
                status_code=400,
                detail="generate_type='surface' 时必须提供 background_image_id",
            )

        bg_file = _find_background_file(request.background_image_id)
        if not bg_file:
            raise HTTPException(
                status_code=404,
                detail=f"背景图未找到: {request.background_image_id} (在 {OUTPUT_DIR} 中搜索)",
            )

        comfy_input_dir = _resolve_comfy_input_dir()
        if not comfy_input_dir or not comfy_input_dir.exists():
            raise HTTPException(
                status_code=500,
                detail=(
                    "ComfyUI input 目录未配置或不存在。"
                    "请在 config/config.yaml 中设置 comfyui.comfy_file_path "
                    "为 ComfyUI 的根目录，程序会自动查找其下的 input/ 子目录"
                ),
            )

        bg_filename = f"{task_id}_bg.png"
        dest_path = comfy_input_dir / bg_filename
        shutil.copy(bg_file, dest_path)

    try:
        workflow = _build_comfy_prompt(
            user_prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            generate_type=request.generate_type,
            background_filename=bg_filename,
            checkpoint=request.checkpoint,
            lora=request.lora,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail=(
                f"ComfyUI 工作流模板文件未找到。"
                f"请确保 comfy/sd-gen-{request.generate_type}.json 存在于项目根目录"
            ),
        )

    _task_store[task_id] = {
        "status": "queued",
        "image_urls": [],
        "error": None,
        "generate_type": request.generate_type,
    }

    background_tasks.add_task(_run_generation, task_id, workflow, request.generate_type)

    return GenerateResponse(
        task_id=task_id,
        status="queued",
        websocket_url=f"ws://127.0.0.1:8000/ws/{task_id}",
    )


# ⚠️ 注意: 以下 3 个特定路由必须在 "/{task_id}" 之前注册, 否则会被 catch-all 匹配


@router.get("/models", response_model=ModelsListResponse)
async def list_models():
    """
    列出可用的 Checkpoint 和 LoRA 文件

    从 config.comfy_model_path 下的 checkpoints/ 和 loras/ 子目录读取
    """
    model_dir = _resolve_comfy_model_dir()
    if not model_dir or not model_dir.exists():
        return ModelsListResponse(checkpoints=[], loras=[])

    checkpoints_dir = model_dir / "checkpoints"
    loras_dir = model_dir / "loras"

    valid_exts = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}

    checkpoints = []
    if checkpoints_dir.exists():
        checkpoints = sorted([
            f.name for f in checkpoints_dir.iterdir()
            if f.is_file() and f.suffix.lower() in valid_exts
        ])

    loras = []
    if loras_dir.exists():
        loras = sorted([
            f.name for f in loras_dir.iterdir()
            if f.is_file() and f.suffix.lower() in valid_exts
        ])

    return ModelsListResponse(checkpoints=checkpoints, loras=loras)


@router.get("/materials/list")
async def list_materials(material_type: str | None = None):
    """
    列出已生成的材质

    参数:
        material_type: 可选过滤 — "background" | "surface"
    """
    materials = []
    for task_id, info in _task_store.items():
        if info.get("status") != "completed":
            continue
        if not info.get("image_urls"):
            continue

        gen_type = info.get("generate_type", "")
        if material_type and gen_type != material_type:
            continue

        materials.append({
            "id": task_id,
            "type": gen_type,
            "image_url": info["image_urls"][0],
        })

    # 按最近优先排序
    materials.reverse()
    return {"materials": materials}


@router.get("/config/prompts", response_model=PromptsConfigResponse)
async def get_prompts_config():
    """返回系统提示词默认值, 供前端预填充输入框"""
    return PromptsConfigResponse(
        system_positive=SYSTEM_PROMPT_POSITIVE,
        system_negative=SYSTEM_PROMPT_NEGATIVE,
    )


@router.get("/comfy-outputs")
async def list_comfy_outputs(prefix: str | None = None):
    """
    列出 ComfyUI output 目录中的图片文件

    供「材质库」页面浏览 ComfyUI 直接输出的图片。
    图片通过 /comfy-output/ 静态路径访问。

    参数:
        prefix: 可选，按文件名前缀过滤（支持逗号分隔多个前缀，如 "tgen-background,tgen-surface"）
    """
    output_dir = _resolve_comfy_output_dir()
    if not output_dir or not output_dir.exists():
        return {"images": [], "total": 0}

    # 解析前缀列表
    prefixes = [p.strip() for p in prefix.split(",")] if prefix else []

    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    images = []
    for f in sorted(output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not f.is_file() or f.suffix.lower() not in image_exts:
            continue
        # 按前缀过滤
        if prefixes and not any(f.name.startswith(p) for p in prefixes):
            continue
        images.append({
            "filename": f.name,
            "url": f"/comfy-output/{f.name}",
            "size_kb": round(f.stat().st_size / 1024, 1),
        })

    return {"images": images, "total": len(images)}


@router.post("/comfy-outputs/upload")
async def upload_comfy_output(
    file: UploadFile = File(...),
    texture_type: str = "background",
):
    """
    上传图片到 ComfyUI output 目录

    接受 multipart/form-data 上传，将文件保存到 comfy_file_path/output/ 下。
    文件会自动按类型重命名为 tgen-background_xxxxx 或 tgen-surface_xxxxx。

    参数:
        texture_type: "background" 或 "surface"，决定文件前缀
    """
    if texture_type not in ("background", "surface"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的纹理类型: '{texture_type}'，仅支持 'background' 或 'surface'",
        )

    output_dir = _resolve_comfy_output_dir()
    if not output_dir or not output_dir.exists():
        raise HTTPException(
            status_code=500,
            detail="ComfyUI output 目录未配置或不存在。请在 config.yaml 中设置 comfy_file_path",
        )

    # 校验扩展名
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {suffix}，仅支持 {', '.join(sorted(allowed_exts))}",
        )

    # 使用前缀 + UUID 重命名，保证与 AI 生成的文件前缀一致
    prefix = "tgen-background" if texture_type == "background" else "tgen-surface"
    new_filename = f"{prefix}_{uuid.uuid4().hex[:8]}{suffix}"

    # 保存文件
    dest_path = output_dir / new_filename
    content = await file.read()
    dest_path.write_bytes(content)

    return {
        "filename": new_filename,
        "original_filename": file.filename,
        "url": f"/comfy-output/{new_filename}",
        "size_kb": round(len(content) / 1024, 1),
    }


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """查询材质生成任务的状态 (含 generate_type 信息)"""
    if task_id not in _task_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_store[task_id]
