# Gboard-NTR (iOS Gboard 键盘增强补丁)

**中文** | [English](README.en.md)

在 iOS **Gboard 2.3.19** 官方输入法上做无源码逆向增强：注入一个 Objective-C 动态库（`libgkx.dylib`），配合无损二进制改写实现。

> **设计哲学**：保持绝对原生。完整保留 Google 原生 Mozc 拼音引擎、键盘排布与滑行输入手感，不加高键盘、不遮挡界面、不拦截触摸。

---

## 🌟 功能

**1. Rime 万象词库**
精选 6 万条高频词，精简字段后单文件 1.61 MB。首次启动自动写入 App Group，即装即用，不额外占安装体积。

**2. 九键动作键三态切换**
只替换九键及其符号页的原生表情键，26 键与回车键不动。组字中显示「重输」（清空拼音），有候选未组字显示「收起」（收起键盘），空闲显示「换行」。保留原生背景与配色，不额外加高或遮挡；切页不再闪原生笑脸。

**3. G 图标分页裁剪**
去掉 YouTube、联系人、GIF、贴纸四个分页，只留 emoji、颜文字与自带分页。新版 Gboard 里某类不存在时自动跳过。

**4. 常用语**
G 图标分页新增「常用语」，跟随键盘皮肤配色。钉子关闭时点一条即上屏并关闭，打开后可连续输入。键盘内可直接编辑，主 App「设置 → Gboard → 常用语」是第二个入口。

**5. 标点长按弹层**
九键「，。？！」长按 0.32 秒弹出一排符号，滑到目标松开即上屏。符号表与显示个数（1–10）可在主 App 里改，配色跟随键盘皮肤。

**6. 诊断日志（默认关）**
默认不记录。开关在「设置 → Gboard → 诊断日志」，跨进程半秒内生效。

**7. 地图分页**
完全还原原生，不做任何跳转。

**8. 齿轮键「中/英」**
九键左列第 4 键与 26 键右上角的切语言键，原生只有地球图标，改为「中英」两字，当前语言满不透明、另一字降透明度。纯视觉覆盖，触摸与切换语言仍走原生路径；切中英、切页不再闪地球图标。

---

## 📐 开发红线

1. **不改根视图约束与键盘高度**——会导致候选词被挤出屏幕或出现空隙。
2. **不拦截按键触摸事件**——滑行输入对触摸连贯性极敏感，只能在目标软键上挂独立子视图。
3. **词库硬指标**——不超过 7 万条、2.5 MB，转换时省略冗余字段，避免 Jetsam 杀进程。
4. **Windows 打包必须保留 Unix 权限**——可执行文件 0o755，数据文件 0o644，否则自签报错或启动被杀。
5. **无损注入**——只在 Load Commands 后的全零填充区写 `LC_LOAD_DYLIB`，App Group 等长改写。

---

## 📂 仓库结构

```
gboard-ntr/
├── dylib/                     # 注入源码（gkx.m 与若干头文件）
├── tools/
│   ├── inject.py              # Mach-O 注入 + App Group 改写 + 权限打包
│   ├── dict_converter.py      # 万象词库 → 紧凑 Protobuf
│   ├── inspect_signed.py      # 只读自检：Mach-O、依赖链、权限
│   ├── swap_dylib.py          # 在成品 IPA 里替换 libgkx.dylib（CI 用）
│   ├── verify_release_package.py # 只读校验：新包只换了 dylib，且与 CI 产物逐字节一致
│   └── publish_release.py     # 发 GitHub Release
├── tests/                     # 源码契约测试
├── .github/workflows/         # CI：编译 dylib → 换包 → 发布
├── dist/                      # 构建产物
├── README.md
└── agent.md                   # 逆向细节与踩坑记录
```

---

## 🛠️ 构建与发布

**CI 全自动（常规路径）**：push 改动 `dylib/` 即可。CI 编译出新的 `libgkx.dylib`，下载 Release 上那份成品 IPA，替换其中的 dylib 后覆盖上传并刷新正文哈希。

**本地手工出包**（改了词库或注入逻辑时）：

```powershell
# 1. 转换词库（可选）
python tools/dict_converter.py --dir "%APPDATA%\Rime\dicts" -o "dist/user_dictionary.db" --max 60000

# 2. 注入打包
python tools/inject.py --ipa "../ipa/Gboard_2.3.19.ipa" --dylib "dist/libgkx.dylib" `
  --dict "dist/user_dictionary.db" --app-group "group.zunbengege.top" `
  --out "dist/gboard-ntr-1.0-unsigned.ipa"

# 3. 发布
python tools/publish_release.py --asset dist/gboard-ntr-1.0-unsigned.ipa --refresh-sha
```

`--app-group` 必填，漏掉会闪退且键盘锁在 26 键。换用你自己的描述文件时，`dylib/gkx.m` 顶部的 `GXKGroup`、`inject.py` 默认值与 `--app-group` 三处必须一致。

固定下载地址：
```
https://github.com/IamNewHands/gboard-ntr/releases/latest/download/gboard-ntr-1.0-unsigned.ipa
```

---

## 📱 安装

1. 用 **LCSign** / SideStore / TrollStore 等工具自签安装。
2. 到「设置 → 通用 → 键盘 → 键盘 → Gboard」打开**允许完全访问**（词库与配置依赖 App Group）。
3. 覆盖安装后若未生效，删除键盘重新添加，或重启宿主 App。

---

## ⚠️ 免责声明与许可

* 本项目**不包含**任何 Google 官方二进制或 IPA，仓库里只有注入源码、词库转换脚本与文档。使用前需自行取得正版 **Gboard 2.3.19** IPA。
* 注入改造后的包**仅限个人设备自签测试**，不得分发、不得商用。Gboard 与 Mozc 的著作权归 Google 所有。
* 自签描述文件、证书与 App Group 需自行准备；仓库里的 `group.zunbengege.top` 只是示例值。
* 改造涉及未签名的二进制注入，升级系统或更换签名工具后行为可能变化，风险自负。
