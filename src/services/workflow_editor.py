# src/services/workflow_editor.py
# ComfyUI 工作流 JSON 动态编辑器
# 职责: 加载模板工作流 (comfy/sdgen-api.json), 通过节点 ID 精准修改参数
#   - set_prompt():         注入正向/反向提示词 (节点 2 和 5)
#   - set_seed():           修改随机种子 (节点 4 - KSampler)
#   - set_resolution():     修改输出分辨率 (节点 11 - EmptyLatentImage)
#   - set_sampler_params(): 修改采样器参数 (节点 4)
#   - get_workflow():       返回修改后的工作流 dict, 可直接提交到 ComfyUI

import json
import random
from pathlib import Path
from typing import Any


class WorkflowEditor:
    """
    加载 comfy/sdgen-api.json 模板工作流并动态修改参数

    节点 ID 映射表 (依据 comfy/sdgen-api.json):
    ┌─────────┬─────────────────────────┬──────────────────────────────────┐
    │ 节点 ID  │ 类型                    │ 可修改参数                        │
    ├─────────┼─────────────────────────┼──────────────────────────────────┤
    │ 2       │ CLIPTextEncodeLumina2   │ text (正向提示词)                 │
    │ 5       │ CLIPTextEncodeLumina2   │ text (反向提示词)                 │
    │ 4       │ KSampler                │ seed, steps, cfg, sampler, scheduler │
    │ 11      │ EmptyLatentImage        │ width, height, batch_size         │
    │ 7       │ SaveImage               │ filename_prefix                   │
    └─────────┴─────────────────────────┴──────────────────────────────────┘
    """

    # ComfyUI 工作流模板路径 (相对于项目根目录)
    DEFAULT_TEMPLATE = "comfy/sdgen-api.json"

    def __init__(self, template_path: str | None = None):
        if template_path is None:
            template_path = (
                Path(__file__).resolve().parent.parent.parent
                / self.DEFAULT_TEMPLATE
            )
        self.template = self._load_template(template_path)

    def _load_template(self, path: str | Path) -> dict[str, Any]:
        """加载 ComfyUI API 格式的工作流 JSON 文件"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def set_prompt(self, positive: str, negative: str | None = None):
        """
        修改提示词

        Args:
            positive: 正向提示词 (注入到节点 2)
            negative: 反向提示词 (注入到节点 5), 为 None 时使用默认负向提示词
        """
        # 节点 2: 正向提示词
        if "2" in self.template:
            self.template["2"]["inputs"]["text"] = positive

        # 节点 5: 反向提示词
        if negative is not None and "5" in self.template:
            self.template["5"]["inputs"]["text"] = negative

    def set_seed(self, seed: int | None = None):
        """
        修改随机种子 (节点 4 - KSampler)

        Args:
            seed: 随机种子, 为 None 或 -1 时生成随机种子
        """
        if seed is None or seed == -1:
            seed = random.randint(0, 2**32 - 1)

        if "4" in self.template:
            self.template["4"]["inputs"]["seed"] = seed

    def set_resolution(self, width: int = 512, height: int = 512):
        """
        修改输出分辨率 (节点 11 - EmptyLatentImage)

        默认 512×512, 为 SD3.5 Medium 的最佳生成尺寸
        """
        if "11" in self.template:
            self.template["11"]["inputs"]["width"] = width
            self.template["11"]["inputs"]["height"] = height

    def set_sampler_params(
        self,
        steps: int = 20,
        cfg: float = 8.0,
        sampler: str = "euler",
        scheduler: str = "simple",
    ):
        """
        修改采样器参数 (节点 4 - KSampler)
        """
        if "4" in self.template:
            self.template["4"]["inputs"]["steps"] = steps
            self.template["4"]["inputs"]["cfg"] = cfg
            self.template["4"]["inputs"]["sampler_name"] = sampler
            self.template["4"]["inputs"]["scheduler"] = scheduler

    def set_filename_prefix(self, prefix: str):
        """
        修改输出文件名前缀 (节点 7 - SaveImage)
        """
        if "7" in self.template:
            self.template["7"]["inputs"]["filename_prefix"] = prefix

    def get_workflow(self) -> dict[str, Any]:
        """
        返回修改后的完整工作流 dict, 可直接作为 ComfyUI /prompt API 的请求体
        """
        return self.template
