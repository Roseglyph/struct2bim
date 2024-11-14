"""Project-local Blender discovery and isolated headless execution."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


class BlenderRunError(RuntimeError):
    """Raised when a Blender render process does not complete successfully."""


@dataclass(frozen=True)
class BlenderToolConfig:
    """Configuration for the repository-managed Blender executable."""

    executable: Path
    timeout_seconds: int = 300

    @classmethod
    def discover(cls, project_root: Path) -> "BlenderToolConfig":
        override = os.environ.get("STRUCT2BIM_BLENDER")
        candidates = [
            Path(override) if override else None,
            project_root / ".tools" / "blender" / "blender.exe",
            project_root / ".tools" / "blender-4.2.0-windows-x64" / "blender.exe",
        ]
        candidates.extend(sorted((project_root / ".tools").glob("blender-*/blender.exe")))
        for candidate in candidates:
            if candidate is not None and candidate.is_file():
                return cls(candidate.resolve())
        searched = ", ".join(str(path) for path in candidates if path is not None)
        raise FileNotFoundError(
            "Blender was not found. Set STRUCT2BIM_BLENDER or install the portable "
            f"tool under .tools/. Searched: {searched}"
        )


class BlenderRunner:
    """Run Blender scripts with an isolated factory configuration."""

    def __init__(self, config: BlenderToolConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root.resolve()

    def command(self, script: Path, arguments: Sequence[str]) -> list[str]:
        return [
            str(self.config.executable),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(script.resolve()),
            "--",
            *arguments,
        ]

    def run(
        self,
        script: Path,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if not script.is_file():
            raise FileNotFoundError(f"Blender script does not exist: {script}")
        env = os.environ.copy()
        env.update({"PYTHONHASHSEED": "0", "STRUCT2BIM_PROJECT_ROOT": str(self.project_root)})
        if environment:
            env.update(environment)
        result = subprocess.run(
            self.command(script, arguments),
            cwd=self.project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise BlenderRunError(f"Blender exited with code {result.returncode}: {detail}")
        return result

    def render_clean_drawing(
        self, scene_json: Path, output_png: Path, *, seed: int = 24017
    ) -> None:
        script = self.project_root / "blender" / "scripts" / "render_clean_drawing.py"
        self.run(
            script,
            ["--scene", str(scene_json.resolve()), "--output", str(output_png.resolve()), "--seed", str(seed)],
        )

    def render_ifc_manifest(
        self, manifest_json: Path, output_png: Path, *, seed: int = 24017
    ) -> None:
        script = self.project_root / "blender" / "scripts" / "render_ifc_manifest.py"
        self.run(
            script,
            [
                "--manifest",
                str(manifest_json.resolve()),
                "--output",
                str(output_png.resolve()),
                "--seed",
                str(seed),
            ],
        )
