# src/main.py
# FastAPI 应用入口
# 职责: 创建 FastAPI 实例, 注册所有路由和中间件, 挂载静态文件
#   启动时验证 ComfyUI 服务连通性, 确保生成管线可用
#
# 运行方式:
#   uvicorn src.main:app --reload --host 127.0.0.1 --port 8000

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.config import load_config, AppConfig
from src.services.comfy_client import ComfyClient

# ── 创建 FastAPI 应用 ──────────────────────────────────────────

config: AppConfig = load_config()

app = FastAPI(
    title="Tileset Generator API",
    description="基于 Stable Diffusion + ComfyUI 的自动 47-tile Autotile 生成系统",
    version="0.1.0",
)

# ── CORS 中间件 ────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册 API 路由 ──────────────────────────────────────────────

from src.routers import generate, tileset, chat, ws

app.include_router(generate.router, prefix="/api")
app.include_router(tileset.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(ws.router)

# ── 挂载静态文件 (前端) ────────────────────────────────────────

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

# ── 输出目录文件服务 ────────────────────────────────────────────

output_dir = Path(__file__).resolve().parent.parent / "output"
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / "textures").mkdir(exist_ok=True)
(output_dir / "tilesets").mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


# ── 启动事件: 验证 ComfyUI 连通性 ──────────────────────────────

@app.on_event("startup")
async def startup_check():
    """
    启动时检查 ComfyUI 服务是否可达。
    如果不可达, 打印警告但不阻止服务启动 (允许后续手动修复)。
    """
    client = ComfyClient(
        base_url=config.comfyui.base_url,
        timeout=10,
    )
    try:
        # 尝试访问 ComfyUI 根路径确认服务存活
        http_client = await client._get_client()
        resp = await http_client.get("/prompt")
        # /prompt GET 通常返回 405 (Method Not Allowed), 但说明服务在运行
        print(f"[startup] ComfyUI 服务检测完成: {config.comfyui.base_url}")
    except Exception as e:
        print(
            f"[startup] ⚠️  警告: 无法连接到 ComfyUI 服务 ({config.comfyui.base_url}): {e}\n"
            f"         请确保 ComfyUI 已启动并监听在 {config.comfyui.base_url}"
        )
    finally:
        await client.close()


# ── 健康检查端点 ────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "Tileset Generator API"}
