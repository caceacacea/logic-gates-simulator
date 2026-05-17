from __future__ import annotations

from logic_sim.model import Circuit


class History:
    def __init__(self) -> None:
        self._undo: list[dict] = []
        self._redo: list[dict] = []

    def capture(self, circuit: Circuit) -> None:
        self._undo.append(circuit.to_dict())
        self._redo.clear()

    def undo(self, current: Circuit) -> Circuit | None:
        if not self._undo:
            return None
        self._redo.append(current.to_dict())
        return Circuit.from_dict(self._undo.pop())

    def redo(self, current: Circuit) -> Circuit | None:
        if not self._redo:
            return None
        self._undo.append(current.to_dict())
        return Circuit.from_dict(self._redo.pop())

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
