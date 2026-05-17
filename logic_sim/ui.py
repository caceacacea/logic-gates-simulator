from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from urllib.parse import unquote

from logic_sim.drawing import (
    CANVAS_BG,
    GRID_SIZE,
    PIN_RADIUS,
    draw_free_wire,
    draw_grid,
    draw_part,
    draw_preview_part,
    draw_wire,
    draw_wire_preview,
    part_bounds,
    pattern_dot_positions,
    pin_positions,
    snap,
    wire_preview_points,
)
from logic_sim.model import Circuit, Part, build_custom_component
from logic_sim.persistence import (
    component_folder,
    load_circuit,
    load_custom_components_from_folder,
    save_circuit,
    save_custom_component,
    save_custom_component_to_folder,
    workspace_circuit_path,
)
from logic_sim.simulator import step_circuit
from logic_sim.undo import History


BUILTIN_TOOLS = [
    "Input Pin",
    "Output Pin",
    "LED",
    "AND",
    "OR",
    "NOT",
    "NAND",
    "NOR",
    "XOR",
]


class LogicSimulatorApp:
    def __init__(self, root: tk.Tk, workspace_dir: Path | None = None) -> None:
        self.root = root
        self.workspace_dir = workspace_dir
        self.circuit = Circuit()
        self.main_circuit = self.circuit
        self.component_circuit = Circuit(custom_components=self.circuit.custom_components)
        self.history = History()

        self.selected_tool: tuple[str, str] | None = None
        self.selected_part_id: str | None = None
        self.selected_wire_id: str | None = None
        self.pending_output: tuple[str, str] | None = None
        self.preview_part: Part | None = None
        self.wire_start: tuple[int, int] | None = None
        self.wire_preview: list[tuple[int, int]] | None = None
        self.input_wire_start: tuple[str, str] | None = None

        self.drag_part_id: str | None = None
        self.drag_started = False
        self.drag_last = (0, 0)
        self.drag_start_position = (0, 0)
        self.empty_wire_start: tuple[int, int] | None = None
        self.empty_wire_dragging = False
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0

        self.symbol_style = tk.StringVar(value="ANSI")
        self.custom_choice = tk.StringVar(value="")
        self.editor_mode = tk.StringVar(value="Main Circuit")
        self.signal_length = tk.IntVar(value=8)
        self.status_text = tk.StringVar(value="Choose a part, then click the workspace.")

        self.root.title("Logic Gate Simulator")
        self.root.geometry("1100x720")
        self._build_ui()
        self._load_workspace()
        self._update_custom_choices()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.redraw()

    def _build_ui(self) -> None:
        self._apply_theme()
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="Step", command=self.step).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Undo", command=self.undo).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Redo", command=self.redo).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Clear", command=self.clear_workspace).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Zoom In", command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Zoom Out", command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(top, text="Save", command=self.save).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Load", command=self.load).pack(side=tk.LEFT, padx=2)
        self.save_component_button = ttk.Button(
            top,
            text="Save Component",
            command=self.save_component,
            state="disabled",
        )
        self.save_component_button.pack(
            side=tk.LEFT,
            padx=2,
        )
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(top, text="Main Mode", command=self.enter_main_mode).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Custom Mode", command=self.enter_custom_mode).pack(
            side=tk.LEFT,
            padx=2,
        )
        ttk.Label(top, textvariable=self.editor_mode).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(top, text="Signal Len").pack(side=tk.LEFT, padx=(0, 4))
        tk.Spinbox(
            top,
            from_=1,
            to=64,
            width=4,
            textvariable=self.signal_length,
        ).pack(side=tk.LEFT)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(top, text="Symbol Style").pack(side=tk.LEFT, padx=(0, 4))
        style_box = ttk.Combobox(
            top,
            textvariable=self.symbol_style,
            values=["ANSI", "IEC"],
            width=8,
            state="readonly",
        )
        style_box.pack(side=tk.LEFT)
        style_box.bind("<<ComboboxSelected>>", lambda _event: self.redraw())

        body = ttk.Frame(self.root)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        tools = ttk.Frame(body, padding=(8, 6))
        tools.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(tools, text="Parts").pack(anchor=tk.W, pady=(0, 4))
        for part_type in BUILTIN_TOOLS:
            ttk.Button(
                tools,
                text=part_type,
                command=lambda value=part_type: self.choose_builtin(value),
                width=14,
            ).pack(fill=tk.X, pady=2)

        ttk.Separator(tools, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(tools, text="Custom").pack(anchor=tk.W, pady=(0, 4))
        self.custom_box = ttk.Combobox(
            tools,
            textvariable=self.custom_choice,
            width=15,
            state="disabled",
        )
        self.custom_box.pack(fill=tk.X, pady=2)
        self.place_custom_button = ttk.Button(
            tools,
            text="Place Custom",
            command=self.choose_custom,
            state="disabled",
        )
        self.place_custom_button.pack(fill=tk.X, pady=2)

        self.canvas = tk.Canvas(body, background=CANVAS_BG, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", self.on_canvas_leave)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Delete>", lambda _event: self.delete_selected())
        self.canvas.bind("<BackSpace>", lambda _event: self.delete_selected())
        self.canvas.bind("<Escape>", lambda _event: self.cancel_action())
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.root.bind("<KeyPress-w>", lambda _event: self.pan_view(0, -GRID_SIZE * 2))
        self.root.bind("<KeyPress-a>", lambda _event: self.pan_view(-GRID_SIZE * 2, 0))
        self.root.bind("<KeyPress-s>", lambda _event: self.pan_view(0, GRID_SIZE * 2))
        self.root.bind("<KeyPress-d>", lambda _event: self.pan_view(GRID_SIZE * 2, 0))

        status = ttk.Label(self.root, textvariable=self.status_text, padding=(8, 4))
        status.pack(side=tk.BOTTOM, fill=tk.X)

    def _apply_theme(self) -> None:
        self.root.configure(background="#120b24")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#120b24")
        style.configure("TLabel", background="#120b24", foreground="#f8f0ff")
        style.configure(
            "TButton",
            background="#3b1768",
            foreground="#f8f0ff",
            bordercolor="#8b5cf6",
            focusthickness=2,
            focuscolor="#c084fc",
            padding=(8, 4),
        )
        style.map(
            "TButton",
            background=[("active", "#6d28d9"), ("pressed", "#7c3aed")],
            foreground=[("disabled", "#7c6b9f")],
        )
        style.configure(
            "TCombobox",
            fieldbackground="#241142",
            background="#3b1768",
            foreground="#f8f0ff",
            arrowcolor="#f8f0ff",
        )

    def choose_builtin(self, part_type: str) -> None:
        self.selected_tool = ("builtin", part_type)
        self.pending_output = None
        self.wire_start = None
        self.wire_preview = None
        self.input_wire_start = None
        self.status_text.set(f"Click the workspace to place {part_type}.")

    def choose_wire(self) -> None:
        self.selected_tool = ("wire", "Wire")
        self.pending_output = None
        self.preview_part = None
        self.wire_start = None
        self.wire_preview = None
        self.input_wire_start = None
        self.status_text.set("Click the grid to start a wire.")

    def choose_custom(self) -> None:
        name = self.custom_choice.get()
        if not name:
            self.status_text.set("Save or load a circuit with a custom component first.")
            return
        self.selected_tool = ("custom", name)
        self.pending_output = None
        self.wire_start = None
        self.wire_preview = None
        self.input_wire_start = None
        self.status_text.set(f"Click the workspace to place {name}.")

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        view_width = int(self.canvas.winfo_width() / self.zoom)
        view_height = int(self.canvas.winfo_height() / self.zoom)
        width = max(view_width + self.pan_x + GRID_SIZE, 900)
        height = max(view_height + self.pan_y + GRID_SIZE, 600)
        draw_grid(self.canvas, width, height)

        for wire in self.circuit.free_wires:
            draw_free_wire(
                self.canvas,
                wire,
                selected=wire.id == self.selected_wire_id,
            )

        for wire in self.circuit.wires:
            source = self.circuit.parts.get(wire.source_part)
            target = self.circuit.parts.get(wire.target_part)
            if source and target:
                draw_wire(
                    self.canvas,
                    wire,
                    source,
                    target,
                    self.circuit.custom_components,
                    selected=wire.id == self.selected_wire_id,
                    blocked_points=self._blocked_wire_points(
                        ignore_wire_id=wire.id,
                    ),
                )

        for part in self.circuit.parts.values():
            draw_part(
                self.canvas,
                part,
                self.symbol_style.get(),
                self.circuit.custom_components,
                selected=part.id == self.selected_part_id,
            )

        if self.pending_output:
            self._draw_pending_output()

        if self.wire_preview:
            draw_wire_preview(self.canvas, self.wire_preview)

        if self.preview_part:
            draw_preview_part(
                self.canvas,
                self.preview_part,
                self.symbol_style.get(),
                self.circuit.custom_components,
            )

        if self.zoom != 1.0:
            self.canvas.move("all", -self.pan_x, -self.pan_y)
            self.canvas.scale("all", 0, 0, self.zoom, self.zoom)
        elif self.pan_x or self.pan_y:
            self.canvas.move("all", -self.pan_x, -self.pan_y)

    def on_canvas_click(self, event) -> None:
        self.canvas.focus_set()
        x, y = self._event_point(event)

        if self.selected_tool:
            if self.selected_tool[0] == "wire":
                self.place_wire_point(x, y)
            else:
                self.place_selected_tool(x, y)
            return

        tags = self._event_tags(event)
        pattern = self._pattern_from_tags(tags) or self._pattern_at_point(x, y)
        if pattern:
            self.toggle_pattern_value(*pattern)
            return

        pin = self._pin_at_point(x, y) or self._pin_from_tags(tags)
        if pin:
            if self.handle_pin_click(*pin):
                return
            self.start_free_wire_from_pin(pin[0], pin[1])
            return

        part_id = self._part_from_tags(tags)
        if part_id:
            self.selected_part_id = part_id
            self.selected_wire_id = None
            self.drag_part_id = part_id
            self.drag_started = False
            self.drag_last = (x, y)
            part = self.circuit.part(part_id)
            self.drag_start_position = (part.x, part.y)
            self.redraw()
            return

        wire_id = self._wire_from_tags(tags)
        if wire_id:
            node = self._free_wire_node_at_point(x, y)
            if node is not None:
                self.selected_part_id = None
                self.selected_wire_id = None
                self.pending_output = None
                self.empty_wire_start = node
                self.input_wire_start = None
                self.empty_wire_dragging = False
                self.wire_preview = [node, node]
                self.redraw()
                return
            self.selected_wire_id = wire_id
            self.selected_part_id = None
            self.redraw()
            return

        self.selected_part_id = None
        self.selected_wire_id = None
        self.pending_output = None
        self.empty_wire_start = (snap(x), snap(y))
        self.empty_wire_dragging = False
        self.redraw()

    def on_canvas_motion(self, event) -> None:
        if not self.selected_tool:
            if self.preview_part is not None:
                self.preview_part = None
                self.redraw()
            return

        x, y = self._event_point(event)
        if self.selected_tool[0] == "wire":
            point = (snap(x), snap(y))
            if self.wire_start:
                self.wire_preview = self._wire_path(self.wire_start, point)
            else:
                self.wire_preview = [point, point]
            self.redraw()
            return

        self.preview_part = make_preview_part(self.selected_tool, x, y)
        self.redraw()

    def on_canvas_press(self, event) -> None:
        self.canvas.focus_set()
        x, y = self._event_point(event)
        tags = self._event_tags(event)

        if _ctrl_pressed(event):
            wire_id = self._wire_from_tags(tags)
            if wire_id:
                self.change_wire_color(wire_id)
                return
            pattern = self._pattern_from_tags(tags) or self._pattern_at_point(x, y)
            if pattern:
                self.toggle_pattern_visibility(pattern[0])
                return
            part_id = self._part_from_tags(tags) or self._part_at_point(x, y)
            if part_id:
                part = self.circuit.parts.get(part_id)
                if part and part.type == "Input Pin" and part.pattern:
                    self.toggle_pattern_visibility(part_id)
                    return

        if not self.selected_tool and not self.pending_output:
            pin = self._pin_at_point(x, y)
            if pin and pin[2] == "input":
                self.start_free_wire_from_pin(pin[0], pin[1])
                return

        self.on_canvas_click(event)

    def on_canvas_leave(self, _event) -> None:
        if self.preview_part is None:
            if self.wire_preview is None:
                return
        self.preview_part = None
        self.wire_preview = None
        self.redraw()

    def on_right_click(self, _event) -> None:
        if (
            self.selected_tool
            or self.preview_part
            or self.wire_start
            or self.wire_preview
            or self.empty_wire_start
        ):
            self.selected_tool = None
            self.preview_part = None
            self.wire_start = None
            self.wire_preview = None
            self.input_wire_start = None
            self.empty_wire_start = None
            self.empty_wire_dragging = False
            self.status_text.set("Dropped current tool.")
            self.redraw()
            return

        tags = self._event_tags(_event)
        part_id = self._part_from_tags(tags)
        wire_id = self._wire_from_tags(tags)
        if part_id:
            self.history.capture(self.circuit)
            self.circuit.remove_part(part_id)
            self.status_text.set("Part deleted.")
        elif wire_id:
            self.history.capture(self.circuit)
            self.circuit.remove_wire(wire_id)
            self.status_text.set("Wire deleted.")
        else:
            return
        self.selected_part_id = None
        self.selected_wire_id = None
        self.redraw()

    def on_canvas_drag(self, event) -> None:
        if self.empty_wire_start is None and self.pending_output:
            if self._start_pending_output_wire_drag(event):
                return

        if self.empty_wire_start is not None:
            x, y = self._event_point(event)
            end = self._wire_drag_end(x, y)
            if end == self.empty_wire_start:
                return
            self.empty_wire_dragging = True
            self.wire_preview = self._wire_path(
                self.empty_wire_start,
                end,
                avoid_wires=self.input_wire_start is None,
            )
            self.status_text.set("Release to place wire.")
            self.redraw()
            return

        if not self.drag_part_id or self.drag_part_id not in self.circuit.parts:
            return

        x, y = self._event_point(event)
        dx = x - self.drag_last[0]
        dy = y - self.drag_last[1]
        if not self.drag_started and abs(dx) + abs(dy) < 3:
            return

        if not self.drag_started:
            self.history.capture(self.circuit)
            self.drag_started = True

        part = self.circuit.part(self.drag_part_id)
        part.x += dx
        part.y += dy
        self.drag_last = (x, y)
        self.redraw()

    def on_canvas_release(self, event) -> None:
        if self.empty_wire_start is not None:
            if self.empty_wire_dragging:
                x, y = self._event_point(event)
                end = self._wire_drag_end(x, y)
                target_pin = self._pin_at_point(x, y)
                if (
                    self.pending_output
                    and target_pin
                    and target_pin[2] == "input"
                    and self.handle_pin_click(*target_pin)
                ):
                    self.empty_wire_start = None
                    self.empty_wire_dragging = False
                    self.input_wire_start = None
                    self.wire_preview = None
                    self.pending_output = None
                    self.redraw()
                    return

                if target_pin and target_pin[2] == "output":
                    self.status_text.set("Start from an output and end at an input.")
                    self.empty_wire_start = None
                    self.empty_wire_dragging = False
                    self.input_wire_start = None
                    self.wire_preview = None
                    self.pending_output = None
                    self.redraw()
                    return

                points = self._wire_path(
                    self.empty_wire_start,
                    end,
                    avoid_wires=self.input_wire_start is None,
                )
                if points[0] != points[-1]:
                    self.history.capture(self.circuit)
                    self.circuit.add_free_wire(points)
                    self.status_text.set("Wire placed.")
            self.empty_wire_start = None
            self.empty_wire_dragging = False
            self.input_wire_start = None
            self.wire_preview = None
            self.pending_output = None
            self.redraw()
            return

        if not self.drag_part_id:
            return

        part = self.circuit.parts.get(self.drag_part_id)
        if part is None:
            self._reset_drag()
            return

        if self.drag_started:
            part.x = snap(part.x)
            part.y = snap(part.y)
            if self._part_overlaps_existing(part, ignore_part_id=part.id):
                part.x, part.y = self.drag_start_position
                self.status_text.set("Cannot move onto another component.")
            else:
                self.status_text.set(f"Moved {part.name}.")
        elif part.type in {"Switch", "Input Pin"}:
            self.history.capture(self.circuit)
            part.state = not part.state
            self.status_text.set(f"{part.name} is now {'1' if part.state else '0'}.")

        self._reset_drag()
        self.redraw()

    def place_selected_tool(self, x: int, y: int) -> None:
        if not self.selected_tool:
            return

        kind, value = self.selected_tool
        label = ""
        part_type = value
        custom_type = None

        if kind == "custom":
            part_type = "CUSTOM"
            custom_type = value
        elif value in {"Input Pin", "Output Pin"}:
            label = self._ask_pin_label(value)
        pattern: list[bool] | None = None
        if value == "Input Pin" and self.editor_mode.get() != "Custom Component":
            pattern = [False] * self._signal_length()

        new_part = Part(
            "__preview__",
            part_type,
            snap(x),
            snap(y),
            label=label,
            custom_type=custom_type,
            pattern=pattern,
        )
        if self._part_overlaps_existing(new_part):
            self.status_text.set("Cannot place component on another component.")
            self.preview_part = new_part
            self.redraw()
            return

        self.history.capture(self.circuit)
        self.circuit.add_part(
            part_type,
            new_part.x,
            new_part.y,
            label=label,
            custom_type=custom_type,
            pattern=pattern,
        )
        self.status_text.set(f"Placed {value}.")
        self.preview_part = make_preview_part(self.selected_tool, x, y)
        self.redraw()

    def place_wire_point(self, x: int, y: int) -> None:
        point = (snap(x), snap(y))
        if self.wire_start is None:
            self.wire_start = point
            self.wire_preview = [point, point]
            self.status_text.set("Move the cursor, then click to finish the wire.")
            self.redraw()
            return

        points = self._wire_path(self.wire_start, point)
        if points[0] == points[-1]:
            self.status_text.set("Wire needs a start and end point.")
            return

        self.history.capture(self.circuit)
        self.circuit.add_free_wire(points)
        self.wire_start = point
        self.wire_preview = [point, point]
        self.status_text.set("Wire placed. Click another point to continue, or right-click to drop.")
        self.redraw()

    def handle_pin_click(self, part_id: str, pin_name: str, kind: str) -> bool:
        if kind == "output":
            self.pending_output = (part_id, pin_name)
            part = self.circuit.part(part_id)
            self.status_text.set(f"Selected output {part.name}.{pin_name}; click an input pin.")
            self.redraw()
            return True

        if kind == "input" and self.pending_output:
            source_part, source_pin = self.pending_output
            if source_part == part_id:
                self.status_text.set("Cannot connect a part to itself.")
                return True

            self.history.capture(self.circuit)
            self.circuit.wires = [
                wire
                for wire in self.circuit.wires
                if not (wire.target_part == part_id and wire.target_pin == pin_name)
            ]
            self.circuit.add_wire(source_part, source_pin, part_id, pin_name)
            self.pending_output = None
            self.status_text.set("Wire connected. Press Step to update signals.")
            self.redraw()
            return True

        self.status_text.set("Drag from the input pin to place a free wire.")
        return False

    def start_free_wire_from_pin(self, part_id: str, pin_name: str) -> None:
        part = self.circuit.parts.get(part_id)
        if part is None:
            return
        pins = pin_positions(part, self.circuit.custom_components)
        if pin_name not in pins:
            return
        x, y, _kind = pins[pin_name]
        self.selected_part_id = None
        self.selected_wire_id = None
        self.empty_wire_start = (x, y)
        self.input_wire_start = (part_id, pin_name)
        self.empty_wire_dragging = False
        self.wire_preview = [self.empty_wire_start, self.empty_wire_start]
        self.redraw()

    def toggle_pattern_visibility(self, part_id: str) -> None:
        if self._toggle_input_pattern_visibility(part_id):
            self.redraw()

    def _toggle_input_pattern_visibility(self, part_id: str) -> bool:
        part = self.circuit.parts.get(part_id)
        if not part or part.type != "Input Pin" or not part.pattern:
            return False
        self.history.capture(self.circuit)
        part.show_pattern = not part.show_pattern
        state = "shown" if part.show_pattern else "hidden"
        self.status_text.set(f"{part.name} signal dots {state}.")
        return True

    def _start_pending_output_wire_drag(self, event) -> bool:
        if not self.pending_output:
            return False
        part_id, pin_name = self.pending_output
        part = self.circuit.parts.get(part_id)
        if part is None:
            self.pending_output = None
            return False
        pins = pin_positions(part, self.circuit.custom_components)
        if pin_name not in pins:
            self.pending_output = None
            return False

        x, y = self._event_point(event)
        start_x, start_y, _kind = pins[pin_name]
        start = (start_x, start_y)
        self.empty_wire_start = start
        self.input_wire_start = None
        end = self._wire_drag_end(x, y)
        if end == start:
            self.empty_wire_start = None
            return False

        self.selected_part_id = None
        self.selected_wire_id = None
        self.empty_wire_dragging = True
        self.wire_preview = self._wire_path(start, end)
        self.status_text.set("Release to place wire.")
        self.redraw()
        return True

    def toggle_pattern_value(self, part_id: str, index: int) -> None:
        part = self.circuit.parts.get(part_id)
        if not part or index < 0 or index >= len(part.pattern):
            return
        self.history.capture(self.circuit)
        part.pattern[index] = not part.pattern[index]
        current_index = self.circuit.time_step % len(part.pattern)
        part.state = part.pattern[current_index]
        self.status_text.set(f"{part.name} value {index + 1} is now {'1' if part.pattern[index] else '0'}.")
        self.redraw()

    def change_wire_color(self, wire_id: str) -> None:
        color = self._ask_wire_color(wire_id)
        if not color:
            return
        wire = self._wire_by_id(wire_id)
        if wire is None:
            return
        self.history.capture(self.circuit)
        wire.color = color
        self.status_text.set(f"Wire color set to {color}.")
        self.redraw()

    def step(self) -> None:
        step_circuit(self.circuit)
        self.status_text.set("Signals updated.")
        self.redraw()

    def zoom_in(self) -> None:
        self.zoom = min(2.0, round(self.zoom + 0.1, 2))
        self.status_text.set(f"Zoom: {int(self.zoom * 100)}%")
        self.redraw()

    def zoom_out(self) -> None:
        self.zoom = max(0.4, round(self.zoom - 0.1, 2))
        self.status_text.set(f"Zoom: {int(self.zoom * 100)}%")
        self.redraw()

    def on_mouse_wheel(self, event) -> None:
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self.zoom_in()
        elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            self.zoom_out()

    def pan_view(self, dx: int, dy: int) -> None:
        self.pan_x = max(0, self.pan_x + dx)
        self.pan_y = max(0, self.pan_y + dy)
        self.status_text.set(f"View: x={self.pan_x}, y={self.pan_y}")
        self.redraw()

    def enter_custom_mode(self) -> None:
        if self.editor_mode.get() == "Custom Component":
            return
        self.main_circuit = self.circuit
        self.component_circuit.custom_components.update(self.main_circuit.custom_components)
        self.circuit = self.component_circuit
        self.editor_mode.set("Custom Component")
        self.save_component_button.configure(state="normal")
        self._after_circuit_replaced("Custom component mode.")

    def enter_main_mode(self) -> None:
        if self.editor_mode.get() == "Main Circuit":
            return
        self.component_circuit = self.circuit
        self.main_circuit.custom_components.update(self.component_circuit.custom_components)
        self.circuit = self.main_circuit
        self.editor_mode.set("Main Circuit")
        self.save_component_button.configure(state="disabled")
        self._after_circuit_replaced("Main circuit mode.")

    def undo(self) -> None:
        previous = self.history.undo(self.circuit)
        if previous is None:
            self.status_text.set("Nothing to undo.")
            return
        self.circuit = previous
        self._after_circuit_replaced("Undo.")

    def redo(self) -> None:
        next_circuit = self.history.redo(self.circuit)
        if next_circuit is None:
            self.status_text.set("Nothing to redo.")
            return
        self.circuit = next_circuit
        self._after_circuit_replaced("Redo.")

    def clear_workspace(self) -> None:
        if not self.circuit.parts and not self.circuit.wires and not self.circuit.free_wires:
            return
        if not messagebox.askyesno("Clear workspace", "Remove all parts and wires?"):
            return
        self.history.capture(self.circuit)
        self.circuit = Circuit(custom_components=dict(self.circuit.custom_components))
        self._after_circuit_replaced("Workspace cleared.")

    def delete_selected(self) -> None:
        if self.selected_part_id:
            self.history.capture(self.circuit)
            self.circuit.remove_part(self.selected_part_id)
            self.status_text.set("Part deleted.")
        elif self.selected_wire_id:
            self.history.capture(self.circuit)
            self.circuit.remove_wire(self.selected_wire_id)
            self.status_text.set("Wire deleted.")
        else:
            return

        self.selected_part_id = None
        self.selected_wire_id = None
        self.pending_output = None
        self.redraw()

    def save(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save circuit",
            defaultextension=".json",
            filetypes=[("Circuit JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_circuit(self.circuit, path)
        except OSError as error:
            messagebox.showerror("Save failed", str(error))
            return
        self.status_text.set(f"Saved {Path(path).name}.")

    def load(self) -> None:
        path = filedialog.askopenfilename(
            title="Load circuit",
            filetypes=[("Circuit JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            loaded = load_circuit(path)
        except (OSError, ValueError, KeyError) as error:
            messagebox.showerror("Load failed", str(error))
            return

        self.history.capture(self.circuit)
        self.circuit = loaded
        self._after_circuit_replaced(f"Loaded {Path(path).name}.")

    def save_component(self) -> None:
        if self.editor_mode.get() != "Custom Component":
            messagebox.showinfo(
                "Custom Component Mode",
                "Switch to Custom Mode before saving a custom component.",
                parent=self.root,
            )
            return
        name = simpledialog.askstring(
            "Save Component",
            "Component name:",
            parent=self.root,
        )
        if not name:
            return
        layout = self._ask_component_layout(name)
        if layout is None:
            return
        try:
            component = build_custom_component(
                name,
                self.circuit,
                width=layout["width"],
                height=layout["height"],
                input_locations=layout["input_locations"],
                output_locations=layout["output_locations"],
            )
        except ValueError as error:
            messagebox.showerror("Cannot save component", str(error))
            return

        try:
            if self.workspace_dir:
                path = save_custom_component_to_folder(component, self.workspace_dir)
            else:
                path = filedialog.asksaveasfilename(
                    title="Save custom component",
                    defaultextension=".component.json",
                    initialfile=f"{_safe_filename(component.name)}.component.json",
                    filetypes=[("Component JSON", "*.json"), ("All files", "*.*")],
                )
                if not path:
                    return
                save_custom_component(component, path)
        except OSError as error:
            messagebox.showerror("Save failed", str(error))
            return

        self.history.capture(self.circuit)
        self.circuit.custom_components[component.name] = component
        self.main_circuit.custom_components[component.name] = component
        self.component_circuit.custom_components[component.name] = component
        self._update_custom_choices()
        self.status_text.set(f"Saved custom component {component.name} to {Path(path).parent}.")

    def cancel_action(self) -> None:
        self.selected_tool = None
        self.pending_output = None
        self.preview_part = None
        self.wire_start = None
        self.wire_preview = None
        self.input_wire_start = None
        self.empty_wire_start = None
        self.empty_wire_dragging = False
        self.status_text.set("Cancelled current action.")
        self.redraw()

    def _after_circuit_replaced(self, status: str) -> None:
        if self.editor_mode.get() == "Custom Component":
            self.component_circuit = self.circuit
        else:
            self.main_circuit = self.circuit
        self.selected_tool = None
        self.selected_part_id = None
        self.selected_wire_id = None
        self.pending_output = None
        self.preview_part = None
        self.wire_start = None
        self.wire_preview = None
        self.input_wire_start = None
        self.empty_wire_start = None
        self.empty_wire_dragging = False
        self._reset_drag()
        self._update_custom_choices()
        self.status_text.set(status)
        self.redraw()

    def _update_custom_choices(self) -> None:
        names = sorted(self.circuit.custom_components)
        self.custom_box.configure(values=names)
        if names:
            if self.custom_choice.get() not in names:
                self.custom_choice.set(names[0])
            self.custom_box.configure(state="readonly")
            self.place_custom_button.configure(state="normal")
        else:
            self.custom_choice.set("")
            self.custom_box.configure(state="disabled")
            self.place_custom_button.configure(state="disabled")

    def _load_workspace(self) -> None:
        if not self.workspace_dir:
            return
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        component_folder(self.workspace_dir).mkdir(parents=True, exist_ok=True)
        self.circuit.custom_components.update(
            load_custom_components_from_folder(self.workspace_dir)
        )
        path = workspace_circuit_path(self.workspace_dir)
        if path.exists():
            try:
                loaded = load_circuit(path)
            except (OSError, ValueError, KeyError) as error:
                messagebox.showerror("Workspace load failed", str(error))
                return
            loaded.custom_components.update(self.circuit.custom_components)
            self.circuit = loaded
            self.main_circuit = self.circuit
            self.component_circuit.custom_components.update(self.circuit.custom_components)
            self.history.clear()

    def on_close(self) -> None:
        if not self.workspace_dir:
            self.root.destroy()
            return

        answer = messagebox.askyesnocancel(
            "Save workspace",
            "Save the current workspace before closing?",
            parent=self.root,
        )
        if answer is None:
            return
        if answer:
            try:
                save_circuit(self.circuit, workspace_circuit_path(self.workspace_dir))
            except OSError as error:
                messagebox.showerror("Export failed", str(error))
                return
        self.root.destroy()

    def _draw_pending_output(self) -> None:
        if not self.pending_output:
            return
        part_id, pin_name = self.pending_output
        part = self.circuit.parts.get(part_id)
        if not part:
            return
        pins = pin_positions(part, self.circuit.custom_components)
        if pin_name not in pins:
            return
        x, y, _kind = pins[pin_name]
        self.canvas.create_oval(
            x - PIN_RADIUS - 4,
            y - PIN_RADIUS - 4,
            x + PIN_RADIUS + 4,
            y + PIN_RADIUS + 4,
            outline="#f97316",
            width=2,
            tags=("pending",),
        )

    def _ask_pin_label(self, part_type: str) -> str:
        default = self._default_pin_label(part_type)
        label = simpledialog.askstring(
            f"{part_type} label",
            "Label:",
            initialvalue=default,
            parent=self.root,
        )
        if label is None:
            return default
        return label.strip() or default

    def _default_pin_label(self, part_type: str) -> str:
        prefix = "IN" if part_type == "Input Pin" else "OUT"
        count = sum(1 for part in self.circuit.parts.values() if part.type == part_type)
        return f"{prefix}{count + 1}"

    def _ask_input_pattern_length(self) -> int:
        length = simpledialog.askinteger(
            "Input signal length",
            "How many signal values?",
            initialvalue=8,
            minvalue=1,
            maxvalue=64,
            parent=self.root,
        )
        return int(length or 8)

    def _signal_length(self) -> int:
        try:
            return max(1, min(64, int(self.signal_length.get())))
        except tk.TclError:
            return 8

    def _ask_component_layout(self, name: str) -> dict | None:
        dialog = ComponentLayoutDialog(self.root, name, self.circuit)
        return dialog.result

    def _ask_wire_color(self, wire_id: str) -> str:
        wire = self._wire_by_id(wire_id)
        current_color = getattr(wire, "color", "") or "#a855f7"
        _rgb, color = colorchooser.askcolor(
            color=current_color,
            title="Wire color",
            parent=self.root,
        )
        return color or ""

    def _current_tags(self) -> tuple[str, ...]:
        current = self.canvas.find_withtag("current")
        if not current:
            return ()
        return self.canvas.gettags(current[0])

    def _event_tags(self, event) -> tuple[str, ...]:
        tags = self._current_tags()
        if tags:
            return tags
        item_ids = self.canvas.find_overlapping(
            event.x - PIN_RADIUS * 2,
            event.y - PIN_RADIUS * 2,
            event.x + PIN_RADIUS * 2,
            event.y + PIN_RADIUS * 2,
        )
        if not item_ids:
            return ()
        return self.canvas.gettags(item_ids[-1])

    def _pin_from_tags(self, tags: tuple[str, ...]) -> tuple[str, str, str] | None:
        for tag in tags:
            if tag.startswith("pin:"):
                parts = tag.split(":", 3)
                if len(parts) == 4:
                    return parts[1], unquote(parts[2]), parts[3]
        return None

    def _part_from_tags(self, tags: tuple[str, ...]) -> str | None:
        for tag in tags:
            if tag.startswith("part:"):
                return tag.split(":", 1)[1]
        return None

    def _wire_from_tags(self, tags: tuple[str, ...]) -> str | None:
        for tag in tags:
            if tag.startswith("wire:"):
                return tag.split(":", 1)[1]
        return None

    def _pattern_from_tags(self, tags: tuple[str, ...]) -> tuple[str, int] | None:
        for tag in tags:
            if tag.startswith("pattern:"):
                parts = tag.split(":")
                if len(parts) == 3 and parts[2].isdigit():
                    return parts[1], int(parts[2])
        return None

    def _pattern_at_point(self, x: int, y: int) -> tuple[str, int] | None:
        for part in self.circuit.parts.values():
            if part.type != "Input Pin":
                continue
            for index, (dot_x, dot_y) in enumerate(pattern_dot_positions(part)):
                if abs(dot_x - x) <= PIN_RADIUS * 2 and abs(dot_y - y) <= PIN_RADIUS * 2:
                    return part.id, index
        return None

    def _pin_at_point(self, x: int, y: int) -> tuple[str, str, str] | None:
        for part in self.circuit.parts.values():
            for pin_name, (pin_x, pin_y, kind) in pin_positions(
                part,
                self.circuit.custom_components,
            ).items():
                if abs(pin_x - x) <= PIN_RADIUS * 2 and abs(pin_y - y) <= PIN_RADIUS * 2:
                    return part.id, pin_name, kind
        return None

    def _part_at_point(self, x: int, y: int) -> str | None:
        for part in self.circuit.parts.values():
            left, top, right, bottom = part_bounds(part, self.circuit.custom_components)
            if left <= x <= right and top <= y <= bottom:
                return part.id
        return None

    def _free_wire_node_at_point(self, x: int, y: int) -> tuple[int, int] | None:
        for free_wire in self.circuit.free_wires:
            for node_x, node_y in free_wire.points:
                if abs(node_x - x) <= PIN_RADIUS * 2 and abs(node_y - y) <= PIN_RADIUS * 2:
                    return node_x, node_y
        return None

    def _wire_drag_end(self, x: int, y: int) -> tuple[int, int]:
        node = self._free_wire_node_at_point(x, y)
        if node is not None:
            return node
        pin = self._pin_at_point(x, y)
        if pin is not None:
            part = self.circuit.parts.get(pin[0])
            if part is not None:
                pins = pin_positions(part, self.circuit.custom_components)
                if pin[1] in pins:
                    pin_x, pin_y, _kind = pins[pin[1]]
                    return pin_x, pin_y

        point = (snap(x), snap(y))
        if not (self.input_wire_start or self.pending_output) or self.empty_wire_start is None:
            return point

        start_x, start_y = self.empty_wire_start
        if abs(y - start_y) <= PIN_RADIUS * 2:
            return snap(x), start_y
        if abs(x - start_x) <= PIN_RADIUS * 2:
            return start_x, snap(y)
        return point

    def _wire_by_id(self, wire_id: str):
        for wire in self.circuit.wires:
            if wire.id == wire_id:
                return wire
        for wire in self.circuit.free_wires:
            if wire.id == wire_id:
                return wire
        return None

    def _reset_drag(self) -> None:
        self.drag_part_id = None
        self.drag_started = False
        self.drag_last = (0, 0)
        self.drag_start_position = (0, 0)

    def _event_point(self, event) -> tuple[int, int]:
        return int(event.x / self.zoom + self.pan_x), int(event.y / self.zoom + self.pan_y)

    def _wire_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        avoid_wires: bool = True,
    ) -> list[tuple[int, int]]:
        return wire_preview_points(
            start,
            end,
            blocked_points=self._blocked_wire_points(include_wires=avoid_wires),
        )

    def _blocked_wire_points(
        self,
        *,
        ignore_wire_id: str | None = None,
        ignore_part_ids: set[str] | None = None,
        include_wires: bool = True,
    ) -> set[tuple[int, int]]:
        ignore_part_ids = ignore_part_ids or set()
        blocked: set[tuple[int, int]] = set()

        for part in self.circuit.parts.values():
            if part.id not in ignore_part_ids:
                blocked.update(self._part_grid_points(part))

        if include_wires:
            for free_wire in self.circuit.free_wires:
                if free_wire.id != ignore_wire_id:
                    blocked.update(free_wire.points)

            for wire in self.circuit.wires:
                if wire.id == ignore_wire_id:
                    continue
                source = self.circuit.parts.get(wire.source_part)
                target = self.circuit.parts.get(wire.target_part)
                if not source or not target:
                    continue
                source_pins = pin_positions(source, self.circuit.custom_components)
                target_pins = pin_positions(target, self.circuit.custom_components)
                if wire.source_pin not in source_pins or wire.target_pin not in target_pins:
                    continue
                x1, y1, _source_kind = source_pins[wire.source_pin]
                x2, y2, _target_kind = target_pins[wire.target_pin]
                blocked.update(wire_preview_points((x1, y1), (x2, y2)))

        return blocked

    def _part_grid_points(self, part: Part) -> set[tuple[int, int]]:
        left, top, right, bottom = part_bounds(part, self.circuit.custom_components)
        points: set[tuple[int, int]] = set()
        for x in range(_ceil_to_grid(left), _floor_to_grid(right) + GRID_SIZE, GRID_SIZE):
            for y in range(_ceil_to_grid(top), _floor_to_grid(bottom) + GRID_SIZE, GRID_SIZE):
                points.add((x, y))
        return points

    def _part_overlaps_existing(
        self,
        part: Part,
        *,
        ignore_part_id: str | None = None,
    ) -> bool:
        target_points = self._part_grid_points(part)
        for existing in self.circuit.parts.values():
            if existing.id == ignore_part_id:
                continue
            if target_points & self._part_grid_points(existing):
                return True
        return False


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return cleaned or "component"


def _floor_to_grid(value: int) -> int:
    return (value // GRID_SIZE) * GRID_SIZE


def _ceil_to_grid(value: int) -> int:
    return ((value + GRID_SIZE - 1) // GRID_SIZE) * GRID_SIZE


def _ctrl_pressed(event) -> bool:
    return bool(getattr(event, "state", 0) & 0x0004)


def make_preview_part(selected_tool: tuple[str, str], x: int, y: int) -> Part:
    kind, value = selected_tool
    if kind == "custom":
        return Part("__preview__", "CUSTOM", snap(x), snap(y), custom_type=value)
    return Part("__preview__", value, snap(x), snap(y))


class ComponentLayoutDialog:
    def __init__(
        self,
        root: tk.Tk,
        name: str,
        circuit: Circuit,
        *,
        auto_show: bool = True,
    ) -> None:
        self.root = root
        self.name = name
        self.circuit = circuit
        self.result: dict | None = None
        self.inputs = _ordered_interface_parts(circuit, "Input Pin")
        self.outputs = _ordered_interface_parts(circuit, "Output Pin")
        self.input_names = [_interface_name(part) for part in self.inputs]
        self.output_names = [_interface_name(part) for part in self.outputs]
        self.pin_locations = self._default_locations()
        self.drag_pin: str | None = None

        self.window = tk.Toplevel(root)
        self.window.title("Custom Component Layout")
        self.window.resizable(False, False)
        if not auto_show:
            self.window.withdraw()

        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(frame)
        controls.pack(side=tk.TOP, fill=tk.X)
        self.width_var = tk.IntVar(value=120)
        self.height_var = tk.IntVar(value=80)
        ttk.Label(controls, text="Width").pack(side=tk.LEFT)
        tk.Spinbox(
            controls,
            from_=40,
            to=400,
            width=5,
            textvariable=self.width_var,
            command=self.redraw,
        ).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(controls, text="Height").pack(side=tk.LEFT)
        tk.Spinbox(
            controls,
            from_=40,
            to=300,
            width=5,
            textvariable=self.height_var,
            command=self.redraw,
        ).pack(side=tk.LEFT, padx=(4, 12))

        self.canvas = tk.Canvas(
            frame,
            width=420,
            height=300,
            background=CANVAS_BG,
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.TOP, pady=10)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        buttons = ttk.Frame(frame)
        buttons.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(buttons, text="Save Layout", command=self.accept).pack(
            side=tk.RIGHT,
            padx=4,
        )
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)

        self.redraw()
        if auto_show:
            self.window.grab_set()
            root.wait_window(self.window)

    def _default_locations(self) -> dict[str, tuple[int, int]]:
        parts = self.inputs + self.outputs
        if not parts:
            return {}
        center_x = int(sum(part.x for part in parts) / len(parts))
        center_y = int(sum(part.y for part in parts) / len(parts))
        locations: dict[str, tuple[int, int]] = {}
        for part in self.inputs + self.outputs:
            locations[_interface_name(part)] = (
                int(part.x - center_x),
                int(part.y - center_y),
            )
        return locations

    def redraw(self) -> None:
        self.canvas.delete("all")
        center_x, center_y = 210, 150
        width = self._width()
        height = self._height()
        left = center_x - int(width / 2)
        top = center_y - int(height / 2)
        right = center_x + int(width / 2)
        bottom = center_y + int(height / 2)
        self.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            fill="#241142",
            outline="#8b5cf6",
            width=2,
        )
        self.canvas.create_text(center_x, center_y, text=self.name, fill="#f8f0ff")
        for name in self.input_names + self.output_names:
            x, y = self.pin_locations.get(name, (0, 0))
            canvas_x = center_x + x
            canvas_y = center_y + y
            fill = "#fb7185" if name in self.input_names else "#22d3ee"
            self.canvas.create_oval(
                canvas_x - 7,
                canvas_y - 7,
                canvas_x + 7,
                canvas_y + 7,
                fill=fill,
                outline=CANVAS_BG,
                tags=(f"layout_pin:{name}",),
            )
            self.canvas.create_text(
                canvas_x,
                canvas_y - 16,
                text=name,
                fill="#f8f0ff",
            )

    def on_press(self, event) -> None:
        current = self.canvas.find_withtag("current")
        if not current:
            return
        for tag in self.canvas.gettags(current[0]):
            if tag.startswith("layout_pin:"):
                self.drag_pin = tag.split(":", 1)[1]
                return

    def on_drag(self, event) -> None:
        if not self.drag_pin:
            return
        half_width = int(self._width() / 2)
        half_height = int(self._height() / 2)
        x = max(-half_width, min(half_width, int(event.x - 210)))
        y = max(-half_height, min(half_height, int(event.y - 150)))
        self.pin_locations[self.drag_pin] = (x, y)
        self.redraw()

    def on_release(self, _event) -> None:
        self.drag_pin = None

    def accept(self) -> None:
        self.result = {
            "width": self._width(),
            "height": self._height(),
            "input_locations": {
                name: self.pin_locations.get(name, (0, 0))
                for name in self.input_names
            },
            "output_locations": {
                name: self.pin_locations.get(name, (0, 0))
                for name in self.output_names
            },
        }
        self.window.destroy()

    def cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def _width(self) -> int:
        return max(40, min(400, int(self.width_var.get())))

    def _height(self) -> int:
        return max(40, min(300, int(self.height_var.get())))


def _ordered_interface_parts(circuit: Circuit, part_type: str) -> list[Part]:
    parts = [part for part in circuit.parts.values() if part.type == part_type]
    return sorted(parts, key=lambda part: (part.y, part.x, part.id))


def _interface_name(part: Part) -> str:
    return part.label.strip() or part.id


class WorkspaceDialog:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.result: Path | None = None
        self.settings = _load_workspace_settings()
        recent = self.settings.get("recent_workspaces", [])
        default = self.settings.get("default_workspace") or (
            str(Path.cwd() / "workspace")
        )

        self.window = tk.Toplevel(root)
        self.window.title("Logic Gate Simulator Launcher")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.grab_set()

        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Select a directory as workspace", font=("", 10, "bold")).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=(0, 6),
        )
        ttk.Label(
            frame,
            text="The simulator stores circuit exports and custom components here.",
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))

        self.workspace_choice = tk.StringVar(value=default)
        values = list(dict.fromkeys([default] + recent))
        self.combo = ttk.Combobox(
            frame,
            textvariable=self.workspace_choice,
            values=values,
            width=68,
        )
        self.combo.grid(row=2, column=0, columnspan=2, sticky=tk.EW)
        ttk.Button(frame, text="Browse...", command=self.browse).grid(
            row=2,
            column=2,
            padx=(8, 0),
        )

        self.use_default = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Use this as the default and do not ask again",
            variable=self.use_default,
        ).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(8, 12))

        ttk.Label(frame, text="Recent Workspaces").grid(
            row=4,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=(0, 4),
        )
        recent_text = "\n".join(recent[:5]) if recent else "No recent workspaces yet."
        ttk.Label(frame, text=recent_text).grid(row=5, column=0, columnspan=3, sticky=tk.W)

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky=tk.E, pady=(16, 0))
        ttk.Button(buttons, text="Launch", command=self.launch).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side=tk.LEFT)

    def browse(self) -> None:
        path = filedialog.askdirectory(
            title="Select workspace",
            initialdir=self.workspace_choice.get() or str(Path.cwd()),
            parent=self.window,
        )
        if path:
            self.workspace_choice.set(path)

    def launch(self) -> None:
        text = self.workspace_choice.get().strip()
        if not text:
            messagebox.showerror("Workspace required", "Choose a workspace folder.")
            return
        workspace = Path(text)
        workspace.mkdir(parents=True, exist_ok=True)
        self.result = workspace
        _save_recent_workspace(
            workspace,
            use_default=self.use_default.get(),
            settings=self.settings,
        )
        self.window.destroy()

    def cancel(self) -> None:
        self.result = None
        self.window.destroy()


