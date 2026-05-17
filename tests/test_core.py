import tempfile
import unittest
from pathlib import Path

from logic_sim.model import Circuit, build_custom_component
from logic_sim.persistence import (
    component_folder,
    load_circuit,
    load_custom_components_from_folder,
    save_circuit,
    save_custom_component_to_folder,
)
from logic_sim.drawing import pin_positions
from logic_sim.simulator import evaluate_custom_component, evaluate_gate, step_circuit


class GateTruthTableTests(unittest.TestCase):
    def test_two_input_gate_truth_tables(self):
        cases = {
            "AND": [False, False, False, True],
            "OR": [False, True, True, True],
            "NAND": [True, True, True, False],
            "NOR": [True, False, False, False],
            "XOR": [False, True, True, False],
        }

        for gate_type, expected in cases.items():
            with self.subTest(gate_type=gate_type):
                actual = [
                    evaluate_gate(gate_type, {"a": False, "b": False}),
                    evaluate_gate(gate_type, {"a": False, "b": True}),
                    evaluate_gate(gate_type, {"a": True, "b": False}),
                    evaluate_gate(gate_type, {"a": True, "b": True}),
                ]
                self.assertEqual(expected, actual)

    def test_not_gate_truth_table(self):
        self.assertTrue(evaluate_gate("NOT", {"in": False}))
        self.assertFalse(evaluate_gate("NOT", {"in": True}))


class SimulationTests(unittest.TestCase):
    def test_step_updates_chain_from_switch_to_gate_to_led(self):
        circuit = Circuit()
        left = circuit.add_part("Switch", 0, 0, state=True)
        right = circuit.add_part("Switch", 0, 80, state=True)
        gate = circuit.add_part("AND", 120, 40)
        led = circuit.add_part("LED", 240, 40)

        circuit.add_wire(left.id, "out", gate.id, "a")
        circuit.add_wire(right.id, "out", gate.id, "b")
        circuit.add_wire(gate.id, "out", led.id, "in")

        step_circuit(circuit)

        self.assertTrue(circuit.part(led.id).state)
        self.assertTrue(circuit.wires[-1].signal)

    def test_step_updates_output_pin_from_input_pin(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 0, 0, label="A", state=True)
        output_pin = circuit.add_part("Output Pin", 120, 0, label="OUT")
        circuit.add_wire(input_pin.id, "out", output_pin.id, "in")

        step_circuit(circuit)

        self.assertTrue(circuit.part(output_pin.id).state)

    def test_free_wire_carries_signal_from_output_to_input_pin(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 100, 100, state=True)
        led = circuit.add_part("LED", 240, 100)
        source_x, source_y, _kind = pin_positions(input_pin, {})["out"]
        target_x, target_y, _kind = pin_positions(led, {})["in"]
        circuit.add_free_wire([(source_x, source_y), (target_x, target_y)])

        step_circuit(circuit)

        self.assertTrue(circuit.part(led.id).state)
        self.assertTrue(circuit.free_wires[0].signal)

    def test_touching_free_wires_share_signal(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 100, 100, state=True)
        led = circuit.add_part("LED", 240, 100)
        source_x, source_y, _kind = pin_positions(input_pin, {})["out"]
        target_x, target_y, _kind = pin_positions(led, {})["in"]
        circuit.add_free_wire([(source_x, source_y), (180, source_y)])
        circuit.add_free_wire([(180, source_y), (target_x, target_y)])

        step_circuit(circuit)

        self.assertTrue(circuit.part(led.id).state)
        self.assertTrue(circuit.free_wires[0].signal)
        self.assertTrue(circuit.free_wires[1].signal)

    def test_crossing_free_wires_without_node_do_not_share_signal(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 100, 100, state=True)
        led = circuit.add_part("LED", 240, 140)
        source_x, source_y, _kind = pin_positions(input_pin, {})["out"]
        target_x, target_y, _kind = pin_positions(led, {})["in"]
        crossing_y = source_y + 40
        circuit.add_free_wire([(source_x, source_y), (source_x, source_y + 80)])
        circuit.add_free_wire([(source_x - 40, crossing_y), (target_x, target_y)])

        step_circuit(circuit)

        self.assertFalse(circuit.part(led.id).state)
        self.assertTrue(circuit.free_wires[0].signal)
        self.assertFalse(circuit.free_wires[1].signal)


