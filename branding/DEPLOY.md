# 不编译的静态外观更新

只更新 Logo、机器人素材和现有首屏 HTML，不覆盖整套 dashboard，也不更改默认配色。要使用青绿，在 Octop 原外观选择器手动选择。

1. 用服务相同的 Python 定位当前网页目录（只读）：

   ```bash
   /home/admin/.octop/venv/bin/python -c 'import importlib.util; from pathlib import Path; print(Path(next(iter(importlib.util.find_spec("octop").submodule_search_locations))) / "dashboard")'
   ```

2. 将静态外观包上传解压到独立目录。使用第 1 步返回的真实目录运行预览，例如：

   ```bash
   /home/admin/.octop/venv/bin/python /home/admin/paldee-branding/branding/apply_branding.py --dashboard /实际安装路径/octop/dashboard
   ```

3. 检查输出的文件清单，确认仅有 index.html 和图片/动画后，再加 --apply：

   ```bash
   /home/admin/.octop/venv/bin/python /home/admin/paldee-branding/branding/apply_branding.py --dashboard /实际安装路径/octop/dashboard --apply
   ```

4. 刷新浏览器、反向代理或 CDN 的相关静态缓存。已有 PWA 缓存也可能继续显示旧素材；可先用无痕窗口核对服务器的新文件。检查浅色/深色 Logo、空状态、聊天欢迎和进入动画。原来保存的配色保留。

脚本在网页目录 .paldee-branding-backups/时间 下保存原文件和记录。若需回退，用实际备份路径：

```bash
python3 branding/apply_branding.py --dashboard /实际安装路径/octop/dashboard --rollback /实际安装路径/octop/dashboard/.paldee-branding-backups/时间
```

文件在应用后被其他更新改过时，脚本会停止回退，避免覆盖新修改。Octop 后续升级可能覆盖这些静态文件，升级后重新预览再应用即可；不要将旧 index.html 整文件复制到新版本。

本次不重写 service worker 或其预缓存清单；缓存刷新以服务器和浏览器实际配置为准。
