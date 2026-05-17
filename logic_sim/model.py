from __future__ import annotations

from dataclasses import dataclass, field


GATE_TYPES = {"AND", "OR", "NOT", "NAND", "NOR", "XOR"}
SOURCE_TYPES = {"Switch", "Input Pin"}
SINK_TYPES = {"LED", "Output Pin"}
BUILTIN_PART_TYPES = SOURCE_TYPES | SINK_TYPES | GATE_TYPES


@dataclass
class Part:
    id: str
    type: str
    x: int
    y: int
    state: bool = False
    label: str = ""
    custom_type: str | None = None
    values: dict[str, bool] = field(default_factory=dict)
    pattern: list[bool] = field(default_factory=list)
    show_pattern: bool = True

    @property
    def name(self) -> str:
        if self.type == "CUSTOM":
            return self.custom_type or "Custom"
        return self.label or self.type

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "state": self.state,
            "label": self.label,
            "custom_type": self.custom_type,
            "values": dict(self.values),
            "pattern": list(self.pattern),
            "show_pattern": self.show_pattern,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Part":
        return cls(
            id=data["id"],
            type=data["type"],
            x=int(data["x"]),
            y=int(data["y"]),
            state=bool(data.get("state", False)),
            label=data.get("label", ""),
            custom_type=data.get("custom_type"),
            values={key: bool(value) for key, value in data.get("values", {}).items()},
            pattern=[bool(value) for value in data.get("pattern", [])],
            show_pattern=bool(data.get("show_pattern", True)),
        )


@dataclass
class Wire:
    id: str
    source_part: str
    source_pin: str
    target_part: str
    target_pin: str
    signal: bool = False
    color: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_part": self.source_part,
            "source_pin": self.source_pin,
            "target_part": self.target_part,
            "target_pin": self.target_pin,
            "signal": self.signal,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wire":
        return cls(
            id=data["id"],
            source_part=data["source_part"],
            source_pin=data["source_pin"],
            target_part=data["target_part"],
            target_pin=data["target_pin"],
            signal=bool(data.get("signal", False)),
            color=data.get("color", ""),
        )


@dataclass
class FreeWire:
    id: str
    points: list[tuple[int, int]]
    signal: bool = False
    color: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "points": [[x, y] for x, y in self.points],
            "signal": self.signal,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FreeWire":
        return cls(
            id=data["id"],
            points=[(int(x), int(y)) for x, y in data.get("points", [])],
            signal=bool(data.get("signal", False)),
            color=data.get("color", ""),
        )


