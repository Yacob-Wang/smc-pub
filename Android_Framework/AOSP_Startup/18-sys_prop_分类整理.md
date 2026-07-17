# Android系统属性文件分类整理

## 文件信息
- **文件路径**: `D:\Users\jiabo.wang\LogInsight_LogFiles\downloads\version\USICPRO-448204\0xffffff13_2025_12_20_19_58_33_12\sys_prop`
- **总行数**: 1975行
- **设备型号**: TECNO SPARK Go 1 (KL4-OP)
- **Android版本**: Android 14 (API Level 34)
- **构建日期**: 2025年5月20日

---

## 一、系统构建与版本信息

### 1.1 构建信息
- **构建ID**: `UP1A.231005.007`
- **构建类型**: `user` (用户版本)
- **构建标签**: `release-keys` (正式发布版本)
- **增量版本**: `250520V3962`
- **安全补丁**: `2025-04-05`
- **构建主机**: `build-1-42`
- **构建用户**: `buildsrv-ci`

### 1.2 产品信息
- **品牌**: TECNO
- **型号**: TECNO KL4
- **市场名称**: TECNO SPARK Go 1
- **设备代号**: TECNO-KL4
- **硬件平台**: `ums9230_KL4_go`
- **主板**: TECNO-KL4

### 1.3 系统版本
- **Android版本**: 14
- **SDK版本**: 34
- **首次API级别**: 34
- **HiOS版本**: `hios14.0.1`
- **OS版本**: `OS14.0.1-U-P81-231129`

### 1.4 芯片信息
- **SoC制造商**: Spreadtrum (展讯)
- **SoC型号**: T615
- **芯片ID**: UMS9230-AC
- **PMIC芯片ID**: 2730
- **平台**: ums9230

---

## 二、硬件配置信息

### 2.1 内存配置
- **DDR大小**: 3072M (3GB)
- **DDR范围**: [3072,4096)
- **低内存设备**: `true` (ro.config.low_ram)

### 2.2 CPU架构
- **主架构**: arm64-v8a
- **CPU变体**: cortex-a75
- **二级架构**: arm
- **二级CPU变体**: cortex-a55
- **支持架构**: arm64-v8a, armeabi-v7a, armeabi

### 2.3 显示配置
- **屏幕密度**: 320 dpi (ro.sf.lcd_density)
- **逻辑宽度**: 720
- **逻辑高度**: 1600
- **OpenGL ES版本**: 196610
- **GPU**: Mali
- **HDR支持**: false
- **宽色域支持**: false

### 2.4 存储配置
- **存储类型**: 2 (persist.storage.type)
- **根磁盘**: mmcblk0
- **数据分区**: mmcblk0p75 (块设备), dm-62 (设备映射)
- **系统分区**: 使用动态分区 (ro.boot.dynamic_partitions: true)

---

## 三、分区与挂载信息

### 3.1 分区挂载点
- **根分区**: mmcblk0p46 (dm-14)
- **系统分区**: 动态分区
- **供应商分区**: mmcblk0p46 (dm-16)
- **产品分区**: mmcblk0p46 (dm-18)
- **ODM分区**: mmcblk0p46 (dm-17)
- **数据分区**: mmcblk0p75 (dm-62)
- **缓存分区**: mmcblk0p47 (dm-缓存)
- **元数据分区**: mmcblk0p51
- **黑盒分区**: mmcblk0p48

### 3.2 分区验证状态
所有关键分区已验证 (verified: 2):
- **ODM**: sha256, 根摘要: `1d2b50c3...`
- **Product**: sha256, 根摘要: `2b68af07...`
- **System**: sha256, 根摘要: `7af2768e...`
- **System_ext**: sha256, 根摘要: `741b16ac...`
- **System_dlkm**: sha256, 根摘要: `58b5f266...`
- **Vendor**: sha256, 根摘要: `d459db1a...`
- **Vendor_dlkm**: sha256, 根摘要: `e183cc66...`

### 3.3 加密状态
- **加密状态**: encrypted
- **加密类型**: file
- **元数据加密**: enabled
- **使用fs_ioc_add_encryption_key**: true

---

## 四、启动与初始化信息

### 4.1 启动原因
- **当前启动原因**: `reboot,userrequested` (用户请求重启)
- **上次启动原因**: `reboot,userrequested`
- **启动历史**: 
  - reboot,userrequested,1765249685
  - reboot,userrequested,1765205563

