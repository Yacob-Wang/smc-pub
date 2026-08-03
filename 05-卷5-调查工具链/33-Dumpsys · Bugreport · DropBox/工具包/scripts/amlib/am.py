"""
amlib.am - am 命令的 Python 封装

覆盖前 5 篇所有 am 命令:
  - 02 篇: kill / force_stop / crash / restart
  - 03 篇: profile start / stop
  - 04 篇: dumpheap
  - 05 篇: hang / monitor
  - 01 篇: start / start-activity
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Iterator, List, Optional

from .device import Device
from .exceptions import AMError, DumpHeapError, ProfileError

logger = logging.getLogger(__name__)


class AM:
    """am 命令的 Python 封装"""

    def __init__(self, device: Device):
        self.device = device

    # ==================== 01 篇: Activity 启动 ====================

    def start(
        self,
        component: str,
        wait: bool = False,
        user: Optional[int] = None,
    ) -> dict:
        """
        启动 Activity(或 Service/Broadcast)。

        Args:
            component: 完整组件名,如 "com.example.app/.MainActivity"
            wait: True 时用 -W,返回 WaitTime/ThisTime/TotalTime
            user: 多用户设备的 userId

        Returns:
            wait=True: {'WaitTime': ms, 'ThisTime': ms, 'TotalTime': ms, 'Status': 'ok'}
            wait=False: {'Status': 'ok'}

        Example:
            result = am.start('com.app/.MainActivity', wait=True)
            print(f"冷启动 WaitTime: {result['WaitTime']}ms")
        """
        cmd_parts = ["am", "start"]
        if user is not None:
            cmd_parts += ["--user", str(user)]
        if wait:
            cmd_parts.append("-W")
        cmd_parts.append(component)

        cmd_str = " ".join(cmd_parts)
        output = self.device.shell(cmd_str, timeout=60)

        result = {"Status": "ok", "raw": output}
        if wait:
            # 解析 am start -W 的输出:
            #   Status: ok
            #   LaunchState: COLD
            #   Activity: com.example.app/.MainActivity
            #   WaitTime: 850
            #   ThisTime: 720
            #   TotalTime: 920
            for key in ["Status", "LaunchState", "Activity", "WaitTime", "ThisTime", "TotalTime"]:
                match = re.search(rf"{key}:\s*(.+)", output)
                if match:
                    value = match.group(1).strip()
                    if key in ("WaitTime", "ThisTime", "TotalTime"):
                        try:
                            result[key] = int(value)
                        except ValueError:
                            result[key] = value
                    else:
                        result[key] = value
        return result

    def cold_start_time(self, component: str) -> dict:
        """便捷方法:返回冷启动 WaitTime(强制先 kill 确保冷启动)"""
        pkg = component.split("/")[0]
        self.force_stop(pkg)
        time.sleep(2)
        return self.start(component, wait=True)

    # ==================== 02 篇: 进程管理 ====================

    def kill(self, pkg: str, user: Optional[int] = None) -> bool:
        """
        am kill:模拟 LMKD 杀进程(SIGKILL,无回调)。

        详见 02 篇 §2.2。
        """
        cmd = f"am kill --user {user} {pkg}" if user is not None else f"am kill {pkg}"
        output = self.device.shell(cmd, timeout=10)
        return True  # am kill 成功通常无输出

    def force_stop(self, pkg: str, user: Optional[int] = None) -> bool:
        """
        am force-stop:模拟用户滑任务(走 onDestroy 链)。

        详见 02 篇 §3.2。
        """
        cmd = f"am force-stop --user {user} {pkg}" if user is not None else f"am force-stop {pkg}"
        output = self.device.shell(cmd, timeout=10)
        return True

    def crash(
        self,
        pkg: str,
        allow_restart: bool = False,
        user: Optional[int] = None,
    ) -> bool:
        """
        am crash:触发 Java RuntimeException。

        详见 02 篇 §4.3。
        注意:这是 Java crash,不是 native crash。
        """
        cmd_parts = ["am", "crash"]
        if user is not None:
            cmd_parts += ["--user", str(user)]
        if allow_restart:
            cmd_parts.append("--allow-restart")
        cmd_parts.append(pkg)
        output = self.device.shell(" ".join(cmd_parts), timeout=10)
        return True

    def restart(self) -> bool:
        """
        am restart:重启 system_server(慎用!)。

        详见 02 篇 §5.2。
        """
        logger.warning("am restart 会重启 system_server,谨慎使用!")
        output = self.device.shell("am restart", timeout=30)
        return True

    # ==================== 03 篇: profile 采样 ====================

    def get_pid(self, pkg: str) -> int:
        """
        获取包的主进程 PID(找不到时抛 AMError)。

        详见 01 篇 §3.2。
        """
        output = self.device.shell(f"pidof {pkg}", timeout=10)
        if not output:
            raise AMError(
                message=f"找不到包 {pkg} 的 PID",
                root_cause="可能原因: app 未启动 / 进程名不匹配",
                fix=f"先 adb shell am start -n {pkg}/... 启动 app",
            )
        return int(output.split()[0])

    def profile_start(
        self,
        pid: int,
        device_path: str = "/data/local/tmp/trace.trace",
        user: Optional[int] = None,
    ) -> None:
        """
        am profile start:启动 Method Trace 采样。

        详见 03 篇 §2.2。

        Raises:
            ProfileError: 启动失败
        """
        if not device_path.startswith("/data/local/tmp/"):
            raise ProfileError(f"profile 文件路径必须在 /data/local/tmp/ 开头: {device_path}")

        cmd_parts = ["am", "profile", "start"]
        if user is not None:
            cmd_parts += ["--user", str(user)]
        cmd_parts += [str(pid), device_path]
        output = self.device.shell(" ".join(cmd_parts), timeout=10)

        if "Profiling failed" in output or "failed" in output.lower():
            raise ProfileError(output)

    def profile_stop(self, pid: int, user: Optional[int] = None) -> Optional[Path]:
        """
        am profile stop:停止采样,自动 pull 文件到当前目录。

        详见 03 篇 §2.3。
        注意:文件被 pull 到调用 adb 的进程的工作目录。
        """
        cmd_parts = ["am", "profile", "stop"]
        if user is not None:
            cmd_parts += ["--user", str(user)]
        cmd_parts.append(str(pid))
        output = self.device.shell(" ".join(cmd_parts), timeout=15)
        # 解析输出看是否成功
        return None  # 文件自动 pull 到当前目录,调用方自己管理

    def profile_and_pull(
        self,
        pid: int,
        duration_sec: int,
        scene: str = "manual",
        output_dir: Optional[Path] = None,
        with_dumpheap: bool = False,
    ) -> dict:
        """
        完整的 profile 流程: start → 等 N 秒 → stop → 自动归档。

        详见 03 篇 §5。

        Args:
            pid: 目标进程 PID
            duration_sec: 采样时长
            scene: 场景描述(用于归档目录名)
            output_dir: 输出根目录,默认当前目录
            with_dumpheap: 是否在采样中段触发 heap dump

        Returns:
            {'trace': Path, 'heap': Optional[Path], 'meta': dict}
        """
        from . import utils

        output_dir = Path(output_dir or ".")
        scene_dir = output_dir / utils.timestamp_str() / scene
        scene_dir.mkdir(parents=True, exist_ok=True)

        device_path = "/data/local/tmp/trace.trace"
        self.profile_start(pid, device_path)

        meta = {
            "scene": scene,
            "pid": pid,
            "duration_sec": duration_sec,
            "with_dumpheap": with_dumpheap,
            "device": self.device.get_device_info(),
            "time_alignment": {
                "profile_start": self.device.shell("date +%s.%N"),
            },
        }

        if with_dumpheap:
            dump_delay = duration_sec // 2
            time.sleep(dump_delay)
            meta["time_alignment"]["dumpheap"] = self.device.shell("date +%s.%N")
            try:
                self.dumpheap(pid, "/data/local/tmp/heap.hprof")
            except DumpHeapError as e:
                logger.warning("dumpheap failed during profile: %s", e)
            time.sleep(duration_sec - dump_delay)
        else:
            time.sleep(duration_sec)

        meta["time_alignment"]["profile_stop"] = self.device.shell("date +%s.%N")

        # profile stop 会自动 pull 到当前目录
        # 我们切到 scene_dir 后再 stop
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(scene_dir)
            self.profile_stop(pid)
        finally:
            os.chdir(original_cwd)

        # 等待 pull 完成
        time.sleep(2)

        result = {"meta": meta}
        trace_file = scene_dir / "trace.trace"
        if trace_file.exists():
            result["trace"] = trace_file
            meta["trace_size"] = trace_file.stat().st_size
        else:
            logger.warning("trace.trace not found in %s", scene_dir)

        if with_dumpheap:
            heap_file = scene_dir / "heap.hprof"
            if not heap_file.exists():
                # am dumpheap 不会自动 pull
                self.device.pull("/data/local/tmp/heap.hprof", heap_file)
            if heap_file.exists():
                result["heap"] = heap_file
                meta["heap_size"] = heap_file.stat().st_size

        # 保存元信息
        import json
        with open(scene_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return result

    # ==================== 04 篇: dumpheap ====================

    def dumpheap(self, pid: int, device_path: str = "/data/local/tmp/heap.hprof") -> None:
        """
        am dumpheap:触发 Java 堆 dump。

        详见 04 篇 §2.2。

        Raises:
            DumpHeapError: dump 失败
        """
        cmd = f"am dumpheap {pid} {device_path}"
        output = self.device.shell(cmd, timeout=60)  # dump 期间 app 卡顿,需要长超时
        if "Error" in output or "failed" in output.lower():
            raise DumpHeapError(output)

    def dumpheap_and_pull(
        self,
        pid: int,
        scene: str = "manual",
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        完整的 dumpheap 流程: dump → pull → 自动归档。

        Returns:
            本地 heap.hprof 路径
        """
        from . import utils

        output_dir = Path(output_dir or ".")
        scene_dir = output_dir / utils.timestamp_str() / scene
        scene_dir.mkdir(parents=True, exist_ok=True)

        device_path = "/data/local/tmp/heap.hprof"
        self.dumpheap(pid, device_path)

        local_path = scene_dir / "heap.hprof"
        if not self.device.pull(device_path, local_path, timeout=120):
            raise DumpHeapError(f"pull failed: {device_path} -> {local_path}")

        return local_path

    # ==================== 05 篇: hang / monitor ====================

    def hang(self, pid: int, allow_restart: bool = True) -> bool:
        """
        am hang:触发 Input ANR。

        详见 05 篇 §2。

        Args:
            pid: 目标进程 PID
            allow_restart: True 时 ANR 后会自动 kill 进程
        """
        cmd_parts = ["am", "hang"]
        if allow_restart:
            cmd_parts.append("--allow-restart")
        cmd_parts.append(str(pid))
        output = self.device.shell(" ".join(cmd_parts), timeout=15)
        return True

    def monitor_start(self) -> "MonitorSession":
        """
        启动 am monitor(后台运行),返回 MonitorSession 用于读事件流。

        详见 05 篇 §3.2。
        """
        return MonitorSession(self.device)

    def monitor(self, duration_sec: int) -> List[dict]:
        """
        同步跑 am monitor 持续 N 秒,返回事件列表。

        简单场景用这个,复杂场景用 monitor_start。
        """
        events: List[dict] = []
        with self.monitor_start() as monitor:
            time.sleep(duration_sec)
            events = monitor.collect_events()
        return events


