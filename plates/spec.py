"""Test-plate geometry. Process-agnostic: the same plate prints on resin and PLA.

Coordinates are in mm, viewed from above, with the origin at the plate's
bottom-left corner. Slot (row, col) has its center at
    x = ORIGIN + PITCH * col,  y = PLATE - ORIGIN - PITCH * row
so row 0 is the top row in a top-down scan.

Orientation markers: square through-hole fiducials at the top-left, top-right,
and bottom-left corners (the bottom-right is empty), plus a notch in the
bottom edge. Piece identity comes from grid position only; there is no text.
"""

PLATE = 100.0       # mm, square plate side
THICK = 3.0         # mm, plate thickness
GRID = (8, 8)       # rows, cols
PITCH = 10.0        # mm between slot centers
ORIGIN = 15.0       # mm from plate edge to the first slot center
PIN_H = 3.0         # mm, pin height above the plate top

D_MIN, D_MAX = 1.0, 8.0        # library nominal diameter range, mm
D_STEP = 0.1
TRAIN_RANGE = (1.5, 7.0)       # agents propose only inside this; held-out also goes outside it

FIDUCIAL = 4.0                 # mm, square fiducial side
FIDUCIALS = [(5.0, 95.0), (95.0, 95.0), (5.0, 5.0)]  # centers: top-left, top-right, bottom-left
NOTCH = (50.0, 6.0, 2.5)       # bottom-edge notch: center x, width, depth

SEGMENTS = 128                 # circle resolution in the STL, fine enough to not matter


def slot_center(row: int, col: int) -> tuple[float, float]:
    return ORIGIN + PITCH * col, PLATE - ORIGIN - PITCH * row


def all_slots() -> list[tuple[int, int]]:
    return [(r, c) for r in range(GRID[0]) for c in range(GRID[1])]
