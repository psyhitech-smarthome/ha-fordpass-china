# FordPass China Modern · 中国福特派 Home Assistant 集成

独立的 Home Assistant 自定义集成，面向已绑定车辆的中国福特派车主。
已在国产 2024 款烈马与 Home Assistant Core 2026.10.1 上验证。
当前版本 **0.3.0**；由[心史科技 · 智能家居](https://github.com/psyhitech-smarthome)维护，并非福特官方项目。

## 已实现能力

| 能力 | 行为 |
|---|---|
| 官方账号登录 | 在福特网站登录，将最终跳转 URL 直接提交到 HA |
| 凭证续期 | 自动刷新访问凭证，失效后通过原配置条目重新认证 |
| 基础车况 | 油量、续航、里程、机油、电池、四轮胎压、点火及远程启动只读状态 |
| 门窗状态 | 七项门状态、四项车窗状态 |
| 手动车锁 | 提交一次命令、轮询执行结果，再检查实际锁态；不自动重发 |
| 车辆位置 | 独立 LBS 查询，显示地区、位置上报时间、查询时间与查询状态 |
| 距家距离 | 根据 HA 家庭位置计算整公里直线估算 |

车况与定位在同一轮任务中约每 **15 分钟**查询。查询福特云端成功，
不代表车辆刚刚采集了新数据；请同时查看车辆上报时间。定位查询失败
不会使基础车况失效，地区和距离会变为不可用，最后成功时间仍可检查。

**尚未实现**：远程启动／停止、空调预设写入、鸣笛寻车。
坐标系尚未独立核实，因此距离为估算，不发布用于自动到家检测的
GPS tracker。没有包含车控自动化。锁车协议经车主在官方 App 实测，
HA 控制流程通过模拟测试；不要将这一点描述成所有车型均已实车验收。

## 安装边界

这是一套可研究、可维护的集成源码，**目前不是仅安装 HACS 后登录即可
使用的完整分发包**。它还需要私有协议配置，以及从车主自行取得的官方
APK 中提取的 ARM64 原生 codec。仓库不分发 APK、原生库、白盒密钥、
账号令牌或生产协议密钥。

当前测试部署方式是：macOS 上的 HA Core + Docker 中的 ARM64 Linux
codec；APK 本身不在容器里运行。其他硬件、HA OS／Container 安装方式
需要另行验证网络和 codec 可达性。

1. 将 `custom_components/fordpass_cn_modern/` 复制到 HA 配置目录下的
   `custom_components/`。
2. 按 [安装说明](docs/INSTALL.md)准备私有 codec 与协议配置。
3. 重启 HA，在“设置 → 设备与服务”中添加 **FordPass China Modern**。
4. 阅读并确认福特协议后，在福特网站完成登录，把最终跳转 URL 直接
   粘贴到 HA 表单。不要在 issue、聊天或日志中发布此 URL。
5. 在 HA 中配置家庭位置；启用 LBS 后可显示距家估算及独立查询时间。

开发维护流程见 [Mac mini 维护说明](docs/DEVELOPMENT.md)。

## 开发与验证

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

不安装 Home Assistant 时会跳过 HA 协调器测试。完整测试需在装有
Home Assistant 的隔离 Python 环境内运行。测试使用伪造凭证与坐标，
不会向车辆发送命令。协议客户端同时存在于独立 Python 包和 HA 组件
的 `protocol/`；修改后运行 `python scripts/check_protocol_sync.py`。

认证、签名与数据时间语义见 [协议说明](docs/PROTOCOL.md)。
问题反馈请只提交脱敏错误类别、HA 版本、App 版本和车型年款。

## 许可

本仓库自行编写的代码采用 [MIT License](LICENSE)。福特商标、官方
App 及车主自行提供的原生库和密钥不在本仓库的授权范围内。