class PersistenceTests(unittest.TestCase):
    def test_save_and_load_circuit_round_trip(self):
        circuit = Circuit()
        switch = circuit.add_part("Switch", 10, 20, state=True)
        led = circuit.add_part("LED", 120, 20)
        circuit.add_wire(switch.id, "out", led.id, "in", color="#abcdef")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "circuit.json"
            save_circuit(circuit, path)
            loaded = load_circuit(path)

        self.assertEqual(2, len(loaded.parts))
        self.assertEqual(1, len(loaded.wires))
        self.assertTrue(loaded.part(switch.id).state)
        self.assertEqual("#abcdef", loaded.wires[0].color)

    def test_free_wires_save_and_load_with_circuit(self):
        circuit = Circuit()
        free_wire = circuit.add_free_wire(
            [(0, 0), (80, 0), (80, 40)],
            color="#123456",
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "circuit.json"
            save_circuit(circuit, path)
            loaded = load_circuit(path)

        self.assertEqual(free_wire.points, loaded.free_wires[0].points)
        self.assertEqual("#123456", loaded.free_wires[0].color)

    def test_input_signal_pattern_save_and_load_with_circuit(self):
        circuit = Circuit()
        input_pin = circuit.add_part(
            "Input Pin",
            0,
            0,
            label="A",
            pattern=[True, False, True, True],
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "circuit.json"
            save_circuit(circuit, path)
            loaded = load_circuit(path)

        self.assertEqual([True, False, True, True], loaded.part(input_pin.id).pattern)

    def test_input_signal_visibility_save_and_load_with_circuit(self):
        circuit = Circuit()
        input_pin = circuit.add_part(
            "Input Pin",
            0,
            0,
            label="A",
            pattern=[False, False],
        )
        input_pin.show_pattern = False

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "circuit.json"
            save_circuit(circuit, path)
            loaded = load_circuit(path)

        self.assertFalse(loaded.part(input_pin.id).show_pattern)

    def test_custom_components_save_in_workspace_component_folder(self):
        subcircuit = Circuit()
        subcircuit.add_part("Input Pin", 0, 0, label="A")
        subcircuit.add_part("Output Pin", 120, 0, label="OUT")
        component = build_custom_component("My Gate", subcircuit)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            path = save_custom_component_to_folder(component, workspace)
            loaded = load_custom_components_from_folder(workspace)

        self.assertEqual(component_folder(workspace) / "My_Gate.component.json", path)
        self.assertIn("My Gate", loaded)


class CustomComponentTests(unittest.TestCase):
    def test_custom_component_uses_input_and_output_pins(self):
        subcircuit = Circuit()
        a = subcircuit.add_part("Input Pin", 0, 0, label="A")
        b = subcircuit.add_part("Input Pin", 0, 80, label="B")
        gate = subcircuit.add_part("XOR", 120, 40)
        out = subcircuit.add_part("Output Pin", 240, 40, label="OUT")
        subcircuit.add_wire(a.id, "out", gate.id, "a")
        subcircuit.add_wire(b.id, "out", gate.id, "b")
        subcircuit.add_wire(gate.id, "out", out.id, "in")

        xor_component = build_custom_component("My XOR", subcircuit)

        circuit = Circuit(custom_components={"My XOR": xor_component})
        left = circuit.add_part("Switch", 0, 0, state=True)
        right = circuit.add_part("Switch", 0, 80, state=False)
        custom = circuit.add_part("CUSTOM", 140, 40, custom_type="My XOR")
        led = circuit.add_part("LED", 300, 40)
        circuit.add_wire(left.id, "out", custom.id, "A")
        circuit.add_wire(right.id, "out", custom.id, "B")
        circuit.add_wire(custom.id, "OUT", led.id, "in")

        step_circuit(circuit)

        self.assertTrue(circuit.part(led.id).state)

    def test_custom_component_stores_size_and_external_pin_locations(self):
        subcircuit = Circuit()
        subcircuit.add_part("Input Pin", 0, 20, label="A")
        subcircuit.add_part("Output Pin", 100, 60, label="OUT")

        component = build_custom_component("Sized", subcircuit, width=160, height=100)

        self.assertEqual(160, component.width)
        self.assertEqual(100, component.height)
        self.assertEqual((-50, -20), component.input_locations["A"])
        self.assertEqual((50, 20), component.output_locations["OUT"])

    def test_custom_component_can_use_saved_custom_components(self):
        base = Circuit()
        base_in = base.add_part("Input Pin", 0, 0, label="A")
        inverter = base.add_part("NOT", 100, 0)
        base_out = base.add_part("Output Pin", 200, 0, label="OUT")
        base.add_wire(base_in.id, "out", inverter.id, "in")
        base.add_wire(inverter.id, "out", base_out.id, "in")
        not_component = build_custom_component("My NOT", base)

        wrapper = Circuit(custom_components={"My NOT": not_component})
        wrapper_in = wrapper.add_part("Input Pin", 0, 0, label="A")
        nested = wrapper.add_part("CUSTOM", 120, 0, custom_type="My NOT")
        wrapper_out = wrapper.add_part("Output Pin", 240, 0, label="OUT")
        wrapper.add_wire(wrapper_in.id, "out", nested.id, "A")
        wrapper.add_wire(nested.id, "OUT", wrapper_out.id, "in")

        wrapper_component = build_custom_component("Wrapped NOT", wrapper)

        self.assertEqual({"OUT": True}, evaluate_custom_component(wrapper_component, {"A": False}))
        self.assertIn("My NOT", wrapper_component.circuit.custom_components)

    def test_input_signal_pattern_advances_one_value_per_step(self):
        circuit = Circuit()
        input_pin = circuit.add_part("Input Pin", 0, 0, label="A", pattern=[False, True])
        output_pin = circuit.add_part("Output Pin", 120, 0, label="OUT")
        circuit.add_wire(input_pin.id, "out", output_pin.id, "in")

        step_circuit(circuit)
        self.assertFalse(circuit.part(output_pin.id).state)

        step_circuit(circuit)
        self.assertTrue(circuit.part(output_pin.id).state)

    def test_custom_component_rejects_empty_interface_even_with_nested_parts(self):
        subcircuit = Circuit()
        subcircuit.add_part("CUSTOM", 100, 0, custom_type="Nested")

        with self.assertRaises(ValueError):
            build_custom_component("Bad", subcircuit)


if __name__ == "__main__":
    unittest.main()
