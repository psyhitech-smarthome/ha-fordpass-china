# 安装与运行

## 1. 准备 codec

运行环境：Docker，已验证 ARM64 Linux；宿主 HA Core 可连接本机
`127.0.0.1:8766`。构建需联网下载基础镜像；codec 运行时不联网。

自行从福特官方渠道取得受支持 APK 后：

```sh
python codec_sidecar/prepare_vendor.py /private/path/FordPass.apk /private/path/ford-vendor
cp .env.example .env
chmod 600 .env
# 编辑 .env 的私有目录与随机 bearer，勿提交此文件。
docker compose up -d --build
```

提取脚本会检查原生库哈希，仅接受已验证版本；不要跳过校验。它只提取
原生库与 codec 密钥，不生成 HA 私有配置里的请求签名密钥。

两个容器通过私有 Unix socket 通信：codec 加载只读 vendor 文件；relay
仅在宿主 loopback 发布端口。HA 运行在另一个容器时，loopback 的含义
不同，本示例不能直接照搬。不要将 codec 发布到公网。

## 2. 私有 HA 配置

将 `examples/private-settings.example.json` 的副本放在 HA 配置目录，
命名为 `.fordpass_cn_modern_private.json`，文件权限必须是 `0600`。
示例中的占位值不能实际访问福特。协议参数需从本人合法取得的客户端
及本人账号授权流量中独立配置，仓库不提供生产值。

- `sign_secret_key`、`sign_payload_key`：基础 API 的 R3 签名参数。
- `app_key`：车辆列表查询所需参数。
- `codec_bearer`：与 `.env` 中自行设置的 bearer 一致。
- `codec_url`：HA 可访问的本地 codec 地址。
- `lbs_secret_key`、`lbs_payload_key`、`lbs_application_id`：定位参数。
  不配置这三项仍可使用基础车况和车门锁。

账号 access/refresh token 由登录流程写入 HA 自己的私有 config-entry
存储；不要手工复制进源码或上述示例文件。

## 3. 登录与使用

重启 HA 并添加集成。用户名和密码只输入福特网站，不交给本集成。
在 HA 表单提交带授权码的最终跳转 URL；授权码通常短时、一次有效。
认证失败需按 HA 的重新认证流程处理，避免反复提交同一个授权码。

自动续期已验证，但长时间停机、账号风控、服务故障或协议变动都可能
需要重新登录。集成不承诺凭证永久有效。

## 4. 仪表盘

将车况和定位传感器添加至 HA 自己的仪表盘。实体 ID 会随设备昵称
变化，使用你实例中实际的实体 ID。远程车锁使用标准 `lock` 实体。
自建按钮应配置操作确认；若命令结果未知，先核对实车或官方 App，
不要连续重试。API 超时后车辆仍可能执行先前收到的命令。

## 5. 更新与回退

Git 仓库存源码，HA 配置目录放已部署副本，私有参数放在仓库之外。
更新前备份组件与 HA 配置，测试后复制组件并重新加载／重启 HA。
codec 私有 vendor 目录应独立备份，不随 Git 拉取覆盖。
