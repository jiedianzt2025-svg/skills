---
name: wechat-article-link-export
description: 接收任意一篇微信公众号文章 URL，识别公众号，使用 Agent Reach 的 Exa MCP 搜索公开历史入口，遍历公开文章列表并导出 CSV。用户要求获取公众号文章链接、批量读取公众号历史文章 URL、生成 CSV、安装或配置 Agent Reach 微信公众号渠道时使用。
---

# 公众号读取链接

接收用户提供的一篇 `https://mp.weixin.qq.com/s/...` 文章 URL，导出该公众号公开可检索的文章链接 CSV。

## 边界

- 仅抓取公开页面，不绕过登录、验证码或访问控制。
- CSV 必须区分 `已确认微信原始URL` 与 `公开列表镜像URL`。
- 镜像站若要求登录后才能跳转原文，不得把镜像 URL 描述成微信原始 URL。
- 不上传 Cookie、Token、用户目录中的现有配置、抓取结果或源码缓存。

## 首次设置

Windows 环境优先运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap-agent-reach.ps1
```

脚本会：

1. 在 `~/.agent-reach-venv` 创建隔离虚拟环境。
2. 安装 Agent Reach。若官方源码在 Windows 上触发重复 `force-include` 打包错误，使用本地兼容修复。
3. 安装 `mcporter`，注册公开 Exa MCP：`https://mcp.exa.ai/mcp`。
4. 将 `mcporter.json` 放在 `~/.agent-reach/config/`。
5. 运行 `agent-reach doctor`。

macOS/Linux 或手动设置请读取 [references/setup.md](references/setup.md)。

## 导出流程

运行：

```powershell
python scripts/export-wechat-links.py "https://mp.weixin.qq.com/s/..."
```

可选参数：

```powershell
python scripts/export-wechat-links.py "https://mp.weixin.qq.com/s/..." --column-url "http://www.jintiankansha.me/column/..." --output "articles.csv"
```

脚本执行以下步骤：

1. 从种子文章公开 HTML 中提取标题、公众号名称和账号 ID。
2. 使用 `mcporter + Exa MCP` 搜索公众号公开历史入口。
3. 尝试定位 `jintiankansha.me` 的公开专栏页。
4. 遍历公开分页并去重。
5. 导出 UTF-8 BOM CSV，便于 Excel 直接打开。

如果自动定位不到公开专栏，将脚本打印的搜索结果交给用户，并请用户提供可公开访问的专栏 URL 或更多文章 URL。仍然输出包含种子文章的 CSV。

## 输出说明

CSV 字段：

- `公众号`
- `标题`
- `链接`
- `链接类型`
- `列表页`
- `备注`

向用户报告文章数量、去重数量、CSV 路径和公开索引限制。