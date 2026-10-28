# PD 按需 CLI 桥接

当前 Windows 发布配套为 Paldee Pet 0.2.3。桥接支持完整小助手 CLI、标准输入和文件往返；普通聊天不调用 CLI。复用原聊天 WS/WSS，不要求额外配置或公网端口，不使用 SSH/MCP。

- [上游精确版本与升级迁移](UPSTREAM_BASELINE.md)
- [完整 CLI 与传输用法](FULL_CLI_USAGE.md)
- [已有 Octop 服务器的模块升级](SERVER_UPGRADE.md)
- [Octop 网页静态 Logo 与机器人外观（无需编译）](branding/README.md)

本机桥接仍是独立工程，按 MIT 分发。服务器更新脚本更新两个独立模块，检查并备份 Octop 的 ws.py 和专家工具注册文件 manager.py。支持私有和共享专家：pd_helper_cli 从服务端当前用户/线程取得身份，只调用对应宠物；共享模式不向专家根目录写入用户桥接凭据。不兼容时停止，写入失败尝试恢复备份。服务器状态以用户部署与验收为准；本轮不自动上传或发布。

macOS 执行器与 Windows 共用 Rust 实现，支持 Intel/Apple Silicon 本机构建。见 [Mac 构建与真机测试](MACOS_TESTING.md)。Mac 聊天集成还需宠物端加载对应组件。

共享专家无需为每个账号重建。先使用完整服务器更新包，再从各自的宠物选择共享专家并发消息。共享用户调用 pd_helper_cli，不要求启用 shell/execute；此工具不会给专家增加通用服务器命令执行权限。
