# src/config.py
# 配置加载模块
# 职责: 加载 YAML 配置文件, 并用 .env 环境变量覆盖敏感/可变配置项
# 最终返回强类型的 AppConfig 实例, 供整个应用使用

import os
from pathlib import Path
from pydantic import BaseModel, model_validator
from dotenv import load_dotenv
import yaml


class ComfyUIConfig(BaseModel):
    """ComfyUI 服务连接配置

    comfy_file_path 为 ComfyUI 根目录，其下需包含 input/、models/、output/ 子目录。
    input_dir / model_path / output_dir 三个属性自动从 comfy_file_path 派生。
    """
    base_url: str = "http://127.0.0.1:8188"
    timeout: int = 300
    poll_interval: float = 1.0
    comfy_file_path: str = ""  # ComfyUI 根目录绝对路径

    @property
    def input_dir(self) -> str:
        """ComfyUI input/ 目录 (Surface 生成时需复制背景图到此)"""
        if self.comfy_file_path:
            return str(Path(self.comfy_file_path) / "input")
        return ""

    @property
    def model_path(self) -> str:
        """模型根目录, 包含 checkpoints/ 和 loras/ 子目录"""
        if self.comfy_file_path:
            return str(Path(self.comfy_file_path) / "models")
        return ""

    @property
    def output_dir(self) -> str:
        """ComfyUI output/ 目录, 存放 ComfyUI 生成的所有图片"""
        if self.comfy_file_path:
            return str(Path(self.comfy_file_path) / "output")
        return ""


class GenerationConfig(BaseModel):
    """SD 生成默认参数"""
    default_steps: int = 20
    default_cfg: float = 8.0
    default_sampler: str = "euler"
    default_scheduler: str = "simple"
    surface_background_tolerance: int = 15


class TilesetConfig(BaseModel):
    """Tileset 拼合参数"""
    output_format: str = "png"


class ServerConfig(BaseModel):
    """FastAPI 服务配置"""
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["*"]


class AppConfig(BaseModel):
    """应用全局配置"""
    comfyui: ComfyUIConfig = ComfyUIConfig()
    generation: GenerationConfig = GenerationConfig()
    tileset: TilesetConfig = TilesetConfig()
    server: ServerConfig = ServerConfig()
    output_tile_sizes: list[int] = [16, 32, 64, 128]
    default_tile_size: int = 32


def load_config(config_path: str | None = None) -> AppConfig:
    """
    加载配置: YAML 文件 → 环境变量覆盖 → AppConfig 实例

    优先级: .env 环境变量 > config/config.yaml > Pydantic 默认值
    """
    load_dotenv()

    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

    app_config = AppConfig()

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        if yaml_data:
            if "comfyui" in yaml_data:
                app_config.comfyui = ComfyUIConfig(**yaml_data["comfyui"])
            if "generation" in yaml_data:
                app_config.generation = GenerationConfig(**yaml_data["generation"])
            if "tileset" in yaml_data:
                app_config.tileset = TilesetConfig(**yaml_data["tileset"])
            if "server" in yaml_data:
                app_config.server = ServerConfig(**yaml_data["server"])
            if "output_tile_sizes" in yaml_data:
                app_config.output_tile_sizes = yaml_data["output_tile_sizes"]
            if "default_tile_size" in yaml_data:
                app_config.default_tile_size = yaml_data["default_tile_size"]

    # .env 覆盖
    comfyui_url = os.getenv("COMFYUI_BASE_URL")
    if comfyui_url:
        app_config.comfyui.base_url = comfyui_url

    server_port = os.getenv("SERVER_PORT")
    if server_port:
        app_config.server.port = int(server_port)

    return app_config
