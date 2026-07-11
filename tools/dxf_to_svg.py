from __future__ import annotations

import html
import math
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "data" / "헌병분견대"
OUTPUT_DIR = BASE_DIR / "web" / "assets" / "plans"

DRAWINGS = {
    "main-floor": SOURCE_DIR / "등록198_구 마산헌병 분견대_004평면도.dxf",
    "basement": SOURCE_DIR / "등록198_구 마산헌병 분견대_005지하평면도.dxf",
}


def read_pairs(path: Path) -> list[tuple[str, str]]:
    lines = path.read_text(encoding="cp949", errors="ignore").splitlines()
    pairs: list[tuple[str, str]] = []
    for index in range(0, len(lines) - 1, 2):
        pairs.append((lines[index].strip(), lines[index + 1].strip()))
    return pairs


def is_entity_start(pairs: list[tuple[str, str]], index: int, entity_type: str) -> bool:
    return pairs[index][0] == "0" and pairs[index][1] == entity_type


def extract_entities_section(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    in_entities = False
    section: list[tuple[str, str]] = []

    for index, pair in enumerate(pairs):
        code, value = pair
        if code == "2" and value == "ENTITIES" and index > 0 and pairs[index - 1] == ("0", "SECTION"):
            in_entities = True
            continue
        if in_entities and pair == ("0", "ENDSEC"):
            break
        if in_entities:
            section.append(pair)

    return section


def read_line_entity(pairs: list[tuple[str, str]], start: int) -> tuple[dict[str, str], int]:
    values: dict[str, str] = {}
    index = start + 1
    while index < len(pairs) and pairs[index][0] != "0":
        code, value = pairs[index]
        if code in {"8", "10", "20", "11", "21", "62"}:
            values[code] = value
        index += 1
    return values, index


def read_lwpolyline_entity(pairs: list[tuple[str, str]], start: int) -> tuple[dict[str, object], int]:
    layer = ""
    color = ""
    closed = False
    points: list[tuple[float, float]] = []
    pending_x: float | None = None

    index = start + 1
    while index < len(pairs) and pairs[index][0] != "0":
        code, value = pairs[index]
        if code == "8":
            layer = value
        elif code == "62":
            color = value
        elif code == "70":
            try:
                closed = bool(int(value) & 1)
            except ValueError:
                closed = False
        elif code == "10":
            try:
                pending_x = float(value)
            except ValueError:
                pending_x = None
        elif code == "20" and pending_x is not None:
            try:
                points.append((pending_x, float(value)))
            except ValueError:
                pass
            pending_x = None
        index += 1

    return {"layer": layer, "color": color, "closed": closed, "points": points}, index


def read_circle_entity(pairs: list[tuple[str, str]], start: int) -> tuple[dict[str, str], int]:
    values: dict[str, str] = {}
    index = start + 1
    while index < len(pairs) and pairs[index][0] != "0":
        code, value = pairs[index]
        if code in {"8", "10", "20", "40", "62"}:
            values[code] = value
        index += 1
    return values, index


def convert_entities(section: list[tuple[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    lines: list[dict[str, object]] = []
    polylines: list[dict[str, object]] = []
    circles: list[dict[str, object]] = []
    index = 0

    while index < len(section):
        if is_entity_start(section, index, "LINE"):
            values, index = read_line_entity(section, index)
            try:
                lines.append(
                    {
                        "layer": values.get("8", ""),
                        "color": values.get("62", ""),
                        "x1": float(values["10"]),
                        "y1": float(values["20"]),
                        "x2": float(values["11"]),
                        "y2": float(values["21"]),
                    }
                )
            except (KeyError, ValueError):
                pass
            continue

        if is_entity_start(section, index, "LWPOLYLINE"):
            values, index = read_lwpolyline_entity(section, index)
            if len(values["points"]) >= 2:
                polylines.append(values)
            continue

        if is_entity_start(section, index, "CIRCLE"):
            values, index = read_circle_entity(section, index)
            try:
                circles.append(
                    {
                        "layer": values.get("8", ""),
                        "color": values.get("62", ""),
                        "cx": float(values["10"]),
                        "cy": float(values["20"]),
                        "r": float(values["40"]),
                    }
                )
            except (KeyError, ValueError):
                pass
            continue

        index += 1

    return lines, polylines, circles


def all_points(
    lines: list[dict[str, object]],
    polylines: list[dict[str, object]],
    circles: list[dict[str, object]],
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for line in lines:
        points.append((float(line["x1"]), float(line["y1"])))
        points.append((float(line["x2"]), float(line["y2"])))
    for polyline in polylines:
        points.extend(polyline["points"])  # type: ignore[arg-type]
    for circle in circles:
        cx = float(circle["cx"])
        cy = float(circle["cy"])
        r = float(circle["r"])
        points.append((cx - r, cy - r))
        points.append((cx + r, cy + r))
    return points


def filter_outliers(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = sorted(x for x, _ in points)
    ys = sorted(y for _, y in points)
    if not xs or not ys:
        return 0, 0, 1, 1

    def percentile(values: list[float], ratio: float) -> float:
        return values[min(len(values) - 1, max(0, math.floor((len(values) - 1) * ratio)))]

    min_x = percentile(xs, 0.01)
    max_x = percentile(xs, 0.99)
    min_y = percentile(ys, 0.01)
    max_y = percentile(ys, 0.99)
    return min_x, min_y, max_x, max_y


def layer_class(layer: str) -> str:
    layer_lower = layer.lower()
    if "wall" in layer_lower or "벽" in layer_lower or "column" in layer_lower:
        return "wall"
    if "door" in layer_lower or "창호" in layer_lower or "window" in layer_lower:
        return "opening"
    if "dim" in layer_lower or "치수" in layer_lower:
        return "dim"
    return "line"


def line_svg(line: dict[str, object], bounds: tuple[float, float, float, float]) -> str:
    min_x, min_y, max_x, max_y = bounds
    x1 = float(line["x1"])
    y1 = float(line["y1"])
    x2 = float(line["x2"])
    y2 = float(line["y2"])
    if not (min_x <= x1 <= max_x and min_y <= y1 <= max_y and min_x <= x2 <= max_x and min_y <= y2 <= max_y):
        return ""
    klass = layer_class(str(line.get("layer", "")))
    return f'<line class="{klass}" x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" />'


def polyline_svg(polyline: dict[str, object], bounds: tuple[float, float, float, float]) -> str:
    min_x, min_y, max_x, max_y = bounds
    points = [
        (x, y)
        for x, y in polyline["points"]  # type: ignore[union-attr]
        if min_x <= x <= max_x and min_y <= y <= max_y
    ]
    if len(points) < 2:
        return ""
    d = " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
    tag = "polygon" if polyline.get("closed") else "polyline"
    klass = layer_class(str(polyline.get("layer", "")))
    return f'<{tag} class="{klass}" points="{d}" />'


def circle_svg(circle: dict[str, object], bounds: tuple[float, float, float, float]) -> str:
    min_x, min_y, max_x, max_y = bounds
    cx = float(circle["cx"])
    cy = float(circle["cy"])
    r = float(circle["r"])
    if not (min_x <= cx <= max_x and min_y <= cy <= max_y):
        return ""
    return f'<circle class="line" cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" />'


def write_svg(name: str, source_path: Path) -> None:
    pairs = read_pairs(source_path)
    section = extract_entities_section(pairs)
    lines, polylines, circles = convert_entities(section)
    points = all_points(lines, polylines, circles)
    min_x, min_y, max_x, max_y = filter_outliers(points)

    width = max_x - min_x
    height = max_y - min_y
    pad_x = width * 0.035
    pad_y = height * 0.035
    view_box = (min_x - pad_x, -(max_y + pad_y), width + pad_x * 2, height + pad_y * 2)
    bounds = (min_x, min_y, max_x, max_y)

    body = []
    body.extend(line_svg(line, bounds) for line in lines)
    body.extend(polyline_svg(polyline, bounds) for polyline in polylines)
    body.extend(circle_svg(circle, bounds) for circle in circles)
    body = [item for item in body if item]

    title = "구 마산헌병 분견대 평면도" if name == "main-floor" else "구 마산헌병 분견대 지하평면도"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box[0]:.3f} {view_box[1]:.3f} {view_box[2]:.3f} {view_box[3]:.3f}" role="img" aria-label="{html.escape(title)}">
  <title>{html.escape(title)}</title>
  <defs>
    <style>
      svg {{ background: #071017; }}
      .line {{ fill: none; stroke: #7f8b96; stroke-width: 22; vector-effect: non-scaling-stroke; stroke-linecap: square; stroke-linejoin: miter; opacity: 0.78; }}
      .wall {{ fill: none; stroke: #e6edf3; stroke-width: 34; vector-effect: non-scaling-stroke; stroke-linecap: square; stroke-linejoin: miter; opacity: 0.95; }}
      .opening {{ fill: none; stroke: #49a2d6; stroke-width: 20; vector-effect: non-scaling-stroke; stroke-linecap: square; stroke-linejoin: miter; opacity: 0.85; }}
      .dim {{ fill: none; stroke: #46525f; stroke-width: 12; vector-effect: non-scaling-stroke; stroke-linecap: square; stroke-linejoin: miter; opacity: 0.35; }}
    </style>
  </defs>
  <g transform="scale(1,-1)">
    {chr(10).join(body)}
  </g>
</svg>
'''
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{name}.svg").write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_DIR / f'{name}.svg'} ({len(body)} entities)")


def main() -> None:
    for name, path in DRAWINGS.items():
        write_svg(name, path)


if __name__ == "__main__":
    main()
