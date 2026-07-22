import type { MaterialItem } from "../types/estimate";

// Реальные SKU-варианты уровня (эконом/стандарт/премиум — РАЗНЫЕ товары, свой
// source_url) есть только у finish_key-позиций (#331): у них имена min/avg/max_item
// различаются. У коммодити-материалов (светильник, кабель, труба, плинтус,
// грунт/шпаклёвка) товар один на все уровни — вилка это лишь разброс цены ОДНОГО
// товара по магазинам, а не выбор уровня комплектации. Работы SKU-вариантов не имеют
// вовсе. Отсюда правило: показывать Эконом/Стандарт/Премиум и закрепление уровня —
// только когда hasTierVariants === true (#419).
export const hasTierVariants = (
  m: Pick<MaterialItem, "min_item" | "avg_item" | "max_item">,
): boolean =>
  new Set(
    [m.min_item?.name, m.avg_item?.name, m.max_item?.name].filter(
      (n): n is string => !!n,
    ),
  ).size > 1;
