"""
amlib.artifact - 现场保留(trace/heap/tombstone/logcat/dumpsys)

提供三段式现场保留的封装:
  - collect_profile: 性能 trace
  - collect_heap: 内存 heap
  - collect_full: 三段式保留(profile + heap + logcat + dumpsys + anr)
  - collect_anr_traces: ANR traces 文件
  - collect_tombstones: native crash tombstone 文件
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from . import utils
from .am import AM
from .device import Device

logger = logging.getLogger(__name__)


class ArtifactCollector:
    """现场保留收集器,所有产物自动归档到 output_dir"""

    def __init__(self, device: Device, output_dir: str | Path = "./reports"):
        self.device = device
        self.output_dir = Path(output_dir)
        self.am = AM(device)

    def _create_scene_dir(self, scene: str) -> Path:
        """创建本次归档目录: output_dir/<timestamp>/<scene>/"""
        scene_dir = self.output_dir / utils.timestamp_str() / scene
        scene_dir.mkdir(parents=True, exist_ok=True)
        return scene_dir

    # ==================== 单项保留 ====================

    def collect_profile(
        self,
        pid: int,
        duration_sec: int,
        scene: str = "profile",
    ) -> Path:
        """
        采 profile 一段,归档到 scene_dir/trace.trace。

        Returns:
            trace 文件路径
        """
        scene_dir = self._create_scene_dir(scene)

        # 启动 profile
        self.am.profile_start(pid, "/data/local/tmp/trace.trace")

        # 等
        time.sleep(duration_sec)

        # 停止,自动 pull 到当前目录
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(scene_dir)
            self.am.profile_stop(pid)
        finally:
            os.chdir(original_cwd)
        time.sleep(2)

        trace_file = scene_dir / "trace.trace"
        if not trace_file.exists():
            # 兜底:手动 pull
            self.device.pull("/data/local/tmp/trace.trace", trace_file)

        # 写元信息
        self._write_meta(scene_dir, {"type": "profile", "duration_sec": duration_sec, "pid": pid})
        return trace_file

    def collect_heap(self, pid: int, scene: str = "heap") -> Path:
        """
        触发 dumpheap,归档到 scene_dir/heap.hprof。
        """
        scene_dir = self._create_scene_dir(scene)
        heap_file = scene_dir / "heap.hprof"

        # dumpheap
        self.am.dumpheap(pid, "/data/local/tmp/heap.hprof")

        # pull
        if not self.device.pull("/data/local/tmp/heap.hprof", heap_file, timeout=120):
            raise IOError(f"pull heap failed: {heap_file}")

        self._write_meta(scene_dir, {"type": "heap", "pid": pid})
        return heap_file

    def collect_logcat(self, scene: str = "logcat", tail_lines: int = 5000) -> Path:
        """
        拉 logcat(全设备或指定 PID),归档到 scene_dir/logcat.txt。

        注意:必须在事件触发**之前**就拉一份,否则 logcat 被覆盖就丢了。
        """
        scene_dir = self._create_scene_dir(scene)
        logcat_file = scene_dir / "logcat.txt"

        # 用 logcat -d 拉最近 N 行
        cmd = f"logcat -d -t {tail_lines}"
        output = self.device.shell(cmd, timeout=30)
        logcat_file.write_text(output, encoding="utf-8", errors="replace")

        self._write_meta(scene_dir, {"type": "logcat", "tail_lines": tail_lines})
        return logcat_file

    def collect_anr_traces(self, scene: str = "anr") -> Path:
        """
        拉 /data/anr/traces.txt,归档到 scene_dir/。

        Returns:
            归档目录路径(含 traces.txt)
        """
        scene_dir = self._create_scene_dir(scene)

        # 列出 /data/anr/ 下所有 traces 文件
        anr_dir = "/data/anr/"
        output = self.device.shell(f"ls -la {anr_dir}", timeout=10)

        # 拉最新一个(按时间排序)
        import re
        files = re.findall(r"(\S+traces\S*)", output)
        for fname in files[-3:]:  # 拉最近 3 个
            remote = f"{anr_dir}{fname}"
            local = scene_dir / fname
            self.device.pull(remote, local, timeout=30)

        # 拉一份 system_server_anr.log(如果有)
        self.device.shell("ls /data/anr/", timeout=10)
        self.device.pull("/data/anr/", scene_dir, timeout=60)

        self._write_meta(scene_dir, {"type": "anr"})
        return scene_dir

    def collect_tombstones(self, scene: str = "tombstone") -> Path:
        """
        拉 /data/tombstones/,归档。

        tombstone 是 native crash 的现场,详见 02 篇 §4.4。
        """
        scene_dir = self._create_scene_dir(scene)

        # tombstone 文件通常 root 才有权限拉,先用 shell ls 确认
        output = self.device.shell("ls -la /data/tombstones/", timeout=10)
        tombstone_dir = scene_dir / "tombstones"
        tombstone_dir.mkdir(exist_ok=True)

        # 逐个 pull(避免一次性 pull 整个目录出错)
        import re
        files = re.findall(r"(tombstone_\d+)", output)
        for fname in files:
            self.device.pull(
                f"/data/tombstones/{fname}",
                tombstone_dir / fname,
                timeout=30,
            )

        self._write_meta(scene_dir, {"type": "tombstone", "files": files})
        return scene_dir

    def collect_dumpsys(self, scene: str = "dumpsys", services: Optional[list] = None) -> Path:
        """
        拉 dumpsys 输出(默认 meminfo + activity + cpuinfo)。

        Args:
            scene: 场景名
            services: 要 dump 的服务列表,默认 ['meminfo', 'activity', 'cpuinfo', 'gfxinfo']
        """
        scene_dir = self._create_scene_dir(scene)
        services = services or ["meminfo", "activity", "cpuinfo", "gfxinfo"]

        for svc in services:
            output = self.device.shell(f"dumpsys {svc}", timeout=30)
            (scene_dir / f"{svc}.txt").write_text(output, encoding="utf-8", errors="replace")

        self._write_meta(scene_dir, {"type": "dumpsys", "services": services})
        return scene_dir

    # ==================== 三段式现场保留 ====================

    def collect_full(
        self,
        pkg: str,
        scene: str = "full",
        include_profile: bool = False,
        include_heap: bool = True,
        include_dumpsys: bool = True,
        include_logcat: bool = True,
        include_anr: bool = False,
        include_tombstone: bool = False,
        profile_duration_sec: int = 30,
    ) -> Path:
        """
        三段式现场保留:trace + heap + 系统状态。

        详见 06 篇 §1.2 场景 1/2/3 的串联用法。

        Args:
            pkg: 目标包名
            scene: 场景描述(归档用)
            include_profile: 是否采 profile
            include_heap: 是否 dump heap
            include_dumpsys: 是否拉 dumpsys(meminfo/activity/cpuinfo/gfxinfo)
            include_logcat: 是否拉 logcat
            include_anr: 是否拉 anr traces(ANR 场景)
            include_tombstone: 是否拉 tombstone(native crash 场景)
            profile_duration_sec: profile 采样时长(仅 include_profile=True 时有效)

        Returns:
            归档目录路径,包含所有采集的现场文件
        """
        scene_dir = self._create_scene_dir(scene)

        # 写元信息(完整版)
        meta = {
            "type": "full",
            "scene": scene,
            "package": pkg,
            "device": self.device.get_device_info(),
            "timestamp": utils.timestamp_str(),
            "includes": {
                "profile": include_profile,
                "heap": include_heap,
                "dumpsys": include_dumpsys,
                "logcat": include_logcat,
                "anr": include_anr,
                "tombstone": include_tombstone,
            },
        }

        # 1. logcat(必须最先拉,避免被覆盖)
        if include_logcat:
            try:
                logcat = self.device.shell(f"logcat -d -t 5000", timeout=30)
                (scene_dir / "logcat.txt").write_text(logcat, encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning("logcat 拉取失败: %s", e)

        # 2. profile(可选)
        if include_profile:
            try:
                pid = self.am.get_pid(pkg)
                self.am.profile_start(pid, "/data/local/tmp/trace.trace")
                time.sleep(profile_duration_sec)
                import os
                original_cwd = os.getcwd()
                try:
                    os.chdir(scene_dir)
                    self.am.profile_stop(pid)
                finally:
                    os.chdir(original_cwd)
                time.sleep(2)
                if not (scene_dir / "trace.trace").exists():
                    self.device.pull("/data/local/tmp/trace.trace", scene_dir / "trace.trace")
                meta["trace_size"] = (scene_dir / "trace.trace").stat().st_size
            except Exception as e:
                logger.warning("profile 失败: %s", e)

        # 3. heap dump
        if include_heap:
            try:
                pid = self.am.get_pid(pkg)
                self.am.dumpheap(pid, "/data/local/tmp/heap.hprof")
                self.device.pull(
                    "/data/local/tmp/heap.hprof", scene_dir / "heap.hprof", timeout=120
                )
                meta["heap_size"] = (scene_dir / "heap.hprof").stat().st_size
            except Exception as e:
                logger.warning("heap dump 失败: %s", e)

        # 4. dumpsys
        if include_dumpsys:
            for svc in ["meminfo", "activity", "cpuinfo", "gfxinfo"]:
                try:
                    output = self.device.shell(f"dumpsys {svc}", timeout=30)
                    (scene_dir / f"dumpsys_{svc}.txt").write_text(
                        output, encoding="utf-8", errors="replace"
                    )
                except Exception as e:
                    logger.warning("dumpsys %s 失败: %s", svc, e)

        # 5. anr traces
        if include_anr:
            try:
                self.collect_anr_traces(scene=f"{scene}/anr")
            except Exception as e:
                logger.warning("anr 拉取失败: %s", e)

        # 6. tombstone
        if include_tombstone:
            try:
                self.collect_tombstones(scene=f"{scene}/tombstone")
            except Exception as e:
                logger.warning("tombstone 拉取失败: %s", e)

        # 写元信息
        self._write_meta(scene_dir, meta)

        # 写 README
        self._write_readme(scene_dir, meta)

        return scene_dir

    # ==================== 辅助 ====================

    def _write_meta(self, scene_dir: Path, meta: dict) -> None:
        meta_file = scene_dir / "meta.json"
        # 合并已有 meta
        if meta_file.exists():
            try:
                existing = json.loads(meta_file.read_text(encoding="utf-8"))
                existing.update(meta)
                meta = existing
            except Exception:
                pass
        meta_file.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

    def _write_readme(self, scene_dir: Path, meta: dict) -> None:
        readme = scene_dir / "README.md"
        lines = [
            f"# 现场保留 - {meta.get('scene', 'unknown')}",
            "",
            "## 概述",
            "",
            f"- 时间: `{meta.get('timestamp')}`",
            f"- 设备: `{meta.get('device', {}).get('serial')}`",
            f"- 包名: `{meta.get('package')}`",
            "",
            "## 包含现场",
            "",
        ]
        for key, val in meta.get("includes", {}).items():
            mark = "✅" if val else "❌"
            lines.append(f"- {mark} {key}")
        lines.extend(
            [
                "",
                "## 文件清单",
                "",
            ]
        )
        for f in sorted(scene_dir.iterdir()):
            if f.is_file():
                size = utils.bytes_to_human(f.stat().st_size)
                lines.append(f"- `{f.name}` ({size})")

        readme.write_text("\n".join(lines), encoding="utf-8")