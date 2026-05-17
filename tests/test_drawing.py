import tkinter as tk
from types import SimpleNamespace
import unittest

from logic_sim.drawing import (
    COMPONENT_FILL,
    ON_COLOR,
    PIN_INPUT_COLOR,
    draw_free_wire,
    draw_preview_part,
    draw_part,
    part_bounds,
    pattern_dot_positions,
    pin_positions,
    wire_preview_points,
)
from logic_sim.model import Circuit, FreeWire, build_custom_component
from logic_sim.simulator import step_circuit
from logic_sim.ui import BUILTIN_TOOLS, ComponentLayoutDialog, LogicSimulatorApp, make_preview_part


class FakeCanvas:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("create_"):
            return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        raise AttributeError(name)


class DrawingGeometryTests(unittest.TestCase):
    def test_input_pin_has_one_output_pin_on_right(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 100, 100)

        pins = pin_positions(input_pin, {})

        self.assertEqual({"out": (120, 100, "output")}, pins)

    def test_custom_component_uses_saved_interface_pins(self):
        subcircuit = Circuit()
        subcircuit.add_part("Input Pin", 0, 0, label="A")
        subcircuit.add_part("Input Pin", 0, 80, label="B")
        subcircuit.add_part("Output Pin", 200, 40, label="OUT")
        custom = build_custom_component("Pair", subcircuit)

        circuit = Circuit(custom_components={"Pair": custom})
        part = circuit.add_part("CUSTOM", 100, 100, custom_type="Pair")

        pins = pin_positions(part, circuit.custom_components)
        bounds = part_bounds(part, circuit.custom_components)

        self.assertEqual((50, 70, 150, 130), bounds)
        self.assertEqual((60, 80, "input"), pins["A"])
        self.assertEqual((60, 120, "input"), pins["B"])
        self.assertEqual((160, 100, "output"), pins["OUT"])

    def test_custom_component_uses_saved_size_and_pin_locations(self):
        subcircuit = Circuit()
        subcircuit.add_part("Input Pin", 0, 20, label="A")
        subcircuit.add_part("Output Pin", 100, 60, label="OUT")
        custom = build_custom_component("Sized", subcircuit, width=160, height=100)

        circuit = Circuit(custom_components={"Sized": custom})
        part = circuit.add_part("CUSTOM", 200, 200, custom_type="Sized")

        self.assertEqual((120, 150, 280, 250), part_bounds(part, circuit.custom_components))
        self.assertEqual((150, 180, "input"), pin_positions(part, circuit.custom_components)["A"])
        self.assertEqual((250, 220, "output"), pin_positions(part, circuit.custom_components)["OUT"])

    def test_preview_part_snaps_to_grid_without_editing_circuit(self):
        preview = make_preview_part(("builtin", "AND"), 107, 94)

        self.assertEqual("__preview__", preview.id)
        self.assertEqual("AND", preview.type)
        self.assertEqual((100, 100), (preview.x, preview.y))

    def test_custom_preview_remembers_custom_type(self):
        preview = make_preview_part(("custom", "Half Adder"), 42, 51)

        self.assertEqual("CUSTOM", preview.type)
        self.assertEqual("Half Adder", preview.custom_type)

    def test_gate_preview_uses_selected_symbol_style(self):
        part = make_preview_part(("builtin", "AND"), 100, 100)
        canvas = FakeCanvas()

        draw_preview_part(canvas, part, "ANSI", {})

        call_names = [name for name, _args, _kwargs in canvas.calls]
        self.assertIn("create_arc", call_names)
        self.assertNotIn("create_polygon", call_names)

    def test_non_gate_preview_uses_component_drawing_not_blue_preview(self):
        part = make_preview_part(("builtin", "Input Pin"), 100, 100)
        canvas = FakeCanvas()

        draw_preview_part(canvas, part, "ANSI", {})

        rectangles = [kwargs for name, _args, kwargs in canvas.calls if name == "create_rectangle"]
        self.assertEqual(COMPONENT_FILL, rectangles[0]["fill"])

    def test_input_pin_draws_turing_style_signal_pattern_dots(self):
        circuit = Circuit()
        part = circuit.add_part("Input Pin", 100, 100, pattern=[True, False, True])
        canvas = FakeCanvas()

        draw_part(canvas, part, "ANSI", {})

        pattern_dots = [
            kwargs
            for name, _args, kwargs in canvas.calls
            if name == "create_oval" and "pattern:p1:" in kwargs.get("tags", ())
        ]
        self.assertEqual(3, len(pattern_dots))
        self.assertEqual(ON_COLOR, pattern_dots[0]["fill"])
        self.assertEqual(PIN_INPUT_COLOR, pattern_dots[1]["fill"])

    def test_free_wire_uses_saved_color(self):
        canvas = FakeCanvas()
        wire = FreeWire("w1", [(0, 0), (40, 0)], color="#336699")

        draw_free_wire(canvas, wire)

        lines = [kwargs for name, _args, kwargs in canvas.calls if name == "create_line"]
        self.assertEqual("#336699", lines[0]["fill"])

    def test_and_and_nand_ansi_arc_center_stays_on_gate_center(self):
        for gate_type in ("AND", "NAND"):
            with self.subTest(gate_type=gate_type):
                circuit = Circuit()
                part = circuit.add_part(gate_type, 100, 100)
                canvas = FakeCanvas()

                draw_part(canvas, part, "ANSI", {})

                arc_boxes = [
                    args[:4]
                    for name, args, kwargs in canvas.calls
                    if name == "create_arc" and kwargs.get("extent") == 180
                ]
                self.assertTrue(arc_boxes)
                for left, _top, right, _bottom in arc_boxes:
                    self.assertEqual(part.x, int((left + right) / 2))

    def test_input_and_output_pins_are_small_grid_blocks(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 100, 100)
        output_pin = circuit.add_part("Output Pin", 200, 100)

        self.assertEqual((80, 80, 120, 120), part_bounds(input_pin, {}))
        self.assertEqual((180, 80, 220, 120), part_bounds(output_pin, {}))

    def test_component_pins_sit_on_wire_grid_edges(self):
        circuit = Circuit()
        and_gate = circuit.add_part("AND", 100, 100)
        or_gate = circuit.add_part("OR", 220, 100)

        self.assertEqual((60, 80, "input"), pin_positions(and_gate, {})["a"])
        self.assertEqual((140, 100, "output"), pin_positions(and_gate, {})["out"])
        self.assertEqual((180, 80, "input"), pin_positions(or_gate, {})["a"])
        self.assertEqual((260, 100, "output"), pin_positions(or_gate, {})["out"])

    def test_toolbar_part_list_excludes_switch(self):
        self.assertNotIn("Switch", BUILTIN_TOOLS)
        self.assertNotIn("Wire", BUILTIN_TOOLS)

    def test_wire_preview_makes_orthogonal_path(self):
        points = wire_preview_points((20, 20), (90, 70))

        self.assertEqual([(20, 20), (90, 20), (90, 70)], points)

    def test_wire_preview_routes_around_blocked_grid_points(self):
        points = wire_preview_points(
            (0, 0),
            (80, 40),
            blocked_points={(80, 0), (80, 20)},
        )

        self.assertNotIn((80, 0), _points_touched_by_path(points))
        self.assertNotIn((80, 20), _points_touched_by_path(points))
        self.assertEqual((0, 0), points[0])
        self.assertEqual((80, 40), points[-1])

    def test_canvas_has_right_click_cancel_binding(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            self.assertNotEqual("", app.canvas.bind("<Button-3>"))
        finally:
            root.destroy()

    def test_canvas_has_mouse_wheel_zoom_binding(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            self.assertNotEqual("", app.canvas.bind("<MouseWheel>"))
            self.assertNotEqual("", app.canvas.bind("<Button-4>"))
            self.assertNotEqual("", app.canvas.bind("<Button-5>"))
        finally:
            root.destroy()

    def test_wasd_keys_are_bound_for_panning(self):
        root = tk.Tk()
        root.withdraw()
        try:
            LogicSimulatorApp(root)
            self.assertNotEqual("", root.bind("<KeyPress-w>"))
            self.assertNotEqual("", root.bind("<KeyPress-a>"))
            self.assertNotEqual("", root.bind("<KeyPress-s>"))
            self.assertNotEqual("", root.bind("<KeyPress-d>"))
        finally:
            root.destroy()

    def test_empty_grid_drag_places_free_wire_without_wire_tool(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            app._current_tags = lambda: ()

            app.on_canvas_click(SimpleNamespace(x=20, y=20))
            app.on_canvas_drag(SimpleNamespace(x=90, y=70))
            app.on_canvas_release(SimpleNamespace(x=90, y=70))

            self.assertEqual(1, len(app.circuit.free_wires))
            self.assertEqual([(20, 20), (100, 20), (100, 80)], app.circuit.free_wires[0].points)
        finally:
            root.destroy()

    def test_empty_grid_wire_routes_around_component_grid_points(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            blocker = app.circuit.add_part("AND", 80, 20)
            app._current_tags = lambda: ()

            app.on_canvas_click(SimpleNamespace(x=0, y=0))
            app.on_canvas_drag(SimpleNamespace(x=160, y=40))
            app.on_canvas_release(SimpleNamespace(x=160, y=40))

            touched = _points_touched_by_path(app.circuit.free_wires[0].points)
            self.assertTrue(app._part_grid_points(blocker).isdisjoint(touched))
        finally:
            root.destroy()

    def test_wire_to_component_pin_routes_around_component_grid_points(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("OR", 100, 100)
            end = pin_positions(gate, {})["a"][:2]
            points = app._wire_path((100, 180), end)

            touched = _points_touched_by_path(points)
            self.assertTrue((app._part_grid_points(gate) - {end}).isdisjoint(touched))
        finally:
            root.destroy()

    def test_wire_path_can_cross_plain_wire_segment_without_node(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            app.circuit.add_free_wire([(100, 0), (100, 80)])

            points = app._wire_path((20, 40), (180, 40))

            self.assertEqual([(20, 40), (180, 40)], points)
        finally:
            root.destroy()

    def test_wire_path_routes_around_existing_wire_node(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            app.circuit.add_free_wire([(100, 0), (100, 40), (100, 80)])

            points = app._wire_path((20, 40), (180, 40))

            self.assertNotIn((100, 40), _points_touched_by_path(points))
        finally:
            root.destroy()

    def test_placed_wire_routes_around_component_grid_points(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            source = app.circuit.add_part("Input Pin", 20, 100)
            target = app.circuit.add_part("OR", 140, 100)
            wire = app.circuit.add_wire(source.id, "out", target.id, "a")
            end = pin_positions(target, {})["a"][:2]

            app.redraw()

            wire_items = app.canvas.find_withtag(f"wire:{wire.id}")
            self.assertEqual(1, len(wire_items))
            coords = app.canvas.coords(wire_items[0])
            points = [
                (int(coords[index]), int(coords[index + 1]))
                for index in range(0, len(coords), 2)
            ]
            touched = _points_touched_by_path(points)
            self.assertTrue((app._part_grid_points(target) - {end}).isdisjoint(touched))
        finally:
            root.destroy()

    def test_cannot_place_component_over_existing_component(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            app.circuit.add_part("AND", 100, 100)
            app.selected_tool = ("builtin", "OR")

            app.place_selected_tool(100, 100)

            self.assertEqual(1, len(app.circuit.parts))
        finally:
            root.destroy()

    def test_moving_component_over_existing_component_reverts(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            fixed = app.circuit.add_part("AND", 100, 100)
            mover = app.circuit.add_part("OR", 220, 100)
            app._current_tags = lambda: (f"part:{mover.id}",)

            app.on_canvas_click(SimpleNamespace(x=220, y=100))
            app.on_canvas_drag(SimpleNamespace(x=100, y=100))
            app.on_canvas_release(SimpleNamespace(x=100, y=100))

            self.assertEqual((100, 100), (fixed.x, fixed.y))
            self.assertEqual((220, 100), (mover.x, mover.y))
        finally:
            root.destroy()

    def test_input_pin_click_without_pending_output_can_start_free_wire(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("AND", 100, 100)
            x, y, kind = pin_positions(gate, {})["a"]
            app._current_tags = lambda: (f"pin:{gate.id}:a:{kind}",)

            app.on_canvas_click(SimpleNamespace(x=x, y=y))
            app.on_canvas_drag(SimpleNamespace(x=10, y=y))
            app.on_canvas_release(SimpleNamespace(x=10, y=y))

            self.assertEqual(1, len(app.circuit.free_wires))
        finally:
            root.destroy()

    def test_input_pin_wire_start_uses_coordinates_when_current_tags_are_missing(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("AND", 100, 100)
            x, y, _kind = pin_positions(gate, {})["a"]
            app._current_tags = lambda: ()

            app.on_canvas_click(SimpleNamespace(x=x, y=y))
            app.on_canvas_drag(SimpleNamespace(x=10, y=y))
            app.on_canvas_release(SimpleNamespace(x=10, y=y))

            self.assertEqual(1, len(app.circuit.free_wires))
        finally:
            root.destroy()

    def test_output_pin_drag_from_input_component_places_free_wire(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            input_pin = app.circuit.add_part("Input Pin", 100, 100)
            x, y, _kind = pin_positions(input_pin, {})["out"]

            app.on_canvas_press(SimpleNamespace(x=x, y=y, state=0))
            app.on_canvas_drag(SimpleNamespace(x=180, y=y))
            app.on_canvas_release(SimpleNamespace(x=180, y=y))

            self.assertIsNone(app.pending_output)
            self.assertEqual(1, len(app.circuit.free_wires))
            self.assertEqual([(120, 100), (180, 100)], app.circuit.free_wires[0].points)
        finally:
            root.destroy()

    def test_output_pin_drag_to_input_pin_connects_wire(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            source = app.circuit.add_part("Input Pin", 100, 100)
            target = app.circuit.add_part("LED", 240, 100)
            source_x, source_y, _kind = pin_positions(source, {})["out"]
            target_x, target_y, _kind = pin_positions(target, {})["in"]

            app.on_canvas_press(SimpleNamespace(x=source_x, y=source_y, state=0))
            app.on_canvas_drag(SimpleNamespace(x=target_x, y=target_y))
            app.on_canvas_release(SimpleNamespace(x=target_x, y=target_y))

            self.assertEqual(0, len(app.circuit.free_wires))
            self.assertEqual(1, len(app.circuit.wires))
            self.assertEqual(source.id, app.circuit.wires[0].source_part)
            self.assertEqual(target.id, app.circuit.wires[0].target_part)
        finally:
            root.destroy()

    def test_input_pin_drag_start_is_separate_from_normal_click_selection(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("AND", 100, 100)
            x, y, _kind = pin_positions(gate, {})["a"]
            app._current_tags = lambda: (f"part:{gate.id}",)

            app.on_canvas_press(SimpleNamespace(x=x, y=y))
            app.on_canvas_drag(SimpleNamespace(x=10, y=y))
            app.on_canvas_release(SimpleNamespace(x=10, y=y))

            self.assertEqual(1, len(app.circuit.free_wires))
            self.assertIsNone(app.drag_part_id)
        finally:
            root.destroy()

    def test_input_wire_can_end_at_free_wire_round_node_without_moving_part(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("AND", 100, 100)
            app.circuit.add_free_wire([(20, 20), (80, 20)])
            start_position = (gate.x, gate.y)
            x, y, _kind = pin_positions(gate, {})["a"]

            app.on_canvas_press(SimpleNamespace(x=x, y=y))
            app.on_canvas_drag(SimpleNamespace(x=80, y=20))
            app.on_canvas_release(SimpleNamespace(x=80, y=20))

            self.assertEqual(start_position, (gate.x, gate.y))
            self.assertEqual(2, len(app.circuit.free_wires))
            self.assertEqual((80, 20), app.circuit.free_wires[-1].points[-1])
        finally:
            root.destroy()

    def test_multiple_inputs_can_place_wires_to_same_round_node(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            first = app.circuit.add_part("AND", 100, 100)
            second = app.circuit.add_part("OR", 180, 100)
            app.circuit.add_free_wire([(20, 20), (80, 20)])
            first_x, first_y, _kind = pin_positions(first, {})["a"]
            app.on_canvas_press(SimpleNamespace(x=first_x, y=first_y))
            app.on_canvas_drag(SimpleNamespace(x=80, y=20))
            app.on_canvas_release(SimpleNamespace(x=80, y=20))

            second_start = (second.x, second.y)
            second_x, second_y, _kind = pin_positions(second, {})["a"]
            app.on_canvas_press(SimpleNamespace(x=second_x, y=second_y))
            app.on_canvas_drag(SimpleNamespace(x=80, y=20))
            app.on_canvas_release(SimpleNamespace(x=80, y=20))

            self.assertEqual(second_start, (second.x, second.y))
            self.assertEqual(3, len(app.circuit.free_wires))
            self.assertEqual((80, 20), app.circuit.free_wires[-1].points[-1])
        finally:
            root.destroy()

    def test_output_wire_can_end_at_free_wire_round_node(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            source = app.circuit.add_part("Input Pin", 100, 100)
            app.circuit.add_free_wire([(20, 20), (80, 20)])
            x, y, _kind = pin_positions(source, {})["out"]

            app.on_canvas_press(SimpleNamespace(x=x, y=y, state=0))
            app.on_canvas_drag(SimpleNamespace(x=80, y=20))
            app.on_canvas_release(SimpleNamespace(x=80, y=20))

            self.assertIsNone(app.pending_output)
            self.assertEqual(2, len(app.circuit.free_wires))
            self.assertEqual((80, 20), app.circuit.free_wires[-1].points[-1])
        finally:
            root.destroy()

    def test_free_wire_node_can_extend_to_input_pin_and_carry_signal(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            source = app.circuit.add_part("Input Pin", 100, 100, state=True)
            led = app.circuit.add_part("LED", 240, 100)
            source_x, source_y, _kind = pin_positions(source, {})["out"]
            target_x, target_y, _kind = pin_positions(led, {})["in"]
            wire = app.circuit.add_free_wire([(source_x, source_y), (180, source_y)])
            app._event_tags = lambda _event: (f"wire:{wire.id}",)

            app.on_canvas_press(SimpleNamespace(x=180, y=source_y, state=0))
            app.on_canvas_drag(SimpleNamespace(x=target_x, y=target_y))
            app.on_canvas_release(SimpleNamespace(x=target_x, y=target_y))
            step_circuit(app.circuit)

            self.assertEqual(2, len(app.circuit.free_wires))
            self.assertEqual((target_x, target_y), app.circuit.free_wires[-1].points[-1])
            self.assertTrue(led.state)
        finally:
            root.destroy()

    def test_input_to_output_pin_drag_does_not_place_wire(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            source = app.circuit.add_part("Input Pin", 100, 100)
            led = app.circuit.add_part("LED", 240, 100)
            source_x, source_y, _kind = pin_positions(source, {})["out"]
            input_x, input_y, _kind = pin_positions(led, {})["in"]

            app.on_canvas_press(SimpleNamespace(x=input_x, y=input_y, state=0))
            app.on_canvas_drag(SimpleNamespace(x=source_x, y=source_y))
            app.on_canvas_release(SimpleNamespace(x=source_x, y=source_y))

            self.assertEqual(0, len(app.circuit.wires))
            self.assertEqual(0, len(app.circuit.free_wires))
        finally:
            root.destroy()

    def test_free_wire_node_to_output_pin_drag_does_not_place_wire(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            source = app.circuit.add_part("Input Pin", 100, 100)
            source_x, source_y, _kind = pin_positions(source, {})["out"]
            wire = app.circuit.add_free_wire([(20, source_y), (80, source_y)])
            app._event_tags = lambda _event: (f"wire:{wire.id}",)

            app.on_canvas_press(SimpleNamespace(x=80, y=source_y, state=0))
            app.on_canvas_drag(SimpleNamespace(x=source_x, y=source_y))
            app.on_canvas_release(SimpleNamespace(x=source_x, y=source_y))

            self.assertEqual(1, len(app.circuit.free_wires))
            self.assertEqual([(20, source_y), (80, source_y)], app.circuit.free_wires[0].points)
        finally:
            root.destroy()

    def test_straight_input_wire_uses_two_points(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("AND", 100, 100)
            x, y, _kind = pin_positions(gate, {})["a"]

            app.on_canvas_press(SimpleNamespace(x=x, y=y))
            app.on_canvas_drag(SimpleNamespace(x=20, y=y))
            app.on_canvas_release(SimpleNamespace(x=20, y=y))

            self.assertEqual([(x, y), (20, y)], app.circuit.free_wires[0].points)
        finally:
            root.destroy()

    def test_wire_started_from_input_does_not_avoid_existing_wire_points(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            gate = app.circuit.add_part("AND", 200, 100)
            app.circuit.add_free_wire([(100, 80), (100, 120)])
            x, y, _kind = pin_positions(gate, {})["a"]

            app.on_canvas_press(SimpleNamespace(x=x, y=y))
            app.on_canvas_drag(SimpleNamespace(x=100, y=120))

            self.assertEqual([(x, y), (100, y), (100, 120)], app.wire_preview)
        finally:
            root.destroy()

    def test_ctrl_left_click_changes_wire_color(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            wire = app.circuit.add_free_wire([(0, 0), (80, 0)])
            app._event_tags = lambda _event: (f"wire:{wire.id}",)
            app._ask_wire_color = lambda _wire_id: "#112233"

            app.on_canvas_press(SimpleNamespace(x=40, y=0, state=0x0004))

            self.assertEqual("#112233", app.circuit.free_wires[0].color)
        finally:
            root.destroy()

    def test_ctrl_left_click_hides_only_clicked_input_pattern_dots(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            first = app.circuit.add_part("Input Pin", 100, 100, pattern=[False, False])
            second = app.circuit.add_part("Input Pin", 100, 180, pattern=[False, False])
            dot_x, dot_y = pattern_dot_positions(first)[0]

            app.on_canvas_press(SimpleNamespace(x=dot_x, y=dot_y, state=0x0004))

            first_canvas = FakeCanvas()
            second_canvas = FakeCanvas()
            draw_part(first_canvas, first, "ANSI", {})
            draw_part(second_canvas, second, "ANSI", {})
            first_dots = [
                kwargs
                for name, _args, kwargs in first_canvas.calls
                if name == "create_oval" and "pattern:p1:" in kwargs.get("tags", ())
            ]
            second_dots = [
                kwargs
                for name, _args, kwargs in second_canvas.calls
                if name == "create_oval" and "pattern:p2:" in kwargs.get("tags", ())
            ]

            self.assertEqual([], first_dots)
            self.assertEqual(2, len(second_dots))
        finally:
            root.destroy()

    def test_ctrl_left_click_input_block_hides_pattern_dots_immediately(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            part = app.circuit.add_part("Input Pin", 100, 100, pattern=[False, False])
            app._event_tags = lambda _event: (f"part:{part.id}",)
            redraws = []
            app.redraw = lambda: redraws.append(True)

            app.on_canvas_press(SimpleNamespace(x=part.x, y=part.y, state=0x0004))

            self.assertFalse(part.show_pattern)
            self.assertEqual([True], redraws)
        finally:
            root.destroy()

    def test_signal_dot_click_updates_current_pattern_value_only(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            part = app.circuit.add_part(
                "Input Pin",
                100,
                100,
                state=False,
                pattern=[False, False],
            )
            app.circuit.time_step = 1

            app.toggle_pattern_value(part.id, 1)

            self.assertEqual([False, True], part.pattern)
            self.assertTrue(part.state)
        finally:
            root.destroy()

    def test_signal_dot_click_does_not_change_current_value_for_future_dot(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            part = app.circuit.add_part(
                "Input Pin",
                100,
                100,
                state=False,
                pattern=[False, False],
            )

            app.toggle_pattern_value(part.id, 1)

            self.assertEqual([False, True], part.pattern)
            self.assertFalse(part.state)
        finally:
            root.destroy()

    def test_main_mode_uses_signal_length_control_without_prompting_each_input(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            app.selected_tool = ("builtin", "Input Pin")
            app.signal_length.set(3)
            app._ask_pin_label = lambda _part_type: "A"
            app._ask_input_pattern_length = lambda: self.fail("length prompt should be hidden")

            app.place_selected_tool(20, 20)

            input_pin = next(iter(app.circuit.parts.values()))
            self.assertEqual([False, False, False], input_pin.pattern)
        finally:
            root.destroy()

    def test_custom_component_mode_input_has_no_signal_set(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)
            app.enter_custom_mode()
            app.selected_tool = ("builtin", "Input Pin")
            app.signal_length.set(3)
            app._ask_pin_label = lambda _part_type: "A"

            app.place_selected_tool(20, 20)

            input_pin = next(iter(app.circuit.parts.values()))
            self.assertEqual([], input_pin.pattern)
        finally:
            root.destroy()

    def test_component_layout_dialog_can_update_size_and_pin_locations(self):
        root = tk.Tk()
        root.withdraw()
        try:
            circuit = Circuit()
            circuit.add_part("Input Pin", 0, 20, label="A")
            circuit.add_part("Output Pin", 100, 60, label="OUT")
            dialog = ComponentLayoutDialog(root, "Sized", circuit, auto_show=False)

            dialog.width_var.set(180)
            dialog.height_var.set(120)
            dialog.pin_locations["A"] = (-70, -30)
            dialog.pin_locations["OUT"] = (70, 30)
            dialog.accept()

            self.assertEqual(180, dialog.result["width"])
            self.assertEqual(120, dialog.result["height"])
            self.assertEqual((-70, -30), dialog.result["input_locations"]["A"])
            self.assertEqual((70, 30), dialog.result["output_locations"]["OUT"])
        finally:
            root.destroy()

    def test_save_component_button_only_enabled_in_custom_component_mode(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = LogicSimulatorApp(root)

            self.assertEqual("disabled", str(app.save_component_button.cget("state")))
            app.enter_custom_mode()
            self.assertEqual("normal", str(app.save_component_button.cget("state")))
            app.enter_main_mode()
            self.assertEqual("disabled", str(app.save_component_button.cget("state")))
        finally:
            root.destroy()


def _points_touched_by_path(points):
    touched = set()
    for start, end in zip(points, points[1:]):
        x1, y1 = start
        x2, y2 = end
        if x1 == x2:
            step = 20 if y2 >= y1 else -20
            for y in range(y1, y2 + step, step):
                touched.add((x1, y))
        elif y1 == y2:
            step = 20 if x2 >= x1 else -20
            for x in range(x1, x2 + step, step):
                touched.add((x, y1))
    return touched


if __name__ == "__main__":
    unittest.main()
