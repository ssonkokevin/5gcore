"""The operator's cell plan: what a serving cell means as a position.

The E-SMLC produces the position when it can. When it cannot, the MME falls
back to Cell-ID positioning, and the only honest source of a cell's position
is a plan the operator maintains. A cell row without a radius has no
uncertainty and is rejected at load time rather than used; a cell missing
from the plan yields no position at all.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.codecs import lcsap  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "lab_cells.json"


class CellPlanError(ValueError):
    """The plan file would make a fallback position dishonest."""


@dataclass(frozen=True)
class PlannedCell:
    plmn: bytes
    cell: int
    latitude: float
    longitude: float
    radius_m: int
    label: str = ""

    def as_dict(self) -> dict:
        return {
            "plmn": self.plmn.hex(),
            "cell": f"0x{self.cell:07X}",
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_m": self.radius_m,
            "label": self.label,
        }


class CellPlan:
    def __init__(self, cells: List[PlannedCell]):
        self._cells: Dict[Tuple[bytes, int], PlannedCell] = {}
        for cell in cells:
            key = (cell.plmn, cell.cell)
            if key in self._cells:
                raise CellPlanError(
                    f"cell 0x{cell.cell:07X} under PLMN {cell.plmn.hex()} "
                    "appears twice in the plan")
            self._cells[key] = cell

    @classmethod
    def from_dict(cls, document: dict) -> "CellPlan":
        mcc, mnc = _split_plmn(document.get("plmn"))
        try:
            plmn = lcsap.plmn_identity(mcc, mnc)
        except lcsap.LcsApError as exc:
            raise CellPlanError(str(exc)) from exc
        cells = []
        for index, item in enumerate(document.get("cells", [])):
            try:
                cell = int(str(item["cell"]), 0)
            except (KeyError, ValueError) as exc:
                raise CellPlanError(f"cell {index}: a numeric cell identity is required") from exc
            if not 0 <= cell < (1 << 28):
                raise CellPlanError(f"cell {index}: {cell} is not 28 bits")
            latitude = float(item["latitude"])
            longitude = float(item["longitude"])
            if not -90.0 <= latitude <= 90.0:
                raise CellPlanError(f"cell {index}: latitude {latitude} is outside -90..90")
            if not -180.0 <= longitude <= 180.0:
                raise CellPlanError(f"cell {index}: longitude {longitude} is outside -180..180")
            radius = item.get("radius_m")
            if isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius <= 0:
                raise CellPlanError(
                    f"cell {index}: radius_m must be a positive number, got {radius!r}")
            cells.append(PlannedCell(plmn=plmn, cell=cell, latitude=latitude,
                                     longitude=longitude, radius_m=int(round(radius)),
                                     label=str(item.get("label", ""))))
        return cls(cells)

    @classmethod
    def from_file(cls, path) -> "CellPlan":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def lookup(self, plmn: bytes, cell: int) -> Optional[PlannedCell]:
        return self._cells.get((bytes(plmn), cell))

    def cells(self) -> List[PlannedCell]:
        return list(self._cells.values())

    def __len__(self) -> int:
        return len(self._cells)


def _split_plmn(text: object) -> Tuple[str, str]:
    if not isinstance(text, str):
        raise CellPlanError("the plan needs a plmn such as 001-01")
    mcc, _, mnc = text.partition("-")
    return mcc, mnc
