"""
amlib.utils - 工具函数

- adb 命令封装(subprocess + 重试 + 超时)
- 设备信息采集(getprop / dumpsys package)
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from .exceptions import DeviceOfflineError, DeviceTimeoutError


def adb_command(
    cmd: list[str],
    serial: Optional[str] = None,
    timeout: int = 30,
    retry: int = 2,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    执行 adb 命令,带超时和重试。

    Args:
        cmd: adb 命令参数列表,如 ['shell', 'getprop', 'ro.product.model']
        serial: 设备 serial,None 表示默认设备
        timeout: 单次超时秒数
        retry: 失败重试次数
        check: True 时非零退出码抛异常

    Returns:
        subprocess.CompletedProcess

    Raises:
        DeviceTimeoutError: 超时
        DeviceOfflineError: 设备掉线
        subprocess.CalledProcessError: 命令失败(check=True 时)
    """
    full_cmd = ["adb"]
    if serial:
        full_cmd += ["-s", serial]
    full_cmd += cmd

    last_error: Optional[Exception] = None
    for attempt in range(retry + 1):
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if check and result.returncode != 0:
                # 检测设备掉线
                if "device not found" in result.stderr or "offline" in result.stderr:
                    raise DeviceOfflineError(serial or "default")
                raise subprocess.CalledProcessError(
                    result.returncode, full_cmd, result.stdout, result.stderr
                )
            return result
        except subprocess.TimeoutExpired as e:
            last_error = DeviceTimeoutError(" ".join(full_cmd), timeout)
            if attempt < retry:
                time.sleep(1)
                continue
            raise last_error from e
        except DeviceOfflineError:
            raise

    # 不应该到这里
    if last_error:
        raise last_error
    raise RuntimeError("adb_command: unknown error")


def parse_pidof(output: str) -> Optional[int]:
    """
    解析 `pidof <pkg>` 的输出,返回 PID。

    adb shell pidof com.example.app 通常返回:
      - 12345\n
      - 12345\n12346\n(多进程,取主进程)
    """
    output = output.strip()
    if not output:
        return None
    # 取第一个 PID(主进程)
    first = output.split()[0]
    try:
        return int(first)
    except ValueError:
        return None


def ensure_dir(path: Path) -> Path:
    """确保目录存在,不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_str() -> str:
    """生成 20260622_143015 格式的时间戳"""
    return time.strftime("%Y%m%d_%H%M%S")


def bytes_to_human(n: int) -> str:
    """字节数转人类可读(1.5MB / 800KB)"""
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def get_device_model(serial: Optional[str] = None) -> str:
    """获取设备型号"""
    result = adb_command(["shell", "getprop", "ro.product.model"], serial=serial, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_android_version(serial: Optional[str] = None) -> str:
    """获取 Android 版本号"""
    result = adb_command(
        ["shell", "getprop", "ro.build.version.release"], serial=serial, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_sdk_int(serial: Optional[str] = None) -> int:
    """获取 SDK 版本"""
    result = adb_command(
        ["shell", "getprop", "ro.build.version.sdk"], serial=serial, check=False
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def is_debuggable(pkg: str, serial: Optional[str] = None) -> bool:
    """检查包是否 debuggable(返回 True/False)"""
    result = adb_command(
        ["shell", "dumpsys", "package", pkg], serial=serial, check=False
    )
    # 匹配 flags 行的 DEBUGGABLE 关键字
    match = re.search(r"flags=\[([^\]]*)\]", result.stdout)
    if not match:
        return False
    return "DEBUGGABLE" in match.group(1)