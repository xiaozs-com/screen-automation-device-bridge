# 已安装服务器升级到完整 CLI 桥接

本包用于已有 PD_CHAT_BRIDGE_PATCH 的 Octop。只更新两个独立 Python 模块，不修改 Octop ws.py、服务配置或端口，不重打聊天补丁。

1. 在网页管理面板上传并解压本 ZIP 到 /home/admin/pd-chat-bridge-full-cli-0.2.3/；保留原 /home/admin/pd-chat-bridge/ 和 install-records。
2. 使用服务相同用户 admin 及原 Python 环境预览：

```bash
/home/admin/.octop/venv/bin/python /home/admin/pd-chat-bridge-full-cli-0.2.3/update_bridge.py
```

3. 按原方式停止服务，再更新并重启：

```bash
octop service stop
/home/admin/.octop/venv/bin/python /home/admin/pd-chat-bridge-full-cli-0.2.3/update_bridge.py --apply
octop service start
```

如原服务不是 octop service 管理，则沿用原管理方式。本包不访问 SSH，不自行重启或上传。

4. 本机安装 Paldee Pet 0.2.3，重新打开宠物聊天。每次聊天绑定会自动更新该 Agent 的 CLI 代理入口，既有和新增 Skill 都沿用原 resolver。
5. 让 AI 重新调用 cli describe，随后测试 workflow schema sdk；再以无敏感内容流程包测试 inspect/install/show/validate 和 --pd-download。不要以微信等业务流程作为传输验收。

预览或更新提示未发现聊天补丁时停止：先核对 Octop 升级是否覆盖旧 ws.py；不要盲目再次运行旧 install_server.py --apply。使用当前已安装版本检查补丁兼容性。

更新时旧模块备份到本目录 install-records/modules-时间/，rollback.txt 记录恢复路径。回退前停服务，恢复两个旧模块后再启动；新 Pet 的完整命令/IO 在旧服务器上不会全部可用，普通聊天协议仍不变。

Windows 下载站另行上传 ZIP、已签名 latest、全局目录；本服务器更新包不是功能组件 ZIP，不合并任何产品 catalog.json。用户手动部署后才完成远端联调，不能把本地通过等同服务器已更新。
