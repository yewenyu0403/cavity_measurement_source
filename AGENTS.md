# 腔体内边框图像测量项目

用 Python（NumPy + OpenCV，不含深度学习）从实拍图中测量圆角方腔 **A 内边框**（外围黑边靠腔内的一沿）的长宽。Windows 平台，路径含中文、空格和方括号。

本文件由 Codex 和 Claude Code 共用（Claude Code 通过 `CLAUDE.md` 导入它）。项目规则只在这里修改。

## 目录

- 仓库根（本目录）放数据与输出：`图片/` 是原始 BMP；`图片检测结果/` 是默认输出根（由 `cavity_measurement/config/output_config.json` 指定）；`整理前备份/` 是历史备份。
- `cavity_measurement/` 是程序根，命令都在此目录下运行。`src/cavity_measurement/` 是算法（`contour.py` 轮廓、`metrology.py` 尺寸、`measurement.py` 命令行），另有 `tools/`、`tests/`、`baseline/`（冻结回归参考）、`config/`，以及中文文档 `docs/`（USAGE、MEASUREMENT、VALIDATION、STRUCTURE）。
- `cavity_measurement/_deps/` 是随仓库携带的 OpenCV，由 `src/cavity_measurement/__init__.py` 在导入时加入 `sys.path`。不要修改、格式化或升级它。

## 运行与测试

在 `cavity_measurement/` 下运行。Python 优先用 Codex 运行时（启动脚本同样如此），其路径由 Codex 应用管理，找不到时退回 PATH 里的 `python`。两者均已实测可跑通测试（3.12 与 3.13）。

```powershell
$py = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = 'python' }
$env:PYTHONDONTWRITEBYTECODE = '1'
& $py -X utf8 -m unittest discover -s tests    # 当前 26 项，应全部通过
& $py -X utf8 cavity_measure.py --help
& $py -X utf8 tools/verify_baseline.py         # 四图回归；会在输出根下新建 四图基准验证/时间戳
```

- 必须设置环境变量 `PYTHONDONTWRITEBYTECODE=1`，只加 `-B` 不够（测试会启动子进程）。仓库已提交 `__pycache__`（`.gitignore` 目前只忽略 `图片检测结果/`），写字节码会弄脏工作区。
- `docs/VALIDATION.md` 里写的测试数量是当时的历史记录，以实际运行结果为准。
- 旧的 `--detection strict` 直线流程和 `demo` 合成示例已于 2026-10-23 删除，不要恢复或按旧文档调用。
- 换机器需要 Python 3.10 或以上，并执行 `python -m pip install -r requirements.txt`。

## 不可违反的约束

这是计量类项目，结论是否诚实比"跑通"更重要。

- **不宣称精度。** `config/calibration.json` 当前按用户2026-10-29要求启用20张10 mm棋盘格、773个交点的初步联合比例0.009685371864397972 mm/像素，适用于7008×7000原图和用户确认的相同成像设置、测量平面高度。未完成独立标准长度验证，未启用镜头畸变校正。旧单帧2 mm及三帧10 mm参数保留归档。输出、文档、提交说明都不得写成已达到某个mm精度、不确定度或零件合格。三位小数只是显示格式，JSON保留原始数值。
- **不用被测件自身的尺寸反推或"验证"比例。** 不用设计值 60×40 mm 或三坐标值计算 `mm_per_pixel`，也不用它们调参去贴近结果。
- **不为让图片通过而放宽门限。** `docs/MEASUREMENT.md` 里的质量门限是拒测标准。第 5、6 张图保持 `review_required` 是预期结果。改门限必须由用户明确要求，并在 `docs/VALIDATION.md` 记录。
- **失败必须清空尺寸。** 复核或失败状态会覆盖 `result.json`、`尺寸结果.txt`、`dimensions.csv` 并把 `dimensions` 置空，防止误读上一次的数值，不要改成保留旧值。图像分辨率与默认标定（7008×7000）不符时拒测。退出码：`measured` / `pixel_only` 为 0，`review_required` / `failed` 为 2。
- **测量对象不变。** A 内边框是黑边靠腔内的一沿，沿指向腔内的法向由暗到亮（默认 `--boundary-side inner`）。长宽是四条直边独立拟合后的中央截面对边间距，只用各边中间 56%，排除圆角；圆角半径、腔深、壁厚不在测量范围。
- **回归基准不是真值。** `baseline/` 是目视复查后的算法输出，四张开发图也不是独立测试集。源图哈希不符时 `verify_baseline.py` 必须报错，不得自动覆盖 `baseline/`；更新基准需要用户确认。
- **原始数据只读。** 不修改、重命名或覆盖 `图片/` 下的原图（SHA-256 记录在 `baseline/manifest.json`），不改动 `整理前备份/`。`图片检测结果/` 是用户挑选保留的结果，不纳入 git，未经同意不要清理或删除；每次运行都写入新的时间戳子目录，不覆盖旧结果。

## 编码与脚本约定

- `scripts/measure_image.ps1` 以 **UTF-8 带 BOM** 保存（Windows PowerShell 5 读取中文路径需要），编辑后保持 BOM。`scripts/verify_baseline.ps1` 没有 BOM，不要顺手改动。
- 根目录的 `.cmd` 只是转调 `scripts/*.ps1` 的薄封装，保持简单。
- 路径一律加引号，PowerShell 中用 `-LiteralPath`（路径含 `[` `]`）。Python 一律加 `-X utf8`。
- 文档和面向用户的提示用中文；代码标识符、注释和命令行帮助沿用现有的英文风格。

## 多工具协作

两个工具可能先后修改本仓库：

- 动手前先 `git status`。工作区里不是你改的内容（包括未跟踪的结果目录）不要还原或删除。
- 有意义的改动和验证结果，用带日期的中文条目追加到 `cavity_measurement/docs/VALIDATION.md`，这是两边共用的工作日志。行为变化同步更新 `docs/USAGE.md` 和 `docs/MEASUREMENT.md`。
- 提交信息沿用仓库风格：简短中文，说明做了什么（如"添加标定比例"）。


## 测试与诊断工作目录（2026-10-31）

按用户要求，后续临时测试脚本、单图诊断、分析报告、预览图和测试输出统一写入 F:\文件\研究生文件\38所\测试，并按任务和日期建立独立子目录。执行这些工作时显式使用该目录或其任务子目录作为工作目录，不再向已清理的桌面目录写入测试文件。原图只读，项目源码和正式测试源码仍在现有项目中。调用测量或回归脚本进行测试时，使用 --out 显式指定该测试目录下的新任务子目录；正常业务输出配置不因本项约定改变。
