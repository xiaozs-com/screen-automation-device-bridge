# PD 按需 CLI 桥接

当前 Windows 发布配套为 Paldee Pet 0.2.3。桥接支持完整小助手 CLI、标准输入和文件往返；普通聊天不调用 CLI。复用原聊天 WS/WSS，不要求额外配置或公网端口，不使用 SSH/MCP。

- [完整 CLI 与传输用法](FULL_CLI_USAGE.md)
- [已有 Octop 服务器的模块升级](SERVER_UPGRADE.md)

本机桥接仍是独立工程，按 MIT 分发。服务端只新增/更新两个独立模块，保留原 ws.py 四处接线；后续 Octop 更新仍需检查该补丁兼容性。服务器状态以用户部署与验收为准；本轮不自动上传或发布。

macOS 执行器与 Windows 共用 Rust 实现，支持 Intel/Apple Silicon 本机构建。见 [Mac 构建与真机测试](MACOS_TESTING.md)。Mac 聊天集成还需宠物端加载对应组件。
