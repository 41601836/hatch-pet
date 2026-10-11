# 「小蓝」AI 生成操作说明

目标：用即梦/豆包/Midjourney 等任意支持**参考图**的 AI 绘图工具，生成 1 张 base + 9 张动画行条，下载后放入 `inbox/`，剩下的全部由脚本自动完成。

## 第一步：生成 base 形象（先做这张，确认满意再继续）

1. 打开 `prompts/00-base.txt`，复制全部内容作为提示词
2. 上传参考图：`refs/cat-reference.png`
3. 生成，挑一张最满意的下载，**重命名为 `base.png`** 放入 `inbox/`
4. 告诉我一声，我先验证 base 质量

## 第二步：生成 9 张动画行条

base 确认后，逐状态生成。**每个状态都要上传 2 张参考图**：

| 状态 | 提示词文件 | 参考图 1（形象） | 参考图 2（布局） | 下载后命名 |
|---|---|---|---|---|
| idle | `prompts/row-idle.txt` | inbox/base.png | refs/layout-idle.png | `idle.png` |
| running-right | `prompts/row-running-right.txt` | inbox/base.png | refs/layout-running-right.png | `running-right.png` |
| waving | `prompts/row-waving.txt` | inbox/base.png | refs/layout-waving.png | `waving.png` |
| jumping | `prompts/row-jumping.txt` | inbox/base.png | refs/layout-jumping.png | `jumping.png` |
| waiting | `prompts/row-waiting.txt` | inbox/base.png | refs/layout-waiting.png | `waiting.png` |
| running | `prompts/row-running.txt` | inbox/base.png | refs/layout-running.png | `running.png` |
| review | `prompts/row-review.txt` | inbox/base.png | refs/layout-review.png | `review.png` |
| failed | `prompts/row-failed.txt` | inbox/base.png | refs/layout-failed.png | `failed.png` |

`running-left` **不用生成**，脚本会从 running-right 自动镜像。

## 技巧

- 即梦/豆包：选「图片生成」，参考图全部拖进去，提示词粘贴进文本框
- 如果某行生成结果有明显问题（缺帧、姿势糊、混入绿色），直接重新生成该行覆盖即可
- 文件名必须和上表完全一致（小写、带连字符），格式 PNG/JPG 均可

## 完成后

把图全部放进 `inbox/` 后告诉我，我会自动执行：抠图 → 逐帧切分 → 帧级质检 → 镜像左行 → 合成图集 → 校验 → 联络表/GIF 预览 → 打包到 pets/blue/
