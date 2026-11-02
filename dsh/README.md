# dsh-Onmyoji-Guide · DeepSeek Harness 插件

在 DeepSeek Harness 里提供《阴阳师》查询能力，与仓库根目录的 AstrBot 插件共用同一份 `data/` 知识库。

## 工具

| 工具 | 作用 |
| --- | --- |
| `yys_lookup` | 式神/御魂/阴阳师面板、技能列表、御魂推荐 |
| `yys_skills` | 式神完整技能（升级效果、buff 词条） |
| `yys_calc` | 满暴判定、期望系数、攻击×暴伤 |
| `yys_guide` | 网易大神最新攻略（优先阵容码） |
| `yys_card` | 返回式神/御魂/阴阳师介绍图卡路径 |

## 安装

在 DSH 的插件管理里安装本目录（`yys/dsh`），或使用插件管理工具：

```
plugin_manager install_bundle target = <仓库绝对路径>/dsh
```

安装后插件名为 `dsh-onmyoji-guide`（显示名 dsh-Onmyoji-Guide），工具会出现在可用工具列表里。

## 数据

默认读取 `../data/`（相对本目录）。如果单独复制了 `dsh/`，用环境变量指定：

```
YYS_DATA_DIR=<仓库路径>/data
```

## 说明

- `yys_guide` 需要联网（网易大神公开接口 + 360 搜索）。
- 图卡路径默认是 `../data/cards/`。
- 本插件由 `deepseek-v4.1flash-1017` 生成，非官方工具。
