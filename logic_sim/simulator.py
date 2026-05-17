from __future__ import annotations

from logic_sim.drawing import GRID_SIZE, pin_positions
from logic_sim.model import Circuit, CustomComponent, GATE_TYPES, Part


def evaluate_gate(gate_type: str, inputs: dict[str, bool]) -> bool:
    if gate_type == "AND":
        return inputs.get("a", False) and inputs.get("b", False)
    if gate_type == "OR":
        return inputs.get("a", False) or inputs.get("b", False)
    if gate_type == "NOT":
        return not inputs.get("in", False)
    if gate_type == "NAND":
        return not (inputs.get("a", False) and inputs.get("b", False))
    if gate_type == "NOR":
        return not (inputs.get("a", False) or inputs.get("b", False))
    if gate_type == "XOR":
        return inputs.get("a", False) != inputs.get("b", False)
    raise ValueError(f"Unknown gate type: {gate_type}")


def step_circuit(circuit: Circuit) -> None:
    _apply_input_patterns(circuit)
    _settle_circuit(circuit)
    circuit.time_step += 1


def _apply_input_patterns(circuit: Circuit) -> None:
    for part in circuit.parts.values():
        if part.type == "Input Pin" and part.pattern:
            index = circuit.time_step % len(part.pattern)
            part.state = part.pattern[index]


def _settle_circuit(circuit: Circuit) -> None:
    limit = max(4, len(circuit.parts) + len(circuit.wires) + len(circuit.free_wires) + 4)
    for _ in range(limit):
        changed = _simulate_once(circuit)
        if not changed:
            break


def _simulate_once(circuit: Circuit) -> bool:
    changed = False

    for wire in circuit.wires:
        source = circuit.part(wire.source_part)
        signal = _output_value(source, wire.source_pin)
        if wire.signal != signal:
            wire.signal = signal
            changed = True

    free_wire_inputs, free_wire_changed = _update_free_wire_signals(circuit)
    changed = changed or free_wire_changed
    inputs_by_part = _collect_inputs(circuit)
    _merge_inputs(inputs_by_part, free_wire_inputs)

    for part in circuit.parts.values():
        inputs = inputs_by_part.get(part.id, {})
        if part.type in {"Switch", "Input Pin"}:
            continue
        if part.type in {"LED", "Output Pin"}:
            next_state = inputs.get("in", False)
            if part.state != next_state:
                part.state = next_state
                changed = True
        elif part.type in GATE_TYPES:
            next_state = evaluate_gate(part.type, inputs)
            if part.state != next_state:
                part.state = next_state
                changed = True
        elif part.type == "CUSTOM":
            next_values = _evaluate_custom_part(part, inputs, circuit)
            if part.values != next_values:
                part.values = next_values
                changed = True

    return changed


def _update_free_wire_signals(circuit: Circuit) -> tuple[dict[str, dict[str, bool]], bool]:
    if not circuit.free_wires:
        return {}, False

    wire_points = [_points_touched_by_path(wire.points) for wire in circuit.free_wires]
    wire_nodes = [set(wire.points) for wire in circuit.free_wires]
    parent = list(range(len(circuit.free_wires)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for index, points in enumerate(wire_points):
        for other_index in range(index):
            if _wires_share_node(
                wire_nodes[index],
                points,
                wire_nodes[other_index],
                wire_points[other_index],
            ):
                union(index, other_index)

    nets: dict[int, dict[str, object]] = {}
    for index, points in enumerate(wire_points):
        root = find(index)
        net = nets.setdefault(root, {"indexes": [], "points": set()})
        net["indexes"].append(index)
        net["points"].update(points)

    pin_entries = []
    for part in circuit.parts.values():
        for pin_name, (x, y, kind) in pin_positions(
            part,
            circuit.custom_components,
        ).items():
            pin_entries.append((part, pin_name, kind, (x, y)))

    changed = False
    inputs: dict[str, dict[str, bool]] = {}
    for net in nets.values():
        points = net["points"]
        signal = any(
            _output_value(part, pin_name)
            for part, pin_name, kind, position in pin_entries
            if kind == "output" and position in points
        )
        for index in net["indexes"]:
            wire = circuit.free_wires[index]
            if wire.signal != signal:
                wire.signal = signal
                changed = True
        for part, pin_name, kind, position in pin_entries:
            if kind != "input" or position not in points:
                continue
            part_inputs = inputs.setdefault(part.id, {})
            part_inputs[pin_name] = part_inputs.get(pin_name, False) or signal

    return inputs, changed


def _wires_share_node(
    left_nodes: set[tuple[int, int]],
    left_points: set[tuple[int, int]],
    right_nodes: set[tuple[int, int]],
    right_points: set[tuple[int, int]],
) -> bool:
    return bool((left_nodes & right_points) or (right_nodes & left_points))


def _collect_inputs(circuit: Circuit) -> dict[str, dict[str, bool]]:
    inputs: dict[str, dict[str, bool]] = {}
    for wire in circuit.wires:
        target_inputs = inputs.setdefault(wire.target_part, {})
        target_inputs[wire.target_pin] = wire.signal
    return inputs


def _merge_inputs(
    inputs: dict[str, dict[str, bool]],
    extra_inputs: dict[str, dict[str, bool]],
) -> None:
    for part_id, pins in extra_inputs.items():
        target_inputs = inputs.setdefault(part_id, {})
        for pin_name, signal in pins.items():
            target_inputs[pin_name] = target_inputs.get(pin_name, False) or signal


def _output_value(part: Part, pin: str) -> bool:
    if part.type in {"Switch", "Input Pin"}:
        return part.state
    if part.type in GATE_TYPES:
        return part.state
    if part.type == "CUSTOM":
        return part.values.get(pin, False)
    return False


def _evaluate_custom_part(
    part: Part,
    inputs: dict[str, bool],
    parent_circuit: Circuit,
) -> dict[str, bool]:
    component = parent_circuit.custom_components.get(part.custom_type or "")
    if component is None:
        return {}
    return evaluate_custom_component(component, inputs)


def evaluate_custom_component(
    component: CustomComponent,
    input_values: dict[str, bool],
) -> dict[str, bool]:
    circuit = component.circuit.copy()

    for part in circuit.parts.values():
        if part.type == "Input Pin":
            name = part.label.strip() or part.id
            part.state = input_values.get(name, False)

    _settle_circuit(circuit)

    outputs: dict[str, bool] = {}
    for part in circuit.parts.values():
        if part.type == "Output Pin":
            name = part.label.strip() or part.id
            outputs[name] = part.state
    return {name: outputs.get(name, False) for name in component.output_names}


def _points_touched_by_path(points: list[tuple[int, int]]) -> set[tuple[int, int]]:
    touched: set[tuple[int, int]] = set()
    for start, end in zip(points, points[1:]):
        x1, y1 = start
        x2, y2 = end
        if x1 == x2:
            step = _path_step(y1, y2)
            for y in range(y1, y2 + step, step):
                touched.add((x1, y))
        elif y1 == y2:
            step = _path_step(x1, x2)
            for x in range(x1, x2 + step, step):
                touched.add((x, y1))
    return touched


def _path_step(start: int, end: int) -> int:
    if end >= start:
        return GRID_SIZE if (end - start) % GRID_SIZE == 0 else 1
    return -GRID_SIZE if (start - end) % GRID_SIZE == 0 else -1