class MonitorSession:
    """
    am monitor 的会话封装。

    用法:
        with am.monitor_start() as monitor:
            # ... 跑压测 ...
            events = monitor.collect_events()
    """

    def __init__(self, device: Device):
        self.device = device
        self._process = None
        self._events: List[dict] = []
        self._start()

    def _start(self):
        """后台启动 am monitor"""
        import subprocess
        import threading
        import queue

        self._queue: queue.Queue = queue.Queue()

        def reader_thread():
            """在后台线程读 am monitor 输出"""
            try:
                # 用 adb shell 启动 monitor,持续输出
                cmd = ["adb", "-s", self.device.serial, "shell", "am", "monitor"]
                self._process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                for line in self._process.stdout:
                    self._queue.put(line.strip())
            except Exception as e:
                logger.exception("monitor reader thread failed: %s", e)

        self._thread = threading.Thread(target=reader_thread, daemon=True)
        self._thread.start()

    def collect_events(self, timeout_sec: float = 1.0) -> List[dict]:
        """
        收集当前所有可读的事件。

        每条事件格式:
          {'type': 'crash'|'anr'|'gc'|'lmk'|'died', 'raw': str, 'timestamp': float}
        """
        events = []
        while True:
            try:
                line = self._queue.get(timeout=timeout_sec)
            except Exception:
                break
            event = self._parse_event_line(line)
            if event:
                events.append(event)
                self._events.append(event)
        return events

    def _parse_event_line(self, line: str) -> Optional[dict]:
        """解析 am monitor 输出的一行"""
        import time as _time

        event = {"raw": line, "timestamp": _time.time()}

        # am monitor 典型输出:
        #   ** Activity Manager: GC: ...
        #   ** Activity Manager: Process com.example.app has died
        #   ** Activity Manager: ANR in com.example.app
        #   ** Activity Manager: Crash: ...
        #   ** Activity Manager: Low memory
        line_lower = line.lower()
        if "gc" in line_lower:
            event["type"] = "gc"
        elif "died" in line_lower or "kill" in line_lower:
            event["type"] = "died"
        elif "anr" in line_lower:
            event["type"] = "anr"
        elif "crash" in line_lower or "exception" in line_lower:
            event["type"] = "crash"
        elif "low memory" in line_lower:
            event["type"] = "lmk"
        else:
            return None

        return event

    def stop(self):
        """停止 monitor"""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
        self._process = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False