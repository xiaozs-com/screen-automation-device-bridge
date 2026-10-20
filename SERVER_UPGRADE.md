# 服务器升级：支持共享专家的本机小助手桥接

本包用于已有两个桥接模块的 Octop。每个用户在自己的宠物中选择同一个共享专家即可，无需复制专家。

## 更新

1. 将本完整 ZIP 上传并解压到 `/home/admin/pd-chat-bridge-shared/`。三个 Python 文件必须来自同一包，不要只替换 update_bridge.py。保留原安装目录和 install-records。
2. 使用运行 Octop 的同一用户和 Python 环境预览；此步不修改安装文件：

```bash
/home/admin/.octop/venv/bin/python /home/admin/pd-chat-bridge-shared/update_bridge.py
```

3. 只有输出“检查通过”后才停止服务并更新：

```bash
octop service stop &&
/home/admin/.octop/venv/bin/python /home/admin/pd-chat-bridge-shared/update_bridge.py --apply &&
octop service start
```

若服务不是由 octop service 管理，沿用原管理方式。脚本不自行上传、停止或重启服务。更新失败时按输出和 rollback.txt 处理；自动恢复未全部成功时保持服务停止。

## 修改范围与回退

- 更新 site-packages/pd_chat_bridge.py 和 pd_cli_proxy.py。
- 检查、恢复或迁移 octop/api/routers/chat/ws.py 的四处桥接接线；适配 prepared / prepared_early，保留 Octop 原有用户访问检查。
- 为 octop/infra/agents/manager.py 增加 pd_helper_cli 工具注册。
- 改动前备份到本包 install-records/bridge-时间/；rollback.txt 记录每个备份对应的原路径，并保存 ws.py 和 manager.py 的差异。已符合要求的 Octop 文件不重复修改。
- 写入失败会尝试恢复已改文件。手动回退时停止服务，按 rollback.txt 复制所有备份，再按原方式启动。

不修改 Octop API、服务端口、专家归属或共享权限；不修改 Pet、Device Bridge 本机执行器或 Helper。

## 使用和验收

从各自宠物向共享专家发送消息，要求调用 **pd_helper_cli**：

```json
{"args":["cli","window","list-visible"]}
```

或调用 `["cli","describe"]` 查看本机命令。stdin 是可选文本；工作流源文件自动上传、--pd-upload/--pd-download 与私有 CLI 代理一致。工具上传的服务器文件限专家工作区内，相对路径按该工作区解析。

该工具不需要 shell/execute，但不会额外提供通用服务器进程执行能力。没有对应用户及线程的唯一宠物连接会返回错误，不会回退到专家所有者的设备。网页聊天不能建立宠物桥接。

共享模式不生成/覆盖专家根目录的 .pd-chat-caller.json；旧文件可能保留，因此不要用其有无判断共享桥接状态。共享工作区的旧 pd-helper 默认凭据调用会被拒绝，请使用 pd_helper_cli。私有专家仍兼容原 Skill/CLI 代理。

两人同时测试同一共享专家：A 的查询应返回 A 的电脑信息，B 的查询返回 B 的电脑信息；A 断开后 A 调用失败，B 仍正常。截图和返回文件按用户/线程分目录保存，此功能不改变 Octop 共享工作区本身的文件访问权限。

本包需在实际服务器和两台宠物上完成上述验收；本地模拟和工具框架测试不能替代真实部署。

## 2026-10-20 验证记录与未完成项

- 本地 Python 3.12 回归：52 项，50 项通过，2 项本机执行器环境测试跳过；包含真实 LangChain/LangGraph 工具调用、共享用户并发隔离、首次安装、旧补丁迁移和失败恢复。
- 用户回传：服务器更新完成并产生 install-records 备份；从 Windows 宠物调用共享专家的 pd_helper_cli 执行 window list-visible，外层 ok=true、exit_code=0、stderr 为空，内层 ok=true，返回 18 个窗口。此项证明该账号的基础调用链已跑通。
- 双账号分别调用各自电脑、断开一方后另一方继续调用：尚未完成真实部署验收。
- 用户回传 cli status 返回“CLI 输出过大”。本机执行器 native/src/lib.rs 对 stdout/stderr 各限制 1 MiB；具体超限输出来源尚未在用户电脑测量，尚未修复。初次联调优先使用上述窗口查询，不应把单次窗口查询成功当作全部命令或双用户验收完成。
