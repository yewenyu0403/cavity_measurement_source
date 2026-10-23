# 文件整理说明

本次只整理代码和资源的位置，修正导入及路径引用，保留三个根目录 `.cmd` 启动方式与 `python cavity_measure.py ...` 命令。

## 原位置与新位置

| 原根目录文件或文件夹 | 整理后位置 |
| --- | --- |
| `cavity_measure.py` 的实现 | `src/cavity_measurement/measurement.py`；根目录保留兼容入口 |
| `opening_contour.py` | `src/cavity_measurement/contour.py` |
| `synthetic_demo.py` | `src/cavity_measurement/synthetic.py` |
| `verify_baseline.py` | `tools/verify_baseline.py` |
| 三个 `.ps1` | `scripts/` |
| `output_config.json` | `config/output_config.json` |
| `settings.example.json` | `config/settings.example.json` |
| `requirements-tested.txt` | `config/requirements-tested.txt` |
| 原详细 `README.md` | `docs/USAGE.md`；根目录改为简明导航 |
| `VALIDATION.md` | `docs/VALIDATION.md` |
| `demo_output/` | `examples/demo_output/` |

`requirements.txt`、三个 `.cmd`、`baseline/`、`tests/` 和 `_deps/` 继续保留在程序根目录。测试中的合成模块导入随文件迁移调整。

## 路径规则

启动脚本根据自身位置查找程序根目录。输出配置、私有依赖和基准数据也根据程序根目录查找，不依赖启动时所在的终端目录。`tools/verify_baseline.py` 默认从程序父目录的 `图片/` 读取原始 BMP。

默认输出根目录仍为 `F:\文件\研究生文件\38所\cavity_measurement_source\图片检测结果`。原始图片与历史检测输出不迁移。`examples/demo_output/` 是历史合成示例；以后运行示例仍写入统一输出根目录下的 `合成示例/时间戳`。

在程序根目录导入 `cavity_measure` 的原公开函数仍可使用。直接引用旧内部模块 `opening_contour` 或 `synthetic_demo` 的外部脚本，需要相应改用 `cavity_measurement.contour` 或 `cavity_measurement.synthetic`，并让 Python 能查找到本程序的 `src/` 目录。

## 备份

整理前的程序文件保存在与程序相邻的 `整理前备份/cavity_measurement_时间戳/` 中，包括原始文件清单及哈希。`_deps/` 体积较大且本次未改动，未重复备份。整理时移出的旧文件另外保留在备份中的 `moved_from_root/`，以便核对和恢复。

本次整理不新增尺寸计量能力，不修改轮廓提取参数或四图冻结参考。

## 2026-10-11：新增尺寸测量文件

`src/cavity_measurement/metrology.py` 负责从已确认轮廓计算尺寸；`config/contour_measurement.example.json` 是该流程的质量门限。`tools/measure_folder.py`、`scripts/measure_folder.ps1` 与根目录 `measure_folder.cmd` 提供批量测量，输出到统一结果目录下的 `尺寸测量/时间戳`。`tests/test_contour_measurement.py` 验证新尺寸流程。

## 2026-10-11：单图和批量启动入口合并

根目录 `measure_image.cmd` 统一接受图片或文件夹，`scripts/measure_image.ps1` 根据路径类型选择原单图 CLI 或原批量工具，并共享比例输入。路径处直接回车时使用父目录 `图片`。旧 `measure_folder.cmd` 保留，`scripts/measure_folder.ps1` 改为调用统一脚本的兼容包装，保留原双击即批量测量的方式。算法、基准及输出根目录不修改。

## 2026-10-23：删除旧流程文件

旧 `--detection strict` 流程与合成示例已删除：`src/cavity_measurement/synthetic.py`、`config/settings.example.json`、`examples/demo_output/`、根目录 `run_demo.cmd`、`scripts/run_demo.ps1` 和 `tests/test_measurement.py`。平面标定测试移至 `tests/test_calibration.py`。上文表格中的对应行仅作历史记录，原文件可从 git 历史恢复。

同日删除批量兼容入口 `measure_folder.cmd` 与 `scripts/measure_folder.ps1`，统一使用 `measure_image.cmd`。实际执行批量测量的 `tools/measure_folder.py` 保留。