### 4.2 启动模式
- **启动模式**: normal (正常模式)
- **Tran启动模式**: normal
- **强制正常启动**: true
- **启动槽**: _b (B槽)

### 4.3 启动完成状态
- **启动完成**: true (sys.boot_completed: 1)
- **首次启动完成**: true
- **冷启动完成**: true (ro.cold_boot_done: true)
- **APEX就绪**: true (apex.all.ready: true)
- **APEXD状态**: ready

### 4.4 关键服务启动时间 (纳秒)
重要服务的启动时间戳:
- **init**: 353863307
- **logd**: 2289202305
- **servicemanager**: 2304802959
- **hwservicemanager**: 2309128075
- **zygote**: 5404893226
- **zygote_secondary**: 5410715457
- **system_server**: 11443ms (sys.system_server.start_elapsed)

---

## 五、系统服务状态

### 5.1 核心服务 (运行中)
- **logd**: running (PID: 315)
- **servicemanager**: running (PID: 318)
- **hwservicemanager**: running (PID: 319)
- **lmkd**: running (PID: 316)
- **zygote**: running (PID: 579)
- **zygote_secondary**: running (PID: 580)
- **surfaceflinger**: running (PID: 624)
- **audioserver**: running (PID: 617)
- **cameraserver**: running (PID: 786)
- **netd**: running (PID: 578)
- **vold**: running (PID: 359)

### 5.2 媒体服务
- **media**: running (PID: 798)
- **media.swcodec**: running (PID: 856)
- **media.unisoc.codec2**: running (PID: 601)
- **mediaextractor**: running (PID: 795)
- **mediametrics**: running (PID: 796)
- **mediadrm**: running

### 5.3 安全服务
- **keystore2**: running (PID: 405)
- **gatekeeperd**: running (PID: 858)
- **credstore**: running (PID: 618)
- **tombstoned**: running (PID: 450)

### 5.4 网络服务
- **netd**: running (PID: 578)
- **wificond**: running (PID: 802)
- **sprd_networkcontrol**: running (PID: 815)

### 5.5 供应商服务
- **vendor.audio-hal**: running (PID: 591)
- **vendor.bluetooth-1-1**: running (PID: 592)
- **vendor.camera-provider-2-4**: running (PID: 595)
- **vendor.ril-daemon**: running (PID: 635)
- **vendor.modem_control**: running (PID: 630)

---

## 六、网络与通信

### 6.1 移动网络
- **网络类型**: LTE, LTE (双卡)
- **运营商**: 
  - SIM1: Malitel (61001)
  - SIM2: ORANGE ML (61002)
- **国家代码**: ml, ml (马里)
- **漫游状态**: false, false
- **SIM状态**: LOADED, LOADED
- **VoLTE状态**: 0, 0 (未启用)
- **VoWiFi状态**: 0, 0 (未启用)

### 6.2 基带信息
- **基带版本**: `4G_MODEM_22B_W24.26.3_P7|qogirl6_modem` (双卡相同)
- **RIL实现**: android reference-ril 1.0
- **调制解调器类型**: l (LTE)
- **调制解调器配置**: TL_LF_W_G, TL_LF_W_G
- **工作模式**: 6, 6

### 6.3 WiFi配置
- **WiFi接口**: wlan0
- **直接接口**: p2p-dev-wlan0
- **驱动状态**: unloaded
- **驱动版本**: 5.15.148-android13-8-g551938f2788c-ab765
- **固件版本**: 57824

### 6.4 蓝牙配置
- **A2DP卸载支持**: true
- **设备类别**: 90,2,12
- **启用的配置文件**:
  - A2DP Source: true
  - AVRCP Target: true
  - HFP AG: true
  - HID Device/Host: true
  - MAP Server: true
  - OPP: true
  - PAN NAP/PANU: true
  - PBAP Server: true
  - GATT: true
  - ASHA Central: true
  - BAS Client: true

### 6.5 网络接口
- **数据接口**: seth_lte0
- **IP地址**: 10.93.14.193
- **DNS服务器**: 
  - 217.64.98.67
  - 217.64.98.75

---

## 七、Dalvik虚拟机配置

### 7.1 堆内存配置
- **堆增长限制**: 128m
- **堆最大大小**: 256m
- **堆起始大小**: 8m
- **堆最小空闲**: 512k
- **堆最大空闲**: 8m
- **堆目标利用率**: 0.75
- **前台堆增长倍数**: 2.0

