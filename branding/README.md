# Octop 简单静态外观修改

当前方案不重新编译。仅替换 9 个静态素材，并在服务器现有 index.html 中调整首屏机器人动画；保留原有 JS/CSS 文件及其引用。

- 横版 Logo：PD 标志与 Paldee 字标。深色背景对应 *_white 文件，使用用户提供的 screen-automation-helper_d.png 白色标志；浅色背景素材保留。
- 空状态、聊天欢迎动画和进入动画：复用客户端太极机器人。
- 保留已有主题、明暗模式和系统减少动态效果设置。
- 默认青绿的编译方案已撤回。需要青绿时，用 Octop 自带外观选择器手动选择；不通过注入脚本改写浏览器配置。

目标源码审阅版本为 Octop v1.0.3b1；实际应用前先预览，不认识的首屏结构会停止。安装方法见 [DEPLOY.md](DEPLOY.md)。

```bash
python3 branding/apply_branding.py --dashboard /实际安装路径/octop/dashboard
python3 branding/apply_branding.py --dashboard /实际安装路径/octop/dashboard --apply
```

预览不写文件，应用前备份受影响静态文件。应用脚本不修改 Python 模块、TypeScript、打包后的 JS/CSS、服务端口或桥接接线，不安装依赖、不上传、不重启服务。

素材来源与指纹见 assets-manifest.json；deployFiles 是本次实际部署清单，其他素材仅供开发留存。

在本仓库运行 `python packaging/package_branding.py` 生成小型静态外观包，无需 npm 或构建步骤。此前生成的完整网页包已移入 build/obsolete-branding，不能用于当前方案。
