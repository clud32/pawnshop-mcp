# 深空当铺 MCP

在 MCP 客户端里问「下周要交多少租，手头哪些货能卖？」服务从最近的存档读取现金、库存和物品状态，从本机游戏文件提取难度参数、物品基础价和手册说明，还可以按交租周期生成经营周报。

## 本地运行

准备 64 位 Python 3.11 和 Windows 版《深空当铺》。服务只用 Python 标准库，在 CPU 上完成索引和检索。先在仓库根目录运行以下命令，确认工具能列出自己的存档。

```powershell
$env:PS_GAME_DIR = "D:/SteamLibrary/steamapps/common/Probably Stolen"
python -X utf8 server.py saves
```

在支持 stdio 的 MCP 客户端中添加以下配置，把 `D:/repos/pawnshop-mcp` 和游戏目录换成本机路径。如果桌面客户端找不到 `python`，可在 PowerShell 运行 `(Get-Command python).Source`，把结果填入 `command`。保存配置后重新加载服务。

```json
{
  "mcpServers": {
    "pawnshop": {
      "command": "python",
      "args": [
        "-X",
        "utf8",
        "D:/repos/pawnshop-mcp/server.py"
      ],
      "env": {
        "PS_GAME_DIR": "D:/SteamLibrary/steamapps/common/Probably Stolen"
      }
    }
  }
}
```

存档默认从 Windows 用户目录的 `AppData/LocalLow/Questing Goose Studio/Probably Stolen` 读取。可以通过 `PS_SAVE_DIR` 指定含 `saves_index.es3` 的文件夹。`auto` 读取最近保存的档位，也可通过 `save` 参数传入指定档位号。存档只反映游戏最近一次落盘时的状态。

## 能查什么

| 用途 | MCP 工具 |
| --- | --- |
| 经营与存档 | `overview`、`saves`、`save_get`、`inventory`、`gamelog` |
| 交租与经营记录 | `weekly_report`、`weekly_plan`、`journal` |
| 攻略知识库 | `kb_search`、`kb_get`、`kb_add_seed`、`kb_rebuild` |

例如，让客户端用 `inventory` 查展柜中的物品。`unitValue` 是存档中考虑了品相、真伪等因素的单件数值，`baseValue` 是能从游戏代码读出的基础值。问到下次涨租时，可让客户端用 `kb_get` 取 `num:difficulty`，再结合当前难度和账单计算。 附有可直接交给客户端的[陪玩提示词](陪玩提示词.md)。

索引整合中英文本地化条目、手册、攻略笔记，以及从本地 Unity 资源和 .NET 程序集读出的部分数值。 检索使用 BM25，中文按单字和相邻双字切分，对名称和攻略笔记加权。`kb_search` 返回片段与 ID，`kb_get` 按 ID 返回整篇。游戏更新后可用 `kb_rebuild` 从本机文件重新索引。

## 本地数据与许可

游戏安装目录和存档是只读输入。周报、经营日志、个人笔记和索引缓存写入仓库根目录下的 `.local/`，也可用 `PS_STATE_DIR` 指定其他目录。读取局面时可能自动生成已到期的周报。程序自带的攻略笔记在 `kb_seeds/`，`kb_add_seed` 默认写入 `.local/kb_seeds/`。

本项目的代码、测试和自编文档使用 [MIT 许可证](LICENSE)。游戏本体、游戏程序集和资源包由玩家自行安装。个人存档、历史报告和从游戏生成的完整索引均仅保存在玩家本机。

## 测试环境声明

2026-11-24 在 Windows 11 家庭中文版（10.0.26200，AMD64）、CPython 3.11.9 64 位、Steam Windows 版 Build ID `26525552` 上运行。MCP 客户端通过子进程的标准输入输出协商协议 `2025-06-18`。真实读档测试使用最近保存的档位及本机游戏资源。 每次集成测试单独创建临时状态目录，从空缓存开始。详细环境与原始计数见[测试记录](tests/results.json)。

## 测试结论

| 检查项目 | 本次结果 |
| --- | --- |
| 无游戏安装的回归测试 | 6/6 通过，覆盖握手、工具列表、读档、未知工具和笔记写入范围，另验证大库存存档的总览仍能返回有效 JSON |
| 真实安装的 stdio 集成测试 | 发现 12 个工具，调用其中 7 个。读取现金、解析展柜库存并生成交租周报，档位索引和读取的存档 SHA-256 在测试前后一致 |
| BM25 首条命中 | 95/120（79.2%） |
| BM25 前三条命中 | 110/120（91.7%），从本机游戏和 21 条随附笔记构建 2,855 篇文档 |

[评测题集](tests/queries.tsv)中的每个问题标有一个或多个可接受的文档 ID。前 K 条结果出现任一参考 ID 即计一次命中。题集包含同一机制的多种问法，衡量的是这些问题的资料召回能力。10 道题未在前三条命中，包括熔炉的俗称以及人情点的间接问法。 回答质量、通关成功率、其他操作系统和桌面客户端界面均未纳入本轮测试。

在仓库根目录可复跑以下命令。第一条使用合成存档，第二条需要游戏安装和存档，第三条按当前安装重建知识库，输出命中统计和未命中问题。

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 tests/live_smoke.py
python -X utf8 tests/evaluate.py
```
