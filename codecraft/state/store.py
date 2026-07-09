from __future__ import annotations

import json
import logging
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from codecraft.config import settings

logger = logging.getLogger(__name__)

PROJECTS_DIR = Path(settings.data_dir) / "projects"
MANIFEST_FILE = "codecraft.json"


class ProjectStore:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or PROJECTS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, description: str = "", workdir: Optional[str] = None) -> dict[str, Any]:
        slug = self._slugify(name)
        project_dir = Path(workdir) if workdir else (self.base_dir / slug)

        if project_dir.exists() and list(project_dir.iterdir()):
            raise FileExistsError(f"Project directory already exists: {project_dir}")

        project_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "name": name,
            "slug": slug,
            "description": description,
            "version": "0.1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "created",
            "phases_completed": [],
            "artifacts": {},
            "agent_outputs": {},
            "total_tokens": 0,
            "total_cost": 0.0,
            "errors": [],
            "mode": "pipeline",
        }

        manifest_path = project_dir / MANIFEST_FILE
        manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Created project: {name} at {project_dir}")

        return manifest

    def load(self, project_path: str) -> dict[str, Any]:
        path = Path(project_path)
        if not path.is_dir():
            raise FileNotFoundError(f"Project directory not found: {path}")

        manifest_path = path / MANIFEST_FILE
        if not manifest_path.exists():
            dirs = list(path.iterdir())
            if dirs:
                return {
                    "name": path.name,
                    "slug": path.name,
                    "description": "",
                    "version": "0.1.0",
                    "created_at": "",
                    "updated_at": "",
                    "status": "unknown",
                    "phases_completed": [],
                    "artifacts": {},
                    "agent_outputs": {},
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "errors": [],
                    "mode": "pipeline",
                    "_path": str(path),
                }
            raise FileNotFoundError(f"Not a CodeCraft project: {path}")

        manifest = json.loads(manifest_path.read_text())
        manifest["_path"] = str(path)
        return manifest

    def save(self, project_path: str, manifest: dict[str, Any]) -> None:
        path = Path(project_path)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest.pop("_path", None)

        manifest_path = path / MANIFEST_FILE
        manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Saved project manifest: {manifest_path}")

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for entry in self.base_dir.iterdir():
            if entry.is_dir():
                manifest_path = entry / MANIFEST_FILE
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text())
                        manifest["_path"] = str(entry)
                        projects.append(manifest)
                    except Exception:
                        pass
        projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
        return projects

    def export_project(self, project_path: str, output_path: Optional[str] = None) -> str:
        path = Path(project_path)
        if not path.is_dir():
            raise FileNotFoundError(f"Project not found: {path}")

        output = Path(output_path or f"{path.name}.codecraft.tar.gz")
        with tarfile.open(output, "w:gz") as tar:
            for f in path.rglob("*"):
                if "__pycache__" in f.parts or ".venv" in f.parts or "node_modules" in f.parts:
                    continue
                if f.is_file():
                    arcname = f.relative_to(path.parent)
                    tar.add(f, arcname=arcname)

        logger.info(f"Exported project to: {output}")
        return str(output)

    def import_project(self, archive_path: str, output_dir: Optional[str] = None) -> dict[str, Any]:
        archive = Path(archive_path)
        if not archive.exists():
            raise FileNotFoundError(f"Archive not found: {archive}")

        if output_dir:
            dest = Path(output_dir)
        else:
            dest = self.base_dir / archive.stem.replace(".codecraft", "").replace(".tar", "")

        dest.mkdir(parents=True, exist_ok=True)
        if list(dest.iterdir()):
            raise FileExistsError(f"Output directory not empty: {dest}")

        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(path=dest.parent)

        manifest_path = dest / MANIFEST_FILE
        if manifest_path.exists():
            return json.loads(manifest_path.read_text())

        return {"name": dest.name, "slug": dest.name, "status": "imported", "_path": str(dest)}

    def delete(self, project_path: str) -> None:
        path = Path(project_path)
        if path.is_dir():
            shutil.rmtree(path)
            logger.info(f"Deleted project: {path}")
        elif path.is_file():
            path.unlink()
            logger.info(f"Deleted file: {path}")

    @staticmethod
    def _slugify(name: str) -> str:
        import re
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug[:50].strip("-")


project_store = ProjectStore()