### 7.2 编译配置
- **Dex2oat Xms**: 64m
- **Dex2oat Xmx**: 512m
- **系统服务器编译过滤器**: speed-profile
- **使用JIT**: true
- **使用ART服务**: true
- **USAP池**: disabled

### 7.3 架构配置
- **ARM变体**: cortex-a55
- **ARM64变体**: cortex-a75
- **应用镜像格式**: lz4

---

## 八、存储与文件系统

### 8.1 文件系统特性
- **Casefold支持**: enabled (外部存储)
- **Project ID支持**: enabled (外部存储)
- **SDCardFS**: disabled (external_storage.sdcardfs.enabled: 0)
- **FUSE**: enabled
- **FUSE直通**: enabled

### 8.2 存储服务
- **Vold就绪**: true
- **模拟卷就绪**: true
- **可适配存储**: true
- **配额支持**: true
- **保留空间**: true
- **压缩支持**: false

### 8.3 ZRAM配置
- **ZRAM启用**: true
- **首次回写延迟**: 180分钟
- **标记空闲延迟**: 60分钟
- **定期回写延迟**: 24小时

---

## 九、图形与显示

### 9.1 SurfaceFlinger配置
- **渲染后端**: skiaglthreaded
- **GPU安全**: enabled
- **跳过旋转**: enabled
- **最大帧缓冲获取缓冲区**: 3
- **最大虚拟显示尺寸**: 4096
- **主显示方向**: ORIENTATION_0
- **内容检测刷新率**: true

### 9.2 显示增强
- **显示增强**: true
- **超分辨率**: 0 (禁用)
- **颜色饱和度**: 1.0
- **CABC**: enabled
- **DCI**: enabled

### 9.3 图形配置
- **使用Vulkan**: true
- **强制HWC复制虚拟显示**: true
- **使用上下文优先级**: true

---

## 十、相机配置

### 10.1 传感器信息
- **传感器**: 
  - id0: s5k3l6_1836_13M (后置)
  - id1: hi846_1931_8M (前置)
- **传感器芯片ID**: 81E2C65E5570
- **闪光灯**: aw36515_0

### 10.2 相机功能
- **多相机**: enabled
- **超广角**: enabled
- **人像模式**: enabled (前后)
- **夜景Pro**: enabled
- **HDR版本**: 4
- **MFNR版本**: 3
- **双视图**: enabled (版本2)

### 10.3 相机参数版本
- **后置参数版本**: 2024.07.24_V1.1.1.1
- **前置参数版本**: 2024.07.24_V1.1.1.1

---

## 十一、音频配置

### 11.1 音频HAL
- **音频HAL版本**: V1.7_20250219
- **Whale HAL**: true
- **音频卸载唤醒锁**: false

### 11.2 AAudio配置
- **MMAP策略**: 2
- **MMAP独占策略**: 2

### 11.3 音频功能
- **大音量**: enabled
- **HiFi音频**: disabled
- **音频源**: true

---

## 十二、安全与认证

### 12.1 设备安全
- **安全启动状态**: green (已验证)
- **验证模式**: enforcing
- **防回滚状态**: 1
- **OEM解锁支持**: true
- **OEM解锁允许**: false (sys.oem_unlock_allowed: 0)
- **闪存锁定**: true

### 12.2 生物识别
- **指纹支持**: true
- **指纹配置**: microarray
- **面部识别支持**: true
- **面部识别版本**: 2
- **低电量光**: true

### 12.3 密钥管理
- **Keystore启动级别**: 1000000000
- **KeyMint**: vendor.keymint-unisoc-2.0 (running)
- **Gatekeeper**: vendor.gatekeeper-1-0 (running)

---

## 十三、电源管理

### 13.1 电源配置
- **快速充电支持**: true
- **睡眠主控**: true
- **触摸电源**: enabled
- **超省电模式**: enabled

### 13.2 电池相关
- **充电动画无线功率**: 0
- **充电显示类型**: 1
- **充电动画支持**: true

### 13.3 热管理
- **热节流支持**: yes
- **热空间支持**: 0 (禁用)
- **最大亮度**: 4095

---

## 十四、调试与日志

### 14.1 调试配置
- **可调试**: false (ro.debuggable: 0)
- **强制可调试**: false
- **ADB安全**: true (ro.adb.secure: 1)
- **Atrace标签**: 0

