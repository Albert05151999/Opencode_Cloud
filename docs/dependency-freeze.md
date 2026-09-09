# 依赖冻结与升级

发布目标为 Linux x86_64，Python 3.12.3。控制器的 28 个生产依赖记录于 `requirements-controller.lock`；分析运行时的 32 个依赖记录于 `runtime/requirements.lock`。两份锁均固定完整传递版本和下载哈希，安装时要求二进制 wheel 与 `--require-hashes`。它们与本次已测控制器环境和运行时镜像的包版本逐项一致。

更新入口为 `bash scripts/python-dependency-locks.sh update`，默认保留已有版本；有意更新传递依赖时使用 `update --upgrade`。顶层精确版本仍需先修改 `pyproject.toml` 或 `runtime/requirements.txt`。脚本使用 Python 3.12 和 pip-tools 7.5.2，在临时环境运行并隔离机器级 pip 配置。`verify` 子命令分别创建干净虚拟环境，执行哈希安装和 `pip check`，失败退出并清理临时目录。项目源码直接复制进入生产控制器镜像，无需运行浮动的 setuptools 构建隔离环境。

Node 24.20.0 的官方 Linux x64 压缩包 SHA-256 固定于 `versions.env`。OpenCode 1.18.29 的 npm 依赖图与 sha512 完整性值固定于 `runtime/package-lock.json`，验证入口是 `python3 scripts/verify-npm-lock.py`。安装时禁用通用生命周期脚本，再显式执行固定 OpenCode 包的 postinstall 以准备启动器；此步骤只在构建期发生。

Ubuntu 24.04 和 Python 3.12.3 slim 基础镜像使用摘要固定，LiteLLM、Prometheus 和 Grafana 同样固定版本和摘要。Ubuntu apt 使用 `20260907T000000Z` 快照，固定软件仓库时间点，并检查 Python 精确版本。快照机制依据 [Ubuntu 官方说明](https://snapshot.ubuntu.com/)，基础摘要固定依据 [Docker 构建建议](https://docs.docker.com/build/building/best-practices/)。下载和签名验证失败时停止构建，不回退到浮动源。

验收宿主机为 Docker Engine 29.8.0、containerd 2.3.4、runc 1.5.1、cgroup v1/cgroupfs、WSL2 内核 5.15.167.4，详见 `artifacts/release/host-compatibility.json`。这些是实际验证组合，不能推导任意 Linux、架构或未来 Docker 版本均兼容。迁移至 cgroup v2 应重跑资源限制、回收与负载关卡。

依赖冻结不表示永不升级，也不直接证明不同日期构建出的镜像字节完全一致。发布镜像内容最终由镜像摘要和离线包校验和标识；升级任何固定输入都需重新构建并验收。
