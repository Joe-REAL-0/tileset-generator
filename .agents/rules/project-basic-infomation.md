---
trigger: always_on
---

这是我的一个使用python结合comfyUI工作流生成tileset的项目，我们tile分割为两部分，底层的background，外围的surface，surface分割为八个部分，环绕background一圈。八个部分在各自在显示与不显示的状态下切换，排列组合后，形成完整的tile。
项目使用comfyUI的API来生成background和surface，然后使用python脚本将其一键组合成tileset。
前端界面分为三个部分，分别是“生成材质”，“材质库”，“生成图集”。
“生成材质”部分的目标是，由用户攥写材质的keyword，调用comfyUI的API进行生成。
“材质库”读取comfyUI的output目录，筛选出所有与该项目有关的素材。
“生成图集”部分实现的功能是从材质库中选择一个background和surface，调用python脚本生成tileset，将生成的tileset展示给用户。