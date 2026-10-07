# PD 按需 CLI 桥接 v2（开发测试版）
普通聊天、联网查询和其他服务器工具照常运行。只有原 screen-automation Skill 调用小助手 CLI 时，才经当前聊天 WebSocket 发到本机；不是全局 execute 代理。无需 SSH/MCP/第二条设备连接。

Linux 服务端安装一次独立适配器、CLI shim 与聊天协议小补丁。每次私有 Agent 聊天连接时，自动发现现有 screen-automation* Skill 的 resolve_cli.sh，添加 Linux 代理入口并保留原文件备份；以后新增 Agent/Skill 无需人工指定 ID 或再打补丁。没有新增独立窗口 Skill。原 Skill 的其余内容保留。
代理依赖服务器工具执行目录为 Agent 工作目录（Octop 标准行为）；自定义 sandbox/container 配置需要另行核对。

Windows 宠物经现有聊天 WebSocket 按请求执行受限 CLI，不额外显示桥接授权弹窗。断线、错误会话、未知方法和未启用命令均不执行；WS 与 WSS 均支持。只启动已安装的小助手，不经过 shell。当前启用 status/describe/capabilities/health/access list 及 window/screen/mouse/keyboard/ocr 家族；工作流运行、文件上传及其他家族尚未开放。
CLI stdout、stderr、exit_code 原样回传。screen capture 的 PNG（最多 4 MiB）传回服务器、落盘并替换返回 path；不能把 Windows 本地路径当成服务器可读文件。

范围：Windows 本机、Linux 1.0.2b6 官方包已验证补丁生成；私有 Agent，多设备冲突拒绝。共享 Agent、多进程服务器、隔离 sandbox、Mac 本机、正式签名组件分发尚不支持。真实远程 AI、原生确认对话框及屏幕输入操作仍须人工验收。
用户服务器尚未修改。按用户要求，复用现有 HTTP/WS 聊天连接，不要求 HTTPS/WSS 或改端口；未来升级 HTTPS 时同样支持 WSS。
安装与回退见 上传安装说明.md。服务端升级可能覆盖 ws.py，须重查指纹及补丁，不是免维护插件。

## browser 命令修复与已安装服务器更新
browser 家族已补齐到全部桥接校验层。普通错误不再统称 bridge unavailable。
已安装服务器无需重打 ws.py 补丁：上传解压本包，先用 /home/admin/.octop/venv/bin/python update_bridge.py 预览，然后停止服务，使用同一命令加 --apply 更新两个独立模块，按原方式重启。每次有原文件备份。不要再次运行 install_server.py --apply。本机组件与 Pet 同时需要本次版本。当前 Pet 不显示桥接授权弹窗；命令限制及错误提示保留。


## 本地源码管理（2026-10-08）

工程现独立纳入本地 Git；build、native/target、install-records 和凭据文件不提交。
Pet 接入源码仍在 D:/ai/OctopPet，主程序仍在 D:/ai/screen-automation-helper。
本文早期的服务器未部署与原生确认说明属于历史阶段；真实服务器状态以实际安装记录和用户验收为准。本轮仅本地整理和单元测试，不操作远端。
