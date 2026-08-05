"""
amlib.device - 设备管理

提供:
- Device: 单台设备的封装
- DevicePool: 多设备并发管理
- list_devices(): 列出所有连接的设备
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from . import utils
from .exceptions import DeviceOfflineError

logger = logging.getLogger(__name__)


@dataclass
class Device:
    """
    单台 adb 设备的封装。

    自动处理:
      - adb 命令超时
      - 设备掉线重连
      - 跨设备端口冲突(forward)
    """

    serial: str
    model: str = "unknown"
    android_version: str = "unknown"
    sdk_int: int = 0

    def __post_init__(self):
        if self.model == "unknown":
            self.model = utils.get_device_model(self.serial)
        if self.sdk_int == 0:
            self.sdk_int = utils.get_sdk_int(self.serial)
        if self.android_version == "unknown":
            self.android_version = utils.get_android_version(self.serial)

    def __repr__(self) -> str:
        return f"Device(serial={self.serial!r}, model={self.model!r}, android={self.android_version})"

    # ---------- 基础命令封装 ----------

    def shell(self, cmd: str, timeout: int = 30, retry: int = 2) -> str:
        """
        执行 adb shell 命令,返回 stdout。

        Args:
            cmd: shell 命令字符串(如 "getprop ro.product.model")
            timeout: 超时秒数
            retry: 失败重试次数

        Returns:
            stdout 字符串(已 strip)

        Raises:
            DeviceTimeoutError: 超时
            DeviceOfflineError: 设备掉线
        """
        result = utils.adb_command(
            ["shell", cmd], serial=self.serial, timeout=timeout, retry=retry, check=False
        )
        if result.returncode != 0:
            # 检测离线
            if "device not found" in result.stderr or "offline" in result.stderr:
                # 尝试重连
                if self._reconnect():
                    return self.shell(cmd, timeout, retry - 1) if retry > 0 else ""
                raise DeviceOfflineError(self.serial)
            # 其他错误,返回 stderr 供调用方判断
            logger.warning("shell command failed (rc=%d): %s | stderr: %s",
                           result.returncode, cmd, result.stderr.strip())
        return result.stdout.strip()

    def shell_json(self, cmd: str, **kwargs) -> dict:
        """执行 shell 命令,期望返回 JSON"""
        import json
        output = self.shell(cmd, **kwargs)
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw": output}

    def push(self, local: str | Path, remote: str) -> bool:
        """adb push 文件"""
        result = utils.adb_command(
            ["push", str(local), remote], serial=self.serial, timeout=120, check=False
        )
        return result.returncode == 0

    def pull(self, remote: str, local: str | Path, timeout: int = 120) -> bool:
        """adb pull 文件"""
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        result = utils.adb_command(
            ["pull", remote, str(local)], serial=self.serial, timeout=timeout, check=False
        )
        return result.returncode == 0

    def install(self, apk: str | Path, replace: bool = True) -> bool:
        """adb install APK"""
        cmd = ["install", "-r" if replace else "", str(apk)]
        cmd = [c for c in cmd if c]  # 移除空串
        result = utils.adb_command(cmd, serial=self.serial, timeout=180, check=False)
        return result.returncode == 0

    def forward(self, port_local: int, port_remote: int) -> bool:
        """adb forward(注意端口冲突,见 06 篇 §7.2)"""
        result = utils.adb_command(
            ["forward", f"tcp:{port_local}", f"tcp:{port_remote}"],
            serial=self.serial,
            check=False,
        )
        return result.returncode == 0

    # ---------- 设备信息 ----------

    def get_device_info(self) -> dict:
        """获取完整设备信息"""
        return {
            "serial": self.serial,
            "model": self.model,
            "android_version": self.android_version,
            "sdk_int": self.sdk_int,
            "abi": self.shell("getprop ro.product.cpu.abi"),
            "kernel": self.shell("uname -r"),
            "build_fingerprint": self.shell("getprop ro.build.fingerprint"),
            "free_storage": self.shell("df /data | tail -1 | awk '{print $4}'"),
        }

    # ---------- 内部 ----------

    def _reconnect(self) -> bool:
        """尝试重连设备"""
        logger.info("尝试重连设备 %s...", self.serial)
        utils.adb_command(["reconnect", "offline"], timeout=10, check=False)
        time.sleep(2)
        devices = list_devices()
        return any(d.serial == self.serial for d in devices)


def list_devices() -> List[Device]:
    """
    列出所有连接的 adb 设备。

    Returns:
        List[Device]

    Raises:
        DeviceOfflineError: 没有可用设备
    """
    result = utils.adb_command(["devices", "-l"], check=False)
    devices = []
    for line in result.stdout.splitlines()[1:]:  # 跳过 "List of devices attached"
        line = line.strip()
        if not line or "offline" in line:
            continue
        # 解析: serial state model:xxx device:yyy
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        try:
            devices.append(Device(serial=serial))
        except Exception as e:
            logger.warning("创建设备对象失败 %s: %s", serial, e)
    if not devices:
        raise DeviceOfflineError("no device")
    return devices


@dataclass
class DevicePool:
    """
    多设备并发管理。

    用法:
        pool = DevicePool(criteria={'android_version': ['13', '14']})
        results = pool.parallel_run(check_cold_start, args=('com.app',), max_workers=4)
    """

    devices: List[Device]
    max_workers: int = 4

    @classmethod
    def from_criteria(
        cls,
        criteria: Optional[dict] = None,
        max_workers: int = 4,
    ) -> "DevicePool":
        """
        按条件筛选设备。

        criteria 支持的键:
          - android_version: List[str],如 ['13', '14']
          - sdk_int: List[int],如 [33, 34]
          - abi: List[str],如 ['arm64-v8a']
          - exclude_serials: List[str],如 ['known_bad_serial']
        """
        all_devices = list_devices()
        if not criteria:
            return cls(devices=all_devices, max_workers=max_workers)

        filtered = []
        for dev in all_devices:
            # android_version 过滤
            if "android_version" in criteria:
                if dev.android_version not in criteria["android_version"]:
                    continue
            # sdk_int 过滤
            if "sdk_int" in criteria:
                if dev.sdk_int not in criteria["sdk_int"]:
                    continue
            # abi 过滤
            if "abi" in criteria:
                abi = dev.shell("getprop ro.product.cpu.abi")
                if abi not in criteria["abi"]:
                    continue
            # exclude 过滤
            if "exclude_serials" in criteria:
                if dev.serial in criteria["exclude_serials"]:
                    continue
            filtered.append(dev)

        return cls(devices=filtered, max_workers=max_workers)

    def parallel_run(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        max_workers: Optional[int] = None,
    ) -> dict:
        """
        并发在所有设备上跑同一个函数。

        Args:
            func: 接受 device 作为第一个参数的函数
            args: 传给 func 的额外位置参数
            kwargs: 传给 func 的关键字参数
            max_workers: 最大并发数(默认 self.max_workers)

        Returns:
            {serial: result_or_exception}
        """
        kwargs = kwargs or {}
        max_workers = max_workers or self.max_workers

        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_serial = {}
            for dev in self.devices:
                future = executor.submit(func, dev, *args, **kwargs)
                future_to_serial[future] = dev.serial

            for future in as_completed(future_to_serial):
                serial = future_to_serial[future]
                try:
                    results[serial] = future.result()
                except Exception as e:
                    logger.exception("设备 %s 执行失败", serial)
                    results[serial] = e

        return results

    def parallel_run_batch(
        self,
        jobs: List[dict],
        max_workers: Optional[int] = None,
    ) -> dict:
        """
        并发跑多个不同的任务。

        jobs 是 dict 列表,每个 dict 包含:
          - func: 函数
          - args: tuple(默认 ())
          - kwargs: dict(默认 {})
          - devices: 可选,只在指定设备上跑

        Returns:
            {(serial, job_idx): result_or_exception}
        """
        max_workers = max_workers or self.max_workers
        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {}
            for idx, job in enumerate(jobs):
                func = job["func"]
                args = job.get("args", ())
                kwargs = job.get("kwargs", {})
                target_devices = job.get("devices", self.devices)

                for dev in target_devices:
                    future = executor.submit(func, dev, *args, **kwargs)
                    future_to_key[future] = (dev.serial, idx)

            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.exception("任务 %s 执行失败", key)
                    results[key] = e

        return results