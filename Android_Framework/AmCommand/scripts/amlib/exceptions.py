"""
amlib.exceptions - amlib 自定义异常类

所有异常的根类: AMError
子类按错误源划分:
  - DeviceOfflineError: adb 设备掉线
  - DeviceTimeoutError: shell 命令超时
  - ProfileError: am profile 失败
  - DumpHeapError: am dumpheap 失败
"""

from __future__ import annotations


class AMError(Exception):
    """amlib 所有异常的基类"""

    def __init__(self, message: str, root_cause: str = "", fix: str = ""):
        super().__init__(message)
        self.message = message
        self.root_cause = root_cause
        self.fix = fix

    def __str__(self) -> str:
        parts = [self.message]
        if self.root_cause:
            parts.append(f"  根因: {self.root_cause}")
        if self.fix:
            parts.append(f"  解决: {self.fix}")
        return "\n".join(parts)


class DeviceOfflineError(AMError):
    """adb 设备掉线或不可达"""

    def __init__(self, serial: str):
        super().__init__(
            message=f"设备 {serial} 不可达",
            root_cause="可能原因: USB 断开 / adb server 异常 / 设备未授权",
            fix="检查 adb devices 列表,或执行 adb reconnect offline 重连",
        )
        self.serial = serial


class DeviceTimeoutError(AMError):
    """adb shell 命令超时"""

    def __init__(self, cmd: str, timeout_sec: int):
        super().__init__(
            message=f"shell 命令超时 ({timeout_sec}s): {cmd}",
            root_cause="可能原因: 设备响应慢 / 命令本身卡住(am dumpheap 等重操作)",
            fix="增加 timeout 参数,或检查设备状态(adb shell df 看存储空间)",
        )
        self.cmd = cmd
        self.timeout_sec = timeout_sec


class ProfileError(AMError):
    """am profile 失败"""

    def __init__(self, message: str):
        super().__init__(
            message=f"am profile 失败: {message}",
            root_cause="常见原因: app 未 debuggable / 路径不在 /data/local/tmp/ / 进程已死",
            fix="确认 dumpsys package 的 flags 含 DEBUGGABLE,确认文件路径,确认进程存活",
        )


class DumpHeapError(AMError):
    """am dumpheap 失败"""

    def __init__(self, message: str):
        super().__init__(
            message=f"am dumpheap 失败: {message}",
            root_cause="常见原因: 文件路径无写权限 / 设备存储满 / dump 期间 app 已死",
            fix="检查 /data/local/tmp/ 目录权限,清理设备存储",
        )