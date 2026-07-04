import type { Point } from "../store/projectStore";

type Seg = { x1: number; y1: number; x2: number; y2: number };

function toSeg(p: Point, q: Point): Seg {
  return { x1: Number(p.x), y1: Number(p.y), x2: Number(q.x), y2: Number(q.y) };
}

function cross(ax: number, ay: number, bx: number, by: number): number {
  return ax * by - ay * bx;
}

function segmentsIntersect(a: Seg, b: Seg): boolean {
  const dx1 = a.x2 - a.x1, dy1 = a.y2 - a.y1;
  const dx2 = b.x2 - b.x1, dy2 = b.y2 - b.y1;

  const d = cross(dx1, dy1, dx2, dy2);
  const t_num = cross(b.x1 - a.x1, b.y1 - a.y1, dx2, dy2);
  const u_num = cross(b.x1 - a.x1, b.y1 - a.y1, dx1, dy1);

  if (Math.abs(d) < 1e-10) return false; // параллельные

  const t = t_num / d;
  const u = u_num / d;
  return t > 0 && t < 1 && u > 0 && u < 1;
}

// Возвращает Set индексов рёбер, участвующих в пересечении.
// Ребро i соединяет points[i] и points[(i+1) % n].
export function getSelfIntersectingEdges(points: Point[]): Set<number> {
  const n = points.length;
  const bad = new Set<number>();
  if (n < 4) return bad;

  for (let i = 0; i < n; i++) {
    const a = toSeg(points[i], points[(i + 1) % n]);
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue; // смежные рёбра
      const b = toSeg(points[j], points[(j + 1) % n]);
      if (segmentsIntersect(a, b)) {
        bad.add(i);
        bad.add(j);
      }
    }
  }
  return bad;
}

export function hasSelfIntersection(points: Point[]): boolean {
  return getSelfIntersectingEdges(points).size > 0;
}

export function validateHeight(height: number | string): string | null {
  if (height === "" || height === null || height === undefined) return null;
  const v = Number(height);
  if (isNaN(v) || v <= 0) return "Высота должна быть больше нуля";
  if (v > 10) return "Высота не должна превышать 10 м";
  return null;
}
