# 微信开发者工具 CLI 自动化(2026-10-06 实测)

上传小程序一直是用仓库里的 `npm run upload`(miniprogram-ci + 私钥),
那条路不依赖开发者工具。但在需要**在 IDE 里操作**(比如看版本、点上传)时,
会用到官方 CLI。这份文档记录 2026-10-06 摸清的几个坑。

## 工具信息

| 项 | 值 |
|---|---|
| 安装目录 | `C:\Program Files (x86)\Tencent\微信web开发者工具` |
| CLI 入口 | `<安装目录>\cli.bat` |
| 版本 | Stable v2.02.2608070 |
| 用户数据 | `%LOCALAPPDATA%\微信开发者工具\User Data\<dataDirHash>\` |

## 坑 1:`ELECTRON_RUN_AS_NODE=1` 会让 IDE 起不来

`cli.bat` 内部会 `set ELECTRON_RUN_AS_NODE=1`。这个变量如果残留在**当前会话环境**里,
之后直接启动 `微信开发者工具.exe` 时,Electron 会以 Node 模式运行 ——
**进程瞬间退出,不建窗口,日志里什么都不留**。

现象:启动后 `Get-Process` 找不到进程,`%APPDATA%\微信开发者工具` 下最新日志还是几天前的。

正确启动方式(显式剔除该变量):

```powershell
$dt = "C:\Program Files (x86)\Tencent\微信web开发者工具"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "$dt\微信开发者工具.exe"
$psi.UseShellExecute = $false
$psi.EnvironmentVariables.Remove("ELECTRON_RUN_AS_NODE") | Out-Null
[System.Diagnostics.Process]::Start($psi) | Out-Null
```

## 坑 2:服务端口默认关闭,CLI 会直接拒绝

未开启时报:

```
[error] IDE service port disabled. To use CLI Call, please enter y to confirm
        enabling CLI capability, or manually open IDE -> Settings -> Security
        Settings, and set Service Port On.
```

**GUI 开启路径**:工具 → 设置 → 安全设置 → 打开"服务端口"。
可用配置键(实测位于 `WeappLocalData/localstorage_<hash>.json` 的 `security` 节点):

```json
{"enableServicePort": true, "port": 39448, "allowGetTicket": false, "trustWhenAuto": false}
```

- 必须在 **IDE 完全退出**时改文件,否则退出时会被内存状态覆盖回 `false`;
- `port` 留 `null` 时,IDE 启动会自己分配一个端口(实测分配了 39448);
- 改完重启 IDE 生效,`Get-NetTCPConnection` 能看到该端口由 IDE 进程监听。

## 坑 3:CLI 调用会挤掉 IDE 的登录态

实测:先扫码登录 → 正常;随后启动第二个 IDE 实例 + 跑 `cli login`,
IDE 侧日志出现 `errcode: 41001 ... 需要重新登录`,界面回到二维码。

**结论**:不要让 CLI 去做登录动作;`cli login` 只在确实需要重新登录时用,
且用完别反复调用。多开 IDE 实例也会互相挤会话。

## 坑 4:端口是 WebSocket,不是 HTTP

`curl http://127.0.0.1:39448` 会超时 —— 那是 WebSocket 服务,
CLI 通过 `ws://127.0.0.1:<port>` 通信。**别用 HTTP 探测判断它是否可用**。

## 可用的 CLI 子命令(本版本)

```
cloud  open  login  islogin  preview  auto-preview  upload  build-npm
auto  auto-replay  agent  reset-fileutils  close  quit  cache  engine
open-other  build-ipa  build-apk
```

**没有"设为体验版"命令** —— 该操作只能在微信公众平台后台
(管理 → 版本管理 → 开发版本 → 选为体验版)或 IDE 的版本管理面板完成。

## 结论:两条上传路径怎么选

| 场景 | 用哪个 |
|---|---|
| 只要把代码传成"开发版本" | **`npm run upload`**(miniprogram-ci + 私钥),无需登录 IDE,已多次验证 |
| 需要在 IDE 里看/点版本相关操作 | 开 IDE + 开服务端口 + 扫码登录 + `cli` |
| 设"体验版" | 只能人工:公众平台后台点一下 |

日常发布走 `npm run upload` 即可,不必折腾 IDE。
