# 室在人为 Windows 本地应用下载

软件 API v0.6.1，应用及资料分发 r3（2026-10-14）。[下载应用 ZIP](https://github.com/zjuhechao/shi-zai-ren-wei/raw/refs/heads/main/downloads/app-windows-v0.6.1.zip)，右键“全部解压”，查看“开始使用.html”，双击 `start-app.bat`。

应用需要 Windows x64 Python 3.12，首次联网安装依赖。它是源码型本地网页应用，不是免安装 EXE，也没有托管公网后端。无 Key 可测算和下载固定假设 PDF；新智能方案需个人 DeepSeek、百炼账号和真实入库，不内置团队 Key。完整配置见包内 `docs/下载后运行与配置.md`。

开发、测试或 Docker 配置请使用完整仓库；应用 ZIP 不包含开发测试、Docker、Git 历史、Python 运行时、安装依赖或私有资料。应用包内指纹文件记录实际运行文件，不对自身取指纹。

## 重新构建

开发者需安装 Git。在已核对的源码根目录，先暂存准备发布的文件，更新 Git 跟踪文件的 `release_files.sha256.json`，再执行构建。以下命令使用 Python 标准库，不调用云端 API：

```powershell
.\.venv\Scripts\python.exe tools\update_source_manifest.py --source . --date 2026-10-14 --revision r3
.\.venv\Scripts\python.exe tools\build_application.py --source . --templates tools\templates --output ..\应用包重建\app-windows-v0.6.1.zip --record ..\应用包重建\packaging-check.json
```

输出须为尚不存在的新路径。构建器只选择运行白名单，不读取 `.env`、`.venv` 或 `storage`，也不会递归打包 `downloads`。相同输入两次构建应完全同字节；输出通过包内 SHA256 和路径检查后才能作为新的分发文件。若新增或修改运行文件，须同步白名单、测试和资料，而不是只替换 ZIP 名称。

替换仓库中的应用 ZIP 后，再暂存该文件并更新一次源码清单；应用构建忽略 `downloads`，因此不会出现 ZIP 与清单互相依赖。清单工具只是逐文件指纹更新，不代替隐私、密钥与运行安全审计。
