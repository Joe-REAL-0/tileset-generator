# src/services/workflow_editor.py
# ComfyUI 工作流 JSON 动态编辑器
# 职责: 根据生成类型加载对应的模板工作流, 通过节点 ID 精准修改参数
#
# 两种模板:
#   - comfy/sd-gen-background.json: 纯文生图, KSampler→EmptyLatentImage
#   - comfy/sd-gen-surface.json:    图生图+遮罩修补, KSampler→SetLatentNoiseMask
#
# 节点 ID 映射 (两个模板共用, 仅连接方式不同):
# ┌─────────┬─────────────────────────┬──────────────────────────────────┐
# │ 节点 ID  │ 类型                    │ 可修改参数                        │
# ├─────────┼─────────────────────────┼──────────────────────────────────┤
# │ 4       │ KSampler                │ seed, steps, cfg, sampler_name,   │
# │         │                         │ scheduler, denoise               │
# │ 7       │ SaveImage               │ filename_prefix                   │
# │ 11      │ EmptyLatentImage        │ width, height, batch_size (仅bg)  │
# │ 19      │ CLIPTextEncode          │ text (正向提示词)                  │
# │ 20      │ CLIPTextEncode          │ text (反向提示词)                  │
# │ 21      │ LoadImage               │ image (用户背景图, 仅surface)      │
# └─────────┴─────────────────────────┴──────────────────────────────────┘

import json
import random
from pathlib import Path
from typing import Any, Literal


class WorkflowEditor:
    """
    根据生成类型加载对应 ComfyUI 模板工作流并动态修改参数

    Usage:
        # Background 生成 (文生图)
        editor = WorkflowEditor("background")
        editor.set_prompt("dirt texture", negative="...")
        editor.set_seed()
        editor.set_resolution(512, 512)
        workflow = editor.get_workflow()

        # Surface 生成 (图生图 + 遮罩修补)
        editor = WorkflowEditor("surface")
        editor.set_prompt("grass texture", negative="...")
        editor.set_seed()
        editor.set_background_image("gen_xxx_0.png")  # 设置背景图文件名
        workflow = editor.get_workflow()
    """

    # 模板文件 (相对于项目根目录)
    TEMPLATES = {
        "background": "comfy/sd-gen-background.json",
        "surface": "comfy/sd-gen-surface.json",
    }

    def __init__(self, template_type: Literal["background", "surface"]):
        if template_type not in self.TEMPLATES:
            raise ValueError(
                f"不支持的模板类型: '{template_type}', "
                f"必须是 {list(self.TEMPLATES.keys())} 之一"
            )
        self._type = template_type
        self._template_path = (
            Path(__file__).resolve().parent.parent.parent
            / self.TEMPLATES[template_type]
        )
        self.template = self._load_template(self._template_path)

    def _load_template(self, path: Path) -> dict[str, Any]:
        """加载 ComfyUI API 格式的工作流 JSON 文件"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── 提示词 (两个模板共用) ──────────────────────────────────────

    def set_prompt(self, positive: str, negative: str | None = None):
        """
        修改正向/反向提示词

        Args:
            positive: 正向提示词 → Node 19 (CLIPTextEncode, 字段 "text")
            negative: 反向提示词 → Node 20 (CLIPTextEncode, 字段 "text")
        """
        if "19" in self.template:
            self.template["19"]["inputs"]["text"] = positive

        if negative is not None and "20" in self.template:
            self.template["20"]["inputs"]["text"] = negative

    # ── Checkpoint / LoRA (两个模板共用) ──────────────────────────

    def set_checkpoint(self, ckpt_name: str):
        """
        修改 Checkpoint (Node 10 - CheckpointLoaderSimple)

        Args:
            ckpt_name: checkpoints 目录下的模型文件名
        """
        if "10" in self.template:
            self.template["10"]["inputs"]["ckpt_name"] = ckpt_name

    def set_lora(self, lora_name: str):
        """
        修改 LoRA (Node 13 - LoraLoader)

        Args:
            lora_name: loras 目录下的 LoRA 文件名
        """
        if "13" in self.template:
            self.template["13"]["inputs"]["lora_name"] = lora_name

    # ── 种子 ──────────────────────────────────────────────────────

    def set_seed(self, seed: int | None = None):
        """
        修改随机种子 (Node 4 - KSampler)

        Args:
            seed: 随机种子, 为 None 或 -1 时自动生成
        """
        if seed is None or seed == -1:
            seed = random.randint(0, 2**32 - 1)

        if "4" in self.template:
            self.template["4"]["inputs"]["seed"] = seed

    # ── 分辨率 (仅 background 模板有 Node 11) ─────────────────────

    def set_resolution(self, width: int = 512, height: int = 512):
        """
        修改输出分辨率 (Node 11 - EmptyLatentImage)

        仅 background 模板有此节点; surface 模板调用此方法为 no-op
        """
        if "11" in self.template:
            self.template["11"]["inputs"]["width"] = width
            self.template["11"]["inputs"]["height"] = height

    # ── 采样器参数 ────────────────────────────────────────────────

    def set_sampler_params(
        self,
        steps: int = 20,
        cfg: float = 8.0,
        sampler: str = "euler",
        scheduler: str = "simple",
    ):
        """
        修改采样器参数 (Node 4 - KSampler)
        """
        if "4" in self.template:
            self.template["4"]["inputs"]["steps"] = steps
            self.template["4"]["inputs"]["cfg"] = cfg
            self.template["4"]["inputs"]["sampler_name"] = sampler
            self.template["4"]["inputs"]["scheduler"] = scheduler

    # ── 背景图 (仅 surface 模板, Node 21 - LoadImage) ─────────────

    def set_background_image(self, filename: str):
        """
        设置 Surface 生成时使用的背景图 (Node 21 - LoadImage)

        将 LoadImage 节点的 image 字段设为 ComfyUI input/ 目录下的文件名。
        调用前需确保该文件已被复制到 ComfyUI 的 input/ 目录。

        Args:
            filename: ComfyUI input/ 目录下的图片文件名 (如 "gen_xxx_0.png")
        """
        if self._type != "surface":
            raise RuntimeError(
                f"set_background_image() 仅适用于 surface 模板, "
                f"当前类型为 '{self._type}'"
            )
        if "21" in self.template:
            self.template["21"]["inputs"]["image"] = filename

    # ── 输出文件名前缀 ────────────────────────────────────────────

    def set_filename_prefix(self, prefix: str):
        """
        修改输出文件名前缀 (Node 7 - SaveImage)
        """
        if "7" in self.template:
            self.template["7"]["inputs"]["filename_prefix"] = prefix

    # ── 获取最终工作流 ────────────────────────────────────────────

    def get_workflow(self) -> dict[str, Any]:
        """
        返回修改后的完整工作流 dict, 可直接提交到 ComfyUI /prompt API
        """
        return self.template
