import type { Room } from "../store/projectStore";

// Единый источник правды валидации проёмов: им пользуются и форма (inline-ошибка
// под полем), и Workspace (блокировка кнопки расчёта), чтобы сообщения и правила
// не разъезжались между отображением и отправкой.

export function validateWidth(width: number | string): string | null {
  if (width === "" || width === null || width === undefined) return null;
  const v = Number(width);
  if (isNaN(v) || v <= 0) return "Должна быть > 0";
  if (v > 10) return "Не более 10 м";
  return null;
}

export function validateHeight(
  height: number | string,
  ceilingHeight: number | string,
): string | null {
  if (height === "" || height === null || height === undefined) return null;
  const v = Number(height);
  const ceiling = Number(ceilingHeight);
  if (isNaN(v) || v <= 0) return "Должна быть > 0";
  if (ceiling > 0 && v > ceiling) return `Не более ${ceiling} м (потолок)`;
  return null;
}

// Есть ли в комнате хоть один проём с некорректной шириной или высотой.
// Высота сверяется с высотой потолка этой же комнаты.
export function roomHasInvalidOpenings(room: Room): boolean {
  return room.openings.some(
    (op) =>
      validateWidth(op.width) !== null ||
      validateHeight(op.height, room.height) !== null,
  );
}
