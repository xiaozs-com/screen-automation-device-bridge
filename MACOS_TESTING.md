# Mac 真机测试

本机执行器与 Windows 共用 Rust 源码和 pd-chat-cli@2 协议。支持 Intel x64 和 Apple Silicon arm64。当前提供源码和本地开发包构建方式，未做 Mac 签名、公证或真机验收。

## 构建

安装 Rust、Python 3 和 Xcode 命令行工具后，在仓库根目录执行：

```bash
bash packaging/build_macos.sh
```

默认构建当前 Mac 架构，输出 build/pd-device-bridge-macos-x64-dev.zip 或 macos-arm64-dev.zip。指定另一架构前，用 rustup target add x86_64-apple-darwin 或 aarch64-apple-darwin 安装目标；另一架构必须另行测试。

## 直接测试执行器

安装 Mac 版屏幕自动化小助手。自动查找 ~/Applications 和 /Applications 下的 Screen Automation Helper.app，调用 Contents/MacOS/screen-automation-helper。自定义安装位置时：

```bash
export SCREEN_AUTOMATION_HELPER_EXE="/Applications/Screen Automation Helper.app/Contents/MacOS/screen-automation-helper"
# Intel 使用 x86_64-apple-darwin；Apple Silicon 使用 aarch64-apple-darwin
export PD_TEST_BRIDGE_EXE="$PWD/native/target/x86_64-apple-darwin/release/pd-device-bridge"
"$PD_TEST_BRIDGE_EXE" cli describe
"$PD_TEST_BRIDGE_EXE" cli workflow schema sdk
printf '%s' '{"args":["cli","describe"],"input":{"stdin":""}}' | "$PD_TEST_BRIDGE_EXE" --request-json
```

输出包含 exit_code、stdout、stderr；必须检查 exit_code 和 stdout 中的小助手结果，外层 ok 表示桥接调用完成。

可选的真实 CLI 集成测试会在临时用户数据目录写入测试记忆、安装无操作流程，不运行流程：

```bash
python3 -m unittest discover -s server -p test_full_cli_native.py -v
```

## 宠物聊天联调

本仓库只提供执行器。需要 Mac 版 Paldee Pet 的组件加载器支持对应平台、无 .exe 的入口，并把 helper.cli / helper.cli.io 请求交给此执行器；本次未修改宠物项目。原 Windows 组件不能直接装到 Mac。服务端沿用 SERVER_UPGRADE.md 的模块和协议。

先完成上述直接测试，再接入宠物测试聊天中的 cli describe、截图以及无敏感内容的文件往返。截图和输入操作需在系统设置中授予小助手实际运行进程所需的屏幕录制和辅助功能权限。

上传成功的文件保留在 ~/Library/Application Support/com.octop.pet/bridge-transfers；OCTOPPET_DATA_DIR 可以覆盖用户数据根目录。文件取回使用 Mac 绝对路径，例如 --pd-download '/Users/你的用户名/Documents/test.txt'，不使用 Windows 路径。服务器上已存在的流程路径仍会自动上传；显式 --pd-upload 可消除同名路径歧义。