@dataclass
class CustomComponent:
    name: str
    circuit: "Circuit"
    input_names: list[str]
    output_names: list[str]
    width: int = 0
    height: int = 0
    input_locations: dict[str, tuple[int, int]] = field(default_factory=dict)
    output_locations: dict[str, tuple[int, int]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "circuit": self.circuit.to_dict(include_components=True),
            "input_names": list(self.input_names),
            "output_names": list(self.output_names),
            "width": self.width,
            "height": self.height,
            "input_locations": {
                name: [x, y] for name, (x, y) in self.input_locations.items()
            },
            "output_locations": {
                name: [x, y] for name, (x, y) in self.output_locations.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CustomComponent":
        return cls(
            name=data["name"],
            circuit=Circuit.from_dict(data["circuit"]),
            input_names=list(data["input_names"]),
            output_names=list(data["output_names"]),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            input_locations=_locations_from_dict(data.get("input_locations", {})),
            output_locations=_locations_from_dict(data.get("output_locations", {})),
        )


@dataclass
class Circuit:
    parts: dict[str, Part] = field(default_factory=dict)
    wires: list[Wire] = field(default_factory=list)
    free_wires: list[FreeWire] = field(default_factory=list)
    custom_components: dict[str, CustomComponent] = field(default_factory=dict)
    next_part_number: int = 1
    next_wire_number: int = 1
    time_step: int = 0

    def add_part(
        self,
        part_type: str,
        x: int,
        y: int,
        *,
        state: bool = False,
        label: str = "",
        custom_type: str | None = None,
        part_id: str | None = None,
        pattern: list[bool] | None = None,
    ) -> Part:
        if part_type != "CUSTOM" and part_type not in BUILTIN_PART_TYPES:
            raise ValueError(f"Unknown part type: {part_type}")
        if part_type == "CUSTOM" and not custom_type:
            raise ValueError("Custom parts need custom_type")

        new_id = part_id or self._next_part_id()
        part = Part(
            id=new_id,
            type=part_type,
            x=int(x),
            y=int(y),
            state=bool(state),
            label=label,
            custom_type=custom_type,
            pattern=[bool(value) for value in (pattern or [])],
        )
        self.parts[new_id] = part
        return part

    def add_wire(
        self,
        source_part: str,
        source_pin: str,
        target_part: str,
        target_pin: str,
        *,
        wire_id: str | None = None,
        signal: bool = False,
        color: str = "",
    ) -> Wire:
        if source_part not in self.parts:
            raise ValueError(f"Missing source part: {source_part}")
        if target_part not in self.parts:
            raise ValueError(f"Missing target part: {target_part}")
        wire = Wire(
            id=wire_id or self._next_wire_id(),
            source_part=source_part,
            source_pin=source_pin,
            target_part=target_part,
            target_pin=target_pin,
            signal=bool(signal),
            color=color,
        )
        self.wires.append(wire)
        return wire

    def add_free_wire(
        self,
        points: list[tuple[int, int]],
        *,
        wire_id: str | None = None,
        signal: bool = False,
        color: str = "",
    ) -> FreeWire:
        if len(points) < 2:
            raise ValueError("Free wires need at least two points")
        wire = FreeWire(
            id=wire_id or self._next_wire_id(),
            points=[(int(x), int(y)) for x, y in points],
            signal=bool(signal),
            color=color,
        )
        self.free_wires.append(wire)
        return wire

    def part(self, part_id: str) -> Part:
        return self.parts[part_id]

    def remove_part(self, part_id: str) -> None:
        self.parts.pop(part_id, None)
        self.wires = [
            wire
            for wire in self.wires
            if wire.source_part != part_id and wire.target_part != part_id
        ]

    def remove_wire(self, wire_id: str) -> None:
        self.wires = [wire for wire in self.wires if wire.id != wire_id]
        self.free_wires = [wire for wire in self.free_wires if wire.id != wire_id]

    def to_dict(self, *, include_components: bool = True) -> dict:
        data = {
            "parts": [part.to_dict() for part in self.parts.values()],
            "wires": [wire.to_dict() for wire in self.wires],
            "free_wires": [wire.to_dict() for wire in self.free_wires],
            "next_part_number": self.next_part_number,
            "next_wire_number": self.next_wire_number,
            "time_step": self.time_step,
        }
        if include_components:
            data["custom_components"] = {
                name: component.to_dict()
                for name, component in self.custom_components.items()
            }
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Circuit":
        circuit = cls()
        circuit.parts = {
            part.id: part for part in (Part.from_dict(item) for item in data.get("parts", []))
        }
        circuit.wires = [Wire.from_dict(item) for item in data.get("wires", [])]
        circuit.free_wires = [
            FreeWire.from_dict(item) for item in data.get("free_wires", [])
        ]
        circuit.next_part_number = int(data.get("next_part_number", 1))
        circuit.next_wire_number = int(data.get("next_wire_number", 1))
        circuit.time_step = int(data.get("time_step", 0))
        circuit.custom_components = {
            name: CustomComponent.from_dict(component_data)
            for name, component_data in data.get("custom_components", {}).items()
        }
        circuit._bump_counters_past_loaded_ids()
        return circuit

    def copy(self) -> "Circuit":
        return Circuit.from_dict(self.to_dict())

    def _next_part_id(self) -> str:
        while True:
            part_id = f"p{self.next_part_number}"
            self.next_part_number += 1
            if part_id not in self.parts:
                return part_id

    def _next_wire_id(self) -> str:
        existing = {wire.id for wire in self.wires} | {wire.id for wire in self.free_wires}
        while True:
            wire_id = f"w{self.next_wire_number}"
            self.next_wire_number += 1
            if wire_id not in existing:
                return wire_id

    def _bump_counters_past_loaded_ids(self) -> None:
        self.next_part_number = max(self.next_part_number, _next_number_after(self.parts))
        self.next_wire_number = max(
            self.next_wire_number,
            _next_number_after(
                {wire.id: wire for wire in self.wires + self.free_wires}
            ),
        )


def input_pins_for(part: Part, custom_components: dict[str, CustomComponent]) -> list[str]:
    if part.type in {"Switch", "Input Pin"}:
        return []
    if part.type in {"LED", "Output Pin", "NOT"}:
        return ["in"]
    if part.type in {"AND", "OR", "NAND", "NOR", "XOR"}:
        return ["a", "b"]
    if part.type == "CUSTOM":
        component = custom_components.get(part.custom_type or "")
        return list(component.input_names) if component else []
    return []


def output_pins_for(part: Part, custom_components: dict[str, CustomComponent]) -> list[str]:
    if part.type in {"Switch", "Input Pin"}:
        return ["out"]
    if part.type in GATE_TYPES:
        return ["out"]
    if part.type == "CUSTOM":
        component = custom_components.get(part.custom_type or "")
        return list(component.output_names) if component else []
    return []


def build_custom_component(
    name: str,
    circuit: Circuit,
    *,
    width: int | None = None,
    height: int | None = None,
    input_locations: dict[str, tuple[int, int]] | None = None,
    output_locations: dict[str, tuple[int, int]] | None = None,
) -> CustomComponent:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Custom component name is required")

    inputs = _ordered_interface_parts(circuit, "Input Pin")
    outputs = _ordered_interface_parts(circuit, "Output Pin")
    if not inputs or not outputs:
        raise ValueError("Custom components need at least one Input Pin and one Output Pin")

    input_names = [_interface_name(part) for part in inputs]
    output_names = [_interface_name(part) for part in outputs]
    _require_unique(input_names, "input")
    _require_unique(output_names, "output")

    component_circuit = circuit.copy()
    component_circuit.custom_components.pop(clean_name, None)
    component_width = int(width or 0)
    component_height = int(height or 0)
    saved_input_locations: dict[str, tuple[int, int]] = {}
    saved_output_locations: dict[str, tuple[int, int]] = {}
    if component_width > 0 and component_height > 0:
        if input_locations is not None or output_locations is not None:
            saved_input_locations = _clamped_locations(
                input_locations or {},
                input_names,
                component_width,
                component_height,
            )
            saved_output_locations = _clamped_locations(
                output_locations or {},
                output_names,
                component_width,
                component_height,
            )
        else:
            center_x, center_y = _interface_center(inputs + outputs)
            saved_input_locations = _interface_locations(
                inputs,
                input_names,
                component_width,
                component_height,
                center_x,
                center_y,
            )
            saved_output_locations = _interface_locations(
                outputs,
                output_names,
                component_width,
                component_height,
                center_x,
                center_y,
            )
    return CustomComponent(
        clean_name,
        component_circuit,
        input_names,
        output_names,
        width=component_width,
        height=component_height,
        input_locations=saved_input_locations,
        output_locations=saved_output_locations,
    )


def _ordered_interface_parts(circuit: Circuit, part_type: str) -> list[Part]:
    parts = [part for part in circuit.parts.values() if part.type == part_type]
    return sorted(parts, key=lambda part: (part.y, part.x, part.id))


def _interface_name(part: Part) -> str:
    return part.label.strip() or part.id


def _require_unique(names: list[str], kind: str) -> None:
    if len(names) != len(set(names)):
        raise ValueError(f"Custom component {kind} names must be unique")


def _interface_locations(
    parts: list[Part],
    names: list[str],
    width: int,
    height: int,
    center_x: int,
    center_y: int,
) -> dict[str, tuple[int, int]]:
    half_width = int(width / 2)
    half_height = int(height / 2)
    locations: dict[str, tuple[int, int]] = {}
    for part, name in zip(parts, names):
        x = max(-half_width, min(half_width, part.x - center_x))
        y = max(-half_height, min(half_height, part.y - center_y))
        locations[name] = (x, y)
    return locations


def _clamped_locations(
    locations: dict[str, tuple[int, int]],
    names: list[str],
    width: int,
    height: int,
) -> dict[str, tuple[int, int]]:
    half_width = int(width / 2)
    half_height = int(height / 2)
    result: dict[str, tuple[int, int]] = {}
    for name in names:
        x, y = locations.get(name, (0, 0))
        result[name] = (
            max(-half_width, min(half_width, int(x))),
            max(-half_height, min(half_height, int(y))),
        )
    return result


def _interface_center(parts: list[Part]) -> tuple[int, int]:
    return (
        int(sum(part.x for part in parts) / len(parts)),
        int(sum(part.y for part in parts) / len(parts)),
    )


def _locations_from_dict(data: dict) -> dict[str, tuple[int, int]]:
    return {
        name: (int(value[0]), int(value[1]))
        for name, value in data.items()
        if isinstance(value, list | tuple) and len(value) == 2
    }


def _next_number_after(items: dict[str, object]) -> int:
    highest = 0
    for item_id in items:
        if len(item_id) > 1 and item_id[0] in {"p", "w"} and item_id[1:].isdigit():
            highest = max(highest, int(item_id[1:]))
    return highest + 1
