# 设置参考

## 可公开配置

本技能只需要公开 Exa MCP 地址：

```json
{
  "mcpServers": {
    "exa": {
      "baseUrl": "https://mcp.exa.ai/mcp"
    }
  }
}
```

将其保存到：

- Windows：`%USERPROFILE%\.agent-reach\config\mcporter.json`
- macOS/Linux：`~/.agent-reach/config/mcporter.json`

不要把 Cookie、Token 或已有私人配置提交到 GitHub。

## Windows

优先运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap-agent-reach.ps1
```

安装脚本会处理 Agent Reach `v1.4.0` 源码在 Windows 上的重复 `force-include` 打包问题。修复仅应用于用户目录下的本地源码副本。

## macOS/Linux

Agent Reach 官方推荐使用 `pipx`：

```bash
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
npm install -g mcporter
mkdir -p ~/.agent-reach/config
mcporter --config ~/.agent-reach/config/mcporter.json config add exa https://mcp.exa.ai/mcp
agent-reach doctor
```

如果 Python 受 PEP 668 管理，使用虚拟环境：

```bash
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
```

## 限制

微信与镜像站可能限制批量原文跳转。脚本不会绕过登录墙。公开列表镜像 URL 与已确认微信原始 URL 会在 CSV 中分开标注。
