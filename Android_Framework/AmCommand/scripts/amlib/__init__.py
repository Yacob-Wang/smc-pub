"""
amlib - Android am 命令的 Python SDK 封装

设计原则:
  1. 薄封装:在 subprocess 之上加错误处理、超时、重试
  2. 幂等:每个函数都可重复调用
  3. 自动归档:拉回的文件按时间戳+场景归档
  4. 可恢复:adb 设备掉线自动重连
  5. 人类可读错误:异常带根因 + 解决方案

典型用法:
    from amlib import Device, AM, ArtifactCollector

    dev = Device()  # 默认选第一台连接的设备
    am = AM(dev)

    # 冷启动测试
    result = am.cold_start_time('com.example.app/.MainActivity')
    print(f"WaitTime: {result['WaitTime']}ms")

    # 性能采样
    pid = am.get_pid('com.example.app')
    trace = am.profile_and_pull(pid, duration_sec=30, scene='cold_start')

    # 三段式现场保留
    collector = ArtifactCollector(dev, output_dir='./reports')
    archive = collector.collect_full('com.example.app', scene='crash')
"""

from .device import Device, DevicePool, list_devices
from .am import AM
from .artifact import ArtifactCollector
from .exceptions import (
    AMError,
    DeviceOfflineError,
    DeviceTimeoutError,
    ProfileError,
    DumpHeapError,
)

__version__ = "1.0.0"
__all__ = [
    "Device",
    "DevicePool",
    "list_devices",
    "AM",
    "ArtifactCollector",
    "AMError",
    "DeviceOfflineError",
    "DeviceTimeoutError",
    "ProfileError",
    "DumpHeapError",
]