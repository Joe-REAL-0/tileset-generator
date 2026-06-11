# src/routers/generate.py
# 材质生成 API 路由
# 职责: 处理 "生成材质" 按钮的请求
#   POST /api/generate          - 提交材质纹理生成任务
#   GET  /api/generate/{task_id} - 查询任务状态
#
# 流程: 接收提示词 → WorkflowEditor 注入参数 → ComfyUI 提交 → 返回 task_id
#       前端通过 WebSocket 获取实时进度推送

import uuid
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from src.schemas.generate import GenerateRequest, GenerateResponse
from src.services.workflow_editor import WorkflowEditor
from src.services.comfy_client import ComfyClient
from src.config import load_config

router = APIRouter(prefix="/generate", tags=["generate"])

# 简易任务状态存储 (后续 Phase 6 替换为 SQLite)
_task_store: dict[str, dict] = {}

# 输出目录
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "textures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_comfy_prompt(user_prompt: str, negative_prompt: str | None, seed: int | None):
    """构建 ComfyUI 工作流: 加载模板 → 注入用户参数"""
    config = load_config()
    editor = WorkflowEditor()

    # 使用默认负向提示词 (如果用户未提供)
    default_negative = (
        "highly detailed realistic, 3D render, octane render, ray tracing, "
        "soft edges, blurry, gradients, messy pixels, noise, organic curves, "
        "real photography, complex lighting, text, watermark, shadows"
    )

    editor.set_prompt(
        positive=user_prompt,
        negative=negative_prompt if negative_prompt else default_negative,
    )
    editor.set_seed(seed)
    editor.set_resolution(512, 512)
    editor.set_sampler_params(
        steps=config.generation.default_steps,
        cfg=config.generation.default_cfg,
        sampler=config.generation.default_sampler,
        scheduler=config.generation.default_scheduler,
    )
    editor.set_filename_prefix("tileset_generator")

    return editor.get_workflow()


async def _run_generation(task_id: str, workflow: dict):
    """后台异步执行 SD 生成任务, 并更新 _task_store"""
    config = load_config()
    client = ComfyClient(
        base_url=config.comfyui.base_url,
        timeout=config.comfyui.timeout,
    )

    try:
        _task_store[task_id]["status"] = "generating"

        images = await client.generate(workflow)

        # 保存生成的图片
        saved_paths = []
        for i, img_bytes in enumerate(images):
            filename = f"{task_id}_{i}.png"
            filepath = OUTPUT_DIR / filename
            filepath.write_bytes(img_bytes)
            saved_paths.append(str(filepath))

        _task_store[task_id].update({
            "status": "completed",
            "image_paths": saved_paths,
        })
    except Exception as e:
        _task_store[task_id].update({
            "status": "failed",
            "error": str(e),
        })
    finally:
        await client.close()


@router.post("", response_model=GenerateResponse)
async def generate_texture(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    提交材质纹理生成任务 (按钮1: 生成材质)

    SD 固定生成 512×512 原始纹理, 后续在 autotile 合成阶段缩放到目标尺寸
    """
    task_id = f"gen_{uuid.uuid4().hex[:12]}"

    # 构建工作流
    try:
        workflow = _build_comfy_prompt(
            user_prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="ComfyUI 工作流模板文件 (comfy/sdgen-api.json) 未找到",
        )

    # 初始化任务状态
    _task_store[task_id] = {
        "status": "queued",
        "image_paths": [],
        "error": None,
    }

    # 提交后台异步生成任务
    background_tasks.add_task(_run_generation, task_id, workflow)

    return GenerateResponse(
        task_id=task_id,
        status="queued",
        websocket_url=f"ws://127.0.0.1:8000/ws/{task_id}",
    )


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """查询材质生成任务的状态"""
    if task_id not in _task_store:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_store[task_id]
