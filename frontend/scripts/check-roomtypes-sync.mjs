#!/usr/bin/env node
/**
 * Проверяет синхронность docs/room-types.json и frontend/src/types/roomTypes.ts.
 * Падает с diff-выводом при расхождении.
 * Запускается как: node frontend/scripts/check-roomtypes-sync.mjs
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dir = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dir, "..", "..");

const jsonPath = resolve(ROOT, "docs", "room-types.json");
const tsPath = resolve(ROOT, "frontend", "src", "types", "roomTypes.ts");

const json = JSON.parse(readFileSync(jsonPath, "utf-8"));
const ts = readFileSync(tsPath, "utf-8");

let errors = [];

// ── 1. finishOptions ────────────────────────────────────────────────────────
const jsonFinish = json.finishOptions;
for (const [category, entries] of Object.entries(jsonFinish)) {
  for (const [key, label] of Object.entries(entries)) {
    if (!ts.includes(`"${key}"`)) {
      errors.push(`finishOptions.${category}.${key}: ключ "${key}" не найден в roomTypes.ts`);
    }
    if (!ts.includes(`"${label}"`)) {
      errors.push(`finishOptions.${category}.${key}: метка "${label}" не найдена в roomTypes.ts`);
    }
  }
}

// ── 2. roomTypes ───────────────────────────────────────────────────��─────────
const jsonRooms = json.roomTypes;
const roomKeys = Object.keys(jsonRooms);

for (const [roomKey, room] of Object.entries(jsonRooms)) {
  // Находим блок комнаты: ищем паттерн "roomKey: {" (ключ без кавычек в объекте)
  const blockPattern = new RegExp(`\\b${roomKey}\\s*:\\s*\\{`, "g");
  const blockMatch = blockPattern.exec(ts);
  if (!blockMatch) {
    errors.push(`roomTypes.${roomKey}: определение не найдено в roomTypes.ts`);
    continue;
  }

  // Определяем конец блока: следующий ключ комнаты или конец файла
  const nextKey = roomKeys[roomKeys.indexOf(roomKey) + 1];
  const blockEnd = nextKey
    ? (ts.indexOf(`${nextKey}:`, blockMatch.index) ?? ts.length)
    : ts.length;
  const roomSlice = ts.slice(blockMatch.index, blockEnd);

  // label
  if (!roomSlice.includes(`"${room.label}"`)) {
    errors.push(`roomTypes.${roomKey}.label: "${room.label}" не найден`);
  }

  // finish arrays
  for (const category of ["floor", "walls", "ceiling", "electric"]) {
    for (const key of room[category]) {
      if (!roomSlice.includes(`"${key}"`)) {
        errors.push(`roomTypes.${roomKey}.${category}: ключ "${key}" не найден`);
      }
    }
  }

  // plumbing
  const availableStr = `available: ${room.plumbing.available}`;
  const requiredStr = `required: ${room.plumbing.required}`;
  if (!roomSlice.includes(availableStr)) {
    errors.push(
      `roomTypes.${roomKey}.plumbing.available: ожидается ${room.plumbing.available}, не найдено`,
    );
  }
  if (!roomSlice.includes(requiredStr)) {
    errors.push(
      `roomTypes.${roomKey}.plumbing.required: ожидается ${room.plumbing.required}, не найдено`,
    );
  }
}

// ── Итог ────────────────────────────────────────────────────────────────────
if (errors.length > 0) {
  console.error("\n❌ roomTypes.ts расходится с docs/room-types.json:\n");
  for (const e of errors) {
    console.error("  •", e);
  }
  console.error(`\nВсего расхождений: ${errors.length}`);
  console.error(
    "Обновите frontend/src/types/roomTypes.ts вручную по образцу docs/room-types.json.\n",
  );
  process.exit(1);
}

console.log("✓ roomTypes.ts синхронен с docs/room-types.json");
