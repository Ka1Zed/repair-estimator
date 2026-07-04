#!/usr/bin/env node
/**
 * Проверяет синхронность docs/room-types.json и frontend/src/types/roomTypes.ts.
 * Сверка двусторонняя и по-категорийная: ловит и пропажу, и лишний/переехавший
 * ключ. Падает с diff-выводом при расхождении.
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

const errors = [];
const FINISH_CATEGORIES = ["floor", "walls", "ceiling", "electric"];

// ── Хелперы парсинга TS ──────────────────────────────────────────────────────

/** Вырезает сбалансированный по скобкам блок, начиная с символа open по индексу. */
function sliceBalanced(text, startIdx, open, close) {
  let depth = 0;
  for (let i = startIdx; i < text.length; i++) {
    if (text[i] === open) depth++;
    else if (text[i] === close) {
      depth--;
      if (depth === 0) return text.slice(startIdx, i + 1);
    }
  }
  return null;
}

/** Возвращает блок `name = { … }` (первое присваивание объекта) или null. */
function objectBlock(text, name) {
  const m = new RegExp(`\\b${name}\\b[^={]*=\\s*\\{`).exec(text);
  if (!m) return null;
  const braceIdx = text.indexOf("{", m.index);
  return sliceBalanced(text, braceIdx, "{", "}");
}

/** Блок объекта по ключу внутри родителя: `key: { … }`. */
function nestedObject(text, key) {
  const m = new RegExp(`\\b${key}\\s*:\\s*\\{`).exec(text);
  if (!m) return null;
  const braceIdx = text.indexOf("{", m.index);
  return sliceBalanced(text, braceIdx, "{", "}");
}

/** Ключи из массива `key: [ "a", "b" ]` внутри блока. null — массив не найден. */
function arrayKeys(text, key) {
  const m = new RegExp(`\\b${key}\\s*:\\s*\\[`).exec(text);
  if (!m) return null;
  const bracketIdx = text.indexOf("[", m.index);
  const slice = sliceBalanced(text, bracketIdx, "[", "]");
  if (slice === null) return null;
  return [...slice.matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

/** Пары ключ→метка из плоского объектного блока `{ a: "A", b: "B" }`. */
function labelMap(block) {
  const out = {};
  for (const m of block.matchAll(/(\w+)\s*:\s*"([^"]+)"/g)) out[m[1]] = m[2];
  return out;
}

/** Булев по ключу `key: true|false` внутри блока или null. */
function boolValue(text, key) {
  const m = new RegExp(`\\b${key}\\s*:\\s*(true|false)`).exec(text);
  return m ? m[1] === "true" : null;
}

/** Двусторонняя сверка множеств ключей. */
function diffKeys(jsonArr, tsArr, ctx) {
  if (tsArr === null) {
    errors.push(`${ctx}: массив не найден в roomTypes.ts`);
    return;
  }
  const j = new Set(jsonArr);
  const t = new Set(tsArr);
  for (const k of j) if (!t.has(k)) errors.push(`${ctx}: "${k}" есть в JSON, нет в TS`);
  for (const k of t) if (!j.has(k)) errors.push(`${ctx}: "${k}" есть в TS, нет в JSON`);
}

// ── 1. finishOptions ─────────────────────────────────────────────────────────
const finishBlock = objectBlock(ts, "finishOptions");
if (!finishBlock) {
  errors.push("finishOptions: блок не найден в roomTypes.ts");
} else {
  for (const [category, entries] of Object.entries(json.finishOptions)) {
    const catBlock = nestedObject(finishBlock, category);
    if (!catBlock) {
      errors.push(`finishOptions.${category}: категория не найдена в TS`);
      continue;
    }
    const tsMap = labelMap(catBlock);
    for (const [key, label] of Object.entries(entries)) {
      if (!(key in tsMap)) {
        errors.push(`finishOptions.${category}.${key}: ключ есть в JSON, нет в TS`);
      } else if (tsMap[key] !== label) {
        errors.push(
          `finishOptions.${category}.${key}: метка "${tsMap[key]}" в TS ≠ "${label}" в JSON`,
        );
      }
    }
    for (const key of Object.keys(tsMap)) {
      if (!(key in entries)) {
        errors.push(`finishOptions.${category}.${key}: ключ есть в TS, нет в JSON`);
      }
    }
  }
}

// ── 2. roomTypes ─────────────────────────────────────────────────────────────
const roomsBlock = objectBlock(ts, "roomTypes");
if (!roomsBlock) {
  errors.push("roomTypes: блок не найден в roomTypes.ts");
} else {
  const jsonRooms = json.roomTypes;

  // Множество ключей комнат: только `key: {` на глубине 1 (не вложенные plumbing и т.п.).
  const tsRoomKeys = new Set();
  for (const m of roomsBlock.matchAll(/(\w+)\s*:\s*\{/g)) {
    let depth = 0;
    for (let i = 0; i < m.index; i++) {
      if (roomsBlock[i] === "{") depth++;
      else if (roomsBlock[i] === "}") depth--;
    }
    if (depth === 1) tsRoomKeys.add(m[1]);
  }
  diffKeys(Object.keys(jsonRooms), [...tsRoomKeys], "roomTypes: набор комнат");

  for (const [roomKey, room] of Object.entries(jsonRooms)) {
    const start = new RegExp(`\\b${roomKey}\\s*:\\s*\\{`).exec(roomsBlock);
    if (!start) {
      errors.push(`roomTypes.${roomKey}: определение не найдено в TS`);
      continue;
    }
    const braceIdx = roomsBlock.indexOf("{", start.index);
    const roomBlock = sliceBalanced(roomsBlock, braceIdx, "{", "}");
    if (roomBlock === null) {
      errors.push(`roomTypes.${roomKey}: не удалось разобрать блок`);
      continue;
    }

    // label
    const labelMatch = /label\s*:\s*"([^"]+)"/.exec(roomBlock);
    if (!labelMatch) {
      errors.push(`roomTypes.${roomKey}.label: не найден в TS`);
    } else if (labelMatch[1] !== room.label) {
      errors.push(
        `roomTypes.${roomKey}.label: "${labelMatch[1]}" в TS ≠ "${room.label}" в JSON`,
      );
    }

    // finish arrays — по категориям, двусторонне
    for (const category of FINISH_CATEGORIES) {
      diffKeys(room[category], arrayKeys(roomBlock, category), `roomTypes.${roomKey}.${category}`);
    }

    // plumbing
    const plumbBlock = nestedObject(roomBlock, "plumbing");
    if (!plumbBlock) {
      errors.push(`roomTypes.${roomKey}.plumbing: блок не найден в TS`);
    } else {
      for (const flag of ["available", "required"]) {
        const tsVal = boolValue(plumbBlock, flag);
        if (tsVal !== room.plumbing[flag]) {
          errors.push(
            `roomTypes.${roomKey}.plumbing.${flag}: ${tsVal} в TS ≠ ${room.plumbing[flag]} в JSON`,
          );
        }
      }
    }
  }
}

// ── Итог ─────────────────────────────────────────────────────────────────────
if (errors.length > 0) {
  console.error("\n❌ roomTypes.ts расходится с docs/room-types.json:\n");
  for (const e of errors) console.error("  •", e);
  console.error(`\nВсего расхождений: ${errors.length}`);
  console.error(
    "Синхронизируйте frontend/src/types/roomTypes.ts с docs/room-types.json.\n",
  );
  process.exit(1);
}

console.log("✓ roomTypes.ts синхронен с docs/room-types.json");