def choose_workspace(root: tk.Tk) -> Path | None:
    settings = _load_workspace_settings()
    if settings.get("skip_launcher") and settings.get("default_workspace"):
        workspace = Path(settings["default_workspace"])
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace
    dialog = WorkspaceDialog(root)
    root.wait_window(dialog.window)
    return dialog.result


def _workspace_settings_path() -> Path:
    return Path.home() / ".logic_gate_simulator_workspaces.json"


def _load_workspace_settings() -> dict:
    path = _workspace_settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_recent_workspace(
    workspace: Path,
    *,
    use_default: bool,
    settings: dict,
) -> None:
    recent = [str(workspace)]
    recent.extend(
        item
        for item in settings.get("recent_workspaces", [])
        if item != str(workspace)
    )
    data = {"recent_workspaces": recent[:10]}
    if use_default:
        data["default_workspace"] = str(workspace)
        data["skip_launcher"] = True
    elif settings.get("default_workspace"):
        data["default_workspace"] = settings["default_workspace"]
        data["skip_launcher"] = settings.get("skip_launcher", False)
    _workspace_settings_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_app() -> None:
    root = tk.Tk()
    root.withdraw()
    workspace = choose_workspace(root)
    if workspace is None:
        root.destroy()
        return
    root.deiconify()
    LogicSimulatorApp(root, workspace)
    root.mainloop()
