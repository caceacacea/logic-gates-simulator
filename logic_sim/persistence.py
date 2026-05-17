from __future__ import annotations

import json
from pathlib import Path

from logic_sim.model import Circuit, CustomComponent


def save_circuit(circuit: Circuit, path: str | Path) -> None:
    _write_json(circuit.to_dict(), path)


def load_circuit(path: str | Path) -> Circuit:
    return Circuit.from_dict(_read_json(path))


def save_custom_component(component: CustomComponent, path: str | Path) -> None:
    _write_json(component.to_dict(), path)


def load_custom_component(path: str | Path) -> CustomComponent:
    return CustomComponent.from_dict(_read_json(path))


def component_folder(workspace_dir: str | Path) -> Path:
    return Path(workspace_dir) / "custom_components"


def workspace_circuit_path(workspace_dir: str | Path) -> Path:
    return Path(workspace_dir) / "workspace.circuit.json"


def save_custom_component_to_folder(
    component: CustomComponent,
    workspace_dir: str | Path,
) -> Path:
    folder = component_folder(workspace_dir)
    path = folder / f"{_safe_filename(component.name)}.component.json"
    save_custom_component(component, path)
    return path


def load_custom_components_from_folder(
    workspace_dir: str | Path,
) -> dict[str, CustomComponent]:
    folder = component_folder(workspace_dir)
    if not folder.exists():
        return {}
    components: dict[str, CustomComponent] = {}
    for path in sorted(folder.glob("*.component.json")):
        component = load_custom_component(path)
        components[component.name] = component
    return components


def _write_json(data: dict, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe_filename(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
    return cleaned.strip("._") or "component"