### 14.2 日志配置
- **Logd就绪**: true
- **Logd大小统计**: 64K
- **Ylog版本**: 4.1.03
- **Ylog启动时间**: enabled
- **FWC调试**: disabled

### 14.3 跟踪配置
- **Traced启用**: true
- **Traced已启动**: true
- **Traced_probes**: running

---

## 十五、应用与运行时

### 15.1 应用管理
- **设备已配置**: true (persist.sys.device_provisioned: 1)
- **OOBE状态**: 2
- **OOBE设备锁定**: 2
- **OOBE国家**: ML

### 15.2 运行时配置
- **首次启动时间**: 1765267527893
- **使用UFFD GC**: true
- **使用代际GC**: true
- **应用镜像启动缓存**: true

### 15.3 包管理
- **包验证线程数**: 8
- **包验证权重**: enabled
- **APM版本**: 3.0
- **APM支持**: true

---

## 十六、供应商特定功能

### 16.1 Transsion特定功能
- **Tran引擎启动完成**: true
- **TranFac包**: com.reallytek.wg
- **TranCare状态**: 1
- **TranLog支持**: true
- **TranOS类型**: hios

### 16.2 系统优化
- **Griffin支持**: true
- **Griffin版本**: 2.1
- **Griffin核心**: enabled
- **Griffin PM**: enabled
- **Griffin资源监控**: enabled

### 16.3 特殊功能
- **Skyroam支持**: true
- **Skyroam SIMO**: enabled
- **Skyroam OSI版本**: 3.2.2.14
- **Skyroam OSI状态**: running
- **Skyroam OSI类型**: gsim

---

## 十七、设备特定配置

### 17.1 设备特性
- **刘海支持**: 2
- **显示切口支持**: true
- **侧边指纹**: true
- **手势导航**: true
- **隐藏导航栏**: true
- **动态栏支持**: true

### 17.2 区域配置
- **时区**: Africa/Bamako (马里巴马科)
- **时区置信度**: 100
- **语言环境**: fr-FR (法语-法国)
- **默认语言环境**: en-US

### 17.3 序列号与标识
- **序列号**: 12922554AF000588
- **蓝牙地址路径**: /data/vendor/bluetooth/btmac.txt

---

## 十八、性能优化配置

### 18.1 内存管理
- **LMK最小空闲级别**: 18432:0,23040:100,27648:200,32256:250,55296:900,80640:950
- **LMK报告杀死**: enabled
- **LMK关键升级**: true
- **LMK升级压力**: 40
- **LMK降级压力**: 60

### 18.2 存储优化
- **智能空闲维护**: enabled
- **智能空闲维护周期**: 60秒
- **脏页回收率**: 0.5
- **目标脏页比例**: 80
- **最小GC睡眠时间**: 5000ms

### 18.3 网络优化
- **数据VIP快速通道**: disabled
- **数据速率始终显示**: enabled
- **数据速率Plus**: enabled
- **数据失速支持**: enabled
- **首选网络支持**: enabled

---

## 十九、开发与测试配置

### 19.1 工厂模式
- **工厂模式启用**: false (persist.sys.factory.enable: 0)
- **Itel工厂**: false (ro.boot.itelfactory: 0)

### 19.2 测试配置
- **模拟位置**: disabled
- **允许模拟位置**: false
- **零售演示**: disabled

---

## 二十、其他重要配置

### 20.1 USB配置
- **USB配置**: mtp
- **USB模式**: normal
- **USB控制器**: musb-hdrc.1.auto
- **USB配置FS**: enabled

### 20.2 虚拟AB分区
- **虚拟AB启用**: true
- **虚拟AB压缩**: enabled
- **虚拟AB压缩线程**: true
- **用户空间快照**: enabled

### 20.3 系统属性服务
- **属性服务版本**: 2
- **持久属性就绪**: true
- **服务管理器就绪**: true
- **硬件服务管理器就绪**: true

---

## 总结

这是一个运行Android 14的TECNO SPARK Go 1设备的完整系统属性快照。设备配置为低内存设备(3GB RAM)，使用Spreadtrum T615芯片，支持双SIM卡LTE网络。系统已完全启动并运行，所有关键服务正常，分区已验证，设备处于安全锁定状态。

### 关键指标
- **Android版本**: 14 (API 34)
- **内存**: 3GB DDR
- **存储**: 动态分区，已加密
- **网络**: 双SIM LTE
- **安全**: 已验证启动，设备锁定
- **状态**: 系统完全启动，所有服务运行正常
