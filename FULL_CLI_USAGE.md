# 完整小助手 CLI 与文件传输（Paldee Pet 0.2.3）

原有命令直接使用，桥接不再按命令类别过滤：

```bash
pd-helper cli describe
pd-helper cli workflow schema sdk
pd-helper cli workflow inspect /home/admin/my-workflow
pd-helper cli workflow install /home/admin/my-workflow
pd-helper cli workflow show workflow-id
pd-helper cli workflow validate workflow-id
printf '%s' '{}' | pd-helper cli screen-memory search
```

只有本机小助手本身存在的命令才能成功；参数、权限或功能未安装的错误由实际 CLI 返回，不由桥接伪装成“超出支持范围”。以后新增 CLI 子命令无需再修改桥接白名单。

workflow install/inspect 的服务器文件或目录会自动复制到本机。*-file 输入选项（如 --object-file / --action-file）同样自动传文件。普通 Windows 路径在服务器不存在时保持原样，仍操作本机文件。

其他输入文件可以显式传送：

```bash
pd-helper --pd-upload '3=/home/admin/source.zip' cli workflow inspect placeholder
```

位置索引按移除桥接选项后的参数计算，cli 为 0、workflow 为 1、inspect 为 2、文件参数为 3；命令参数仍是独立字符串，不经过 shell。上传目录保留相对结构及二进制内容，不传符号链接。

读取本机现有流程源码：先 workflow show 获取 _meta.package_dir，再取回该目录：

```bash
pd-helper --pd-download 'C:\Users\David\Xiaozs\ScreenAutomationHelper\workflows\workflow-id' cli workflow show workflow-id
```

JSON 的 bridge_files[].path 是服务器可读路径，AI 可以通过原服务器文件工具读取其中 workflow.py / workflow.md / workflow.json。source 保留原 Windows 路径；不把 Windows 路径误当服务器文件。bridge_uploaded_files 返回复制后可继续使用的本机路径。

标准输入原样 UTF-8 传递；单次上限 1 MiB。文件批次最多 128 个文件、合计 4 MiB。超限、越界路径、损坏编码与真实 CLI 错误有明确提示。这些是消息/资源边界，不是命令类别白名单。大文件可由 CLI 使用本机已有路径、可下载的 URL 或分批文件传递。

成功上传副本放在本机独立用户目录 com.octop.pet/bridge-transfers，不放进组件版本目录，不在命令结束时删掉，以便后台任务及后续命令继续使用。用户可以在不再需要时清理该目录。文件取回只发生在 --pd-download 明确指定时；普通聊天不调用 CLI，也不传文件。

继续使用 pd-chat-cli@2；含标准输入/文件的请求方法为 helper.cli.io，旧客户端会拒绝该方法，不会静默忽略文件。服务器 ws.py 绑定格式和已有补丁保持不变，必须同时更新服务器模块和 Windows 组件。服务端同一 Agent 的多设备歧义仍拒绝，结果须匹配请求 ID 和线程；不恢复授权弹窗。

cli describe/capabilities 会附加 chat_bridge 使用说明，便于原 Skill 和 AI 发现桥接能力。没有新增 Agent 专属补丁、MCP、SSH 或公网端口。
