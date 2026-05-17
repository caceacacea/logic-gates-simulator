from __future__ import annotations

from collections import deque
from urllib.parse import quote

from logic_sim.model import CustomComponent, FreeWire, Part, input_pins_for, output_pins_for


GRID_SIZE = 20
PIN_RADIUS = 5
CANVAS_BG = "#120b24"
GRID_COLOR = "#24143f"
GRID_STRONG_COLOR = "#35205f"
ON_COLOR = "#a3e635"
OFF_COLOR = "#6d5d91"
SELECTED_COLOR = "#facc15"
COMPONENT_FILL = "#241142"
COMPONENT_FILL_ACTIVE = "#3b1768"
COMPONENT_OUTLINE = "#8b5cf6"
COMPONENT_OUTLINE_SOFT = "#5b35a3"
TEXT_COLOR = "#f8f0ff"
PIN_INPUT_COLOR = "#fb7185"
PIN_OUTPUT_COLOR = "#22d3ee"
WIRE_COLOR = "#a855f7"
WIRE_PREVIEW_COLOR = "#f0abfc"
LED_ON_COLOR = "#fde047"
LED_OFF_COLOR = "#47385f"


def snap(value: int | float) -> int:
    return int((value + GRID_SIZE / 2) // GRID_SIZE) * GRID_SIZE


def wire_preview_points(
    start: tuple[int, int],
    end: tuple[int, int],
    blocked_points: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    if start[0] == end[0] or start[1] == end[1]:
        direct = [start, end]
    else:
        direct = [start, (end[0], start[1]), end]

    if not blocked_points:
        return direct

    blocked = set(blocked_points)
    blocked.discard(start)
    blocked.discard(end)
    if _path_is_clear(direct, blocked):
        return direct
    return _grid_route(start, end, blocked) or direct


def part_bounds(
    part: Part,
    custom_components: dict[str, CustomComponent],
) -> tuple[int, int, int, int]:
    width, height = _part_size(part, custom_components)
    return (
        int(part.x - width / 2),
        int(part.y - height / 2),
        int(part.x + width / 2),
        int(part.y + height / 2),
    )


def pin_positions(
    part: Part,
    custom_components: dict[str, CustomComponent],
) -> dict[str, tuple[int, int, str]]:
    if part.type == "CUSTOM":
        custom_positions = _custom_pin_positions(part, custom_components)
        if custom_positions:
            return custom_positions

    left, top, right, bottom = part_bounds(part, custom_components)
    center_y = int((top + bottom) / 2)
    inputs = input_pins_for(part, custom_components)
    outputs = output_pins_for(part, custom_components)
    input_x, output_x = _pin_edge_x_positions(part, left, right)
    positions: dict[str, tuple[int, int, str]] = {}

    for name, y_offset in zip(inputs, _pin_offsets(len(inputs))):
        positions[name] = (input_x, center_y + y_offset, "input")
    for name, y_offset in zip(outputs, _pin_offsets(len(outputs))):
        positions[name] = (output_x, center_y + y_offset, "output")
    return positions


def _pin_edge_x_positions(part: Part, left: int, right: int) -> tuple[int, int]:
    return snap(left), snap(right)


def draw_grid(canvas, width: int, height: int) -> None:
    for x in range(0, width + GRID_SIZE, GRID_SIZE):
        color = GRID_STRONG_COLOR if x % (GRID_SIZE * 5) == 0 else GRID_COLOR
        canvas.create_line(x, 0, x, height, fill=color, tags=("grid",))
    for y in range(0, height + GRID_SIZE, GRID_SIZE):
        color = GRID_STRONG_COLOR if y % (GRID_SIZE * 5) == 0 else GRID_COLOR
        canvas.create_line(0, y, width, y, fill=color, tags=("grid",))


def draw_wire(
    canvas,
    wire,
    source: Part,
    target: Part,
    custom_components: dict[str, CustomComponent],
    *,
    selected: bool = False,
    blocked_points: set[tuple[int, int]] | None = None,
) -> None:
    source_pins = pin_positions(source, custom_components)
    target_pins = pin_positions(target, custom_components)
    if wire.source_pin not in source_pins or wire.target_pin not in target_pins:
        return

    x1, y1, _ = source_pins[wire.source_pin]
    x2, y2, _ = target_pins[wire.target_pin]
    points = wire_preview_points((x1, y1), (x2, y2), blocked_points=blocked_points)
    flat_points = [coordinate for point in points for coordinate in point]
    color = _wire_color(wire, selected)
    canvas.create_line(
        *flat_points,
        fill=color,
        width=3 if selected else 2,
        capstyle="round",
        joinstyle="round",
        tags=("wire", f"wire:{wire.id}"),
    )


def draw_free_wire(canvas, wire: FreeWire, *, selected: bool = False) -> None:
    draw_wire_path(
        canvas,
        wire.points,
        selected=selected,
        color=_wire_color(wire, selected),
        tags=("wire", f"wire:{wire.id}", f"freewire:{wire.id}"),
    )


def draw_wire_preview(canvas, points: list[tuple[int, int]]) -> None:
    draw_wire_path(canvas, points, selected=True, tags=("wire_preview",))


def draw_wire_path(
    canvas,
    points: list[tuple[int, int]],
    *,
    selected: bool = False,
    color: str | None = None,
    tags: tuple[str, ...] = ("wire",),
) -> None:
    if len(points) < 2:
        return
    flat_points = [coordinate for point in points for coordinate in point]
    color = color or (WIRE_PREVIEW_COLOR if selected else WIRE_COLOR)
    canvas.create_line(
        *flat_points,
        fill=color,
        width=5 if selected else 4,
        capstyle="round",
        joinstyle="round",
        tags=tags,
    )
    for x, y in points:
        canvas.create_oval(
            x - PIN_RADIUS,
            y - PIN_RADIUS,
            x + PIN_RADIUS,
            y + PIN_RADIUS,
            fill=PIN_INPUT_COLOR,
            outline=PIN_INPUT_COLOR,
            width=1,
            tags=tags,
        )


def draw_part(
    canvas,
    part: Part,
    style: str,
    custom_components: dict[str, CustomComponent],
    *,
    selected: bool = False,
) -> None:
    if part.type == "CUSTOM":
        _draw_custom(canvas, part, custom_components, selected)
    elif part.type in {"Switch", "Input Pin"}:
        _draw_source(canvas, part, custom_components, selected)
    elif part.type in {"LED", "Output Pin"}:
        _draw_sink(canvas, part, custom_components, selected)
    elif style == "IEC":
        _draw_iec_gate(canvas, part, custom_components, selected)
    else:
        _draw_ansi_gate(canvas, part, custom_components, selected)

    _draw_pin_dots(canvas, part, custom_components)


def draw_preview_part(
    canvas,
    part: Part,
    style: str,
    custom_components: dict[str, CustomComponent],
) -> None:
    draw_part(canvas, part, style, custom_components)


def _draw_source(
    canvas,
    part: Part,
    custom_components: dict[str, CustomComponent],
    selected: bool,
) -> None:
    left, top, right, bottom = part_bounds(part, custom_components)
    outline = SELECTED_COLOR if selected else COMPONENT_OUTLINE
    fill = COMPONENT_FILL_ACTIVE if part.state else COMPONENT_FILL
    canvas.create_rectangle(
        left,
        top,
        right,
        bottom,
        fill=fill,
        outline=outline,
        width=2,
        tags=_part_tags(part),
    )
    label = part.label or ("IN" if part.type == "Input Pin" else "SW")
    state = "1" if part.state else "0"
    canvas.create_text(part.x, part.y - 7, text=label, fill=TEXT_COLOR, tags=_part_tags(part))
    canvas.create_text(part.x, part.y + 10, text=state, fill=TEXT_COLOR, tags=_part_tags(part))
    if part.type == "Input Pin" and part.pattern and part.show_pattern:
        _draw_pattern_dots(canvas, part, right + 18, part.y)


def _draw_sink(
    canvas,
    part: Part,
    custom_components: dict[str, CustomComponent],
    selected: bool,
) -> None:
    left, top, right, bottom = part_bounds(part, custom_components)
    outline = SELECTED_COLOR if selected else COMPONENT_OUTLINE
    if part.type == "LED":
        fill = LED_ON_COLOR if part.state else LED_OFF_COLOR
        canvas.create_oval(
            left + 10,
            top + 8,
            right - 10,
            bottom - 8,
            fill=fill,
            outline=outline,
            width=2,
            tags=_part_tags(part),
        )
        canvas.create_text(part.x, part.y, text="LED", fill=TEXT_COLOR, tags=_part_tags(part))
    else:
        fill = COMPONENT_FILL_ACTIVE if part.state else COMPONENT_FILL
        canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            fill=fill,
            outline=outline,
            width=2,
            tags=_part_tags(part),
        )
        label = part.label or "OUT"
        canvas.create_text(part.x, part.y - 7, text=label, fill=TEXT_COLOR, tags=_part_tags(part))
        canvas.create_text(
            part.x,
            part.y + 10,
            text="1" if part.state else "0",
            fill=TEXT_COLOR,
            tags=_part_tags(part),
        )


def _draw_custom(
    canvas,
    part: Part,
    custom_components: dict[str, CustomComponent],
    selected: bool,
) -> None:
    left, top, right, bottom = part_bounds(part, custom_components)
    outline = SELECTED_COLOR if selected else COMPONENT_OUTLINE
    canvas.create_rectangle(
        left,
        top,
        right,
        bottom,
        fill=COMPONENT_FILL,
        outline=outline,
        width=2,
        tags=_part_tags(part),
    )
    canvas.create_text(
        part.x,
        part.y,
        text=part.custom_type or "Custom",
        fill=TEXT_COLOR,
        tags=_part_tags(part),
    )


def _draw_iec_gate(
    canvas,
    part: Part,
    custom_components: dict[str, CustomComponent],
    selected: bool,
) -> None:
    left, top, right, bottom = part_bounds(part, custom_components)
    outline = SELECTED_COLOR if selected else COMPONENT_OUTLINE
    canvas.create_rectangle(
        left + 12,
        top,
        right - 12,
        bottom,
        fill=COMPONENT_FILL,
        outline=outline,
        width=2,
        tags=_part_tags(part),
    )
    text = {
        "AND": "&",
        "OR": ">=1",
        "NOT": "1",
        "NAND": "&",
        "NOR": ">=1",
        "XOR": "=1",
    }.get(part.type, part.type)
    canvas.create_text(part.x, part.y, text=text, fill=TEXT_COLOR, tags=_part_tags(part))
    if part.type in {"NOT", "NAND", "NOR"}:
        _draw_bubble(canvas, right - 7, part.y, _part_tags(part))


def _draw_ansi_gate(
    canvas,
    part: Part,
    custom_components: dict[str, CustomComponent],
    selected: bool,
) -> None:
    left, top, right, bottom = part_bounds(part, custom_components)
    outline = SELECTED_COLOR if selected else COMPONENT_OUTLINE
    tags = _part_tags(part)

    if part.type in {"AND", "NAND"}:
        body_left = left + 14
        body_right = right - 14
        canvas.create_rectangle(
            body_left,
            top,
            part.x,
            bottom,
            fill=COMPONENT_FILL,
            outline="",
            tags=tags,
        )
        arc_left = 2 * part.x - body_right
        canvas.create_arc(
            arc_left,
            top,
            body_right,
            bottom,
            start=-90,
            extent=180,
            style="pieslice",
            fill=COMPONENT_FILL,
            outline="",
            tags=tags,
        )
        canvas.create_line(body_left, top, body_left, bottom, fill=outline, width=2, tags=tags)
        canvas.create_line(body_left, top, part.x, top, fill=outline, width=2, tags=tags)
        canvas.create_line(body_left, bottom, part.x, bottom, fill=outline, width=2, tags=tags)
        canvas.create_arc(
            arc_left,
            top,
            body_right,
            bottom,
            start=-90,
            extent=180,
            style="arc",
            outline=outline,
            width=2,
            tags=tags,
        )
        if part.type == "NAND":
            _draw_bubble(canvas, right - 12, part.y, tags)
    elif part.type in {"OR", "NOR", "XOR"}:
        body_left = left + 10
        body_right = right - 14
        canvas.create_polygon(
            body_left,
            top,
            part.x + 8,
            top + 3,
            body_right,
            part.y,
            part.x + 8,
            bottom - 3,
            body_left,
            bottom,
            fill=COMPONENT_FILL,
            outline="",
            tags=tags,
        )
        canvas.create_line(
            body_left,
            top,
            part.x + 8,
            top + 3,
            body_right,
            part.y,
            part.x + 8,
            bottom - 3,
            body_left,
            bottom,
            smooth=True,
            fill=outline,
            width=2,
            tags=tags,
        )
        canvas.create_line(
            body_left,
            top,
            body_left + 18,
            part.y,
            body_left,
            bottom,
            smooth=True,
            fill=outline,
            width=2,
            tags=tags,
        )
        if part.type == "XOR":
            canvas.create_line(
                body_left - 8,
                top,
                body_left + 10,
                part.y,
                body_left - 8,
                bottom,
                smooth=True,
                fill=outline,
                width=2,
                tags=tags,
            )
        if part.type == "NOR":
            _draw_bubble(canvas, right - 12, part.y, tags)
    elif part.type == "NOT":
        canvas.create_polygon(
            left + 15,
            top,
            left + 15,
            bottom,
            right - 18,
            part.y,
            fill=COMPONENT_FILL,
            outline=outline,
            width=2,
            tags=tags,
        )
        _draw_bubble(canvas, right - 12, part.y, tags)


def _draw_pin_dots(
    canvas,
    part: Part,
    custom_components: dict[str, CustomComponent],
) -> None:
    for pin_name, (x, y, kind) in pin_positions(part, custom_components).items():
        color = PIN_OUTPUT_COLOR if kind == "output" else PIN_INPUT_COLOR
        canvas.create_oval(
            x - PIN_RADIUS,
            y - PIN_RADIUS,
            x + PIN_RADIUS,
            y + PIN_RADIUS,
            fill=color,
            outline=CANVAS_BG,
            width=1,
            tags=("pin", f"pin:{part.id}:{quote(pin_name, safe='')}:{kind}"),
        )


def _draw_bubble(canvas, x: int, y: int, tags: tuple[str, str]) -> None:
    canvas.create_oval(
        x - 5,
        y - 5,
        x + 5,
        y + 5,
        fill=COMPONENT_FILL,
        outline=COMPONENT_OUTLINE,
        width=2,
        tags=tags,
    )


def _wire_color(wire, selected: bool) -> str:
    if selected:
        return SELECTED_COLOR
    if getattr(wire, "color", ""):
        return wire.color
    return ON_COLOR if getattr(wire, "signal", False) else WIRE_COLOR


def _part_size(
    part: Part,
    custom_components: dict[str, CustomComponent],
) -> tuple[int, int]:
    if part.type == "CUSTOM":
        component = custom_components.get(part.custom_type or "")
        if component and component.width > 0 and component.height > 0:
            return component.width, component.height
        pin_count = 1
        if component:
            pin_count = max(len(component.input_names), len(component.output_names), 1)
        return 100, max(60, pin_count * 20 + 20)
    if part.type in {"Switch", "Input Pin", "Output Pin"}:
        return 40, 40
    if part.type == "LED":
        return 90, 50
    return 90, 60


def _pin_offsets(count: int) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [0]
    if count == 2:
        return [-GRID_SIZE, GRID_SIZE]
    start = -((count - 1) * 10)
    return [start + index * 20 for index in range(count)]


def _part_tags(part: Part) -> tuple[str, str]:
    return ("part", f"part:{part.id}")


def _custom_pin_positions(
    part: Part,
    custom_components: dict[str, CustomComponent],
) -> dict[str, tuple[int, int, str]]:
    component = custom_components.get(part.custom_type or "")
    if not component:
        return {}

    positions: dict[str, tuple[int, int, str]] = {}
    for name in component.input_names:
        if name in component.input_locations:
            x, y = component.input_locations[name]
            positions[name] = (part.x + x, part.y + y, "input")
    for name in component.output_names:
        if name in component.output_locations:
            x, y = component.output_locations[name]
            positions[name] = (part.x + x, part.y + y, "output")

    expected = len(component.input_names) + len(component.output_names)
    return positions if len(positions) == expected else {}


def pattern_dot_positions(part: Part) -> list[tuple[int, int]]:
    if not part.pattern or not part.show_pattern:
        return []
    left, _top, right, _bottom = part_bounds(part, {})
    start_x = right + 18
    return [(start_x + index * 18, part.y) for index, _value in enumerate(part.pattern)]


def _draw_pattern_dots(canvas, part: Part, start_x: int, y: int) -> None:
    for index, value in enumerate(part.pattern):
        x = start_x + index * 18
        fill = ON_COLOR if value else PIN_INPUT_COLOR
        canvas.create_oval(
            x - 7,
            y - 7,
            x + 7,
            y + 7,
            fill=fill,
            outline=CANVAS_BG,
            width=1,
            tags=(
                "pattern",
                f"pattern:{part.id}:",
                f"pattern:{part.id}:{index}",
            ),
        )


def _path_is_clear(
    points: list[tuple[int, int]],
    blocked: set[tuple[int, int]],
) -> bool:
    return not any(point in blocked for point in _points_touched_by_path(points))


def _grid_route(
    start: tuple[int, int],
    end: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> list[tuple[int, int]] | None:
    if start == end:
        return [start, end]

    all_x = [start[0], end[0], *(point[0] for point in blocked)]
    all_y = [start[1], end[1], *(point[1] for point in blocked)]
    margin = GRID_SIZE * 4
    min_x = min(all_x) - margin
    max_x = max(all_x) + margin
    min_y = min(all_y) - margin
    max_y = max(all_y) + margin

    queue = deque([start])
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    directions = (
        (GRID_SIZE, 0),
        (0, GRID_SIZE),
        (-GRID_SIZE, 0),
        (0, -GRID_SIZE),
    )

    while queue:
        current = queue.popleft()
        if current == end:
            return _compact_route(came_from, end)

        for dx, dy in directions:
            next_point = (current[0] + dx, current[1] + dy)
            if next_point in came_from:
                continue
            if not (min_x <= next_point[0] <= max_x and min_y <= next_point[1] <= max_y):
                continue
            if next_point in blocked:
                continue
            came_from[next_point] = current
            queue.append(next_point)

    return None


def _compact_route(
    came_from: dict[tuple[int, int], tuple[int, int] | None],
    end: tuple[int, int],
) -> list[tuple[int, int]]:
    route = []
    current: tuple[int, int] | None = end
    while current is not None:
        route.append(current)
        current = came_from[current]
    route.reverse()

    compact = [route[0]]
    for index in range(1, len(route) - 1):
        previous = compact[-1]
        current = route[index]
        following = route[index + 1]
        same_x = previous[0] == current[0] == following[0]
        same_y = previous[1] == current[1] == following[1]
        if not (same_x or same_y):
            compact.append(current)
    compact.append(route[-1])
    return compact


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
