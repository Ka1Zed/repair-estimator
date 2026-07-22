import logging
from decimal import Decimal
from math import ceil
from typing import Dict, List, Any, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import PriceSource, MaterialPrice
from app.schemas.estimate import (
    EstimateRequest, EstimateResponse, Summary, GeometrySummary,
    MaterialItem, MaterialTierItem, LaborItem, HiddenWorks, HiddenWorkItem, RoomInput,
)
from app.services.geometry_service import calculate_room_geometry
from app.services.material_calc_service import (
    calculate_materials, calculate_engineering_materials, packs_to_buy, resolve_material,
)
from app.services.labor_calc_service import (
    calculate_labor, calculate_engineering_labor, calculate_rough_labor,
    WET_ROOM_TYPES,
)
from app.services.repair_coeffs_service import CONTINGENCY
from app.services.category_match import detect_category_mismatch
from app.services.price_aggregator_service import get_material_price, get_labor_price
from app.services.hidden_works_service import calculate_hidden_works
from app.parsers.base import BaseParser
from app.parsers.registry import MATERIAL_PARSERS, REGIONAL_MATERIAL_PARSERS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/estimates", tags=["estimates"])


def get_material_parsers() -> list[BaseParser]:
    '''Все зарегистрированные источники цен материалов для расчёта сметы.

    Вынесена в зависимость FastAPI, чтобы тесты могли подменить список заглушкой
    (app.dependency_overrides) и не ходить в сеть. В проде — базовые парсеры из
    app.parsers.registry.MATERIAL_PARSERS (Мегастрой, Леман-Казань) плюс
    региональные (#345, REGIONAL_MATERIAL_PARSERS — Леман для Москвы/СПб);
    get_material_price сам выбирает, какие из них применимы к запрошенному
    городу (_select_regional_parsers), и объединяет их цены в одну вилку (#333).
    '''
    return MATERIAL_PARSERS + REGIONAL_MATERIAL_PARSERS

# Дефолты инженерки, когда группа works включена, а число не задано (null).
# Явный 0 остаётся 0 (осознанный ноль). База — пресеты по типу комнаты; для типа
# без пресета число выводится от площади пола. Источник правды — docs/estimation-rules.md.
# electric: (розетки, светильники) по типу комнаты; plumbing: число точек подключения.
ELECTRICAL_POINTS = {
    "living":   (8, 3),
    "kitchen":  (12, 4),
    "bathroom": (4, 2),
    "hallway":  (3, 2),
}
PLUMBING_POINTS = {
    "kitchen":  1,
    "bathroom": 3,
}
# Погонаж на точку для дефолтного метража, когда cable_m/pipe_m не заданы.
CABLE_M_PER_POINT = Decimal("6")
PIPE_M_PER_POINT = Decimal("3")


def _default_electric(room_type: str, floor_area: Decimal) -> Tuple[int, int]:
    """Дефолтное число розеток и светильников: пресет типа или оценка от площади."""
    if room_type in ELECTRICAL_POINTS:
        return ELECTRICAL_POINTS[room_type]
    fa = float(floor_area)
    return max(2, ceil(fa / 4)), max(1, ceil(fa / 6))


def _resolve_electric(room: RoomInput, floor_area: Decimal) -> Tuple[int, int, Decimal]:
    """Явные числа works.electric или дефолты (розетки, светильники, метраж кабеля)."""
    e = room.works.electric
    if not e.enabled:
        return 0, 0, Decimal(0)
    def_sockets, def_lights = _default_electric(room.room_type, floor_area)
    sockets = e.sockets if e.sockets is not None else def_sockets
    lights = e.lights if e.lights is not None else def_lights
    if e.cable_m is not None:
        cable_m = Decimal(str(e.cable_m))
    else:
        cable_m = (Decimal(sockets) + Decimal(lights)) * CABLE_M_PER_POINT
    return sockets, lights, cable_m


def _resolve_stretch_ceiling(room: RoomInput, floor_area: Decimal) -> Tuple[int, Decimal]:
    """Параметры натяжного потолка (#191): закладные под светильники и ниша под штору.

    light_points по умолчанию = дефолтное число светильников типа комнаты (натяжной
    самодостаточен, число НЕ берётся из блока electric). curtain_niche_m по умолчанию 0.
    """
    c = room.works.ceiling
    _, def_lights = _default_electric(room.room_type, floor_area)
    light_points = c.light_points if c.light_points is not None else def_lights
    niche = Decimal(str(c.curtain_niche_m)) if c.curtain_niche_m is not None else Decimal(0)
    return light_points, niche


def _resolve_plumbing(room: RoomInput) -> Tuple[int, Decimal]:
    """Явные числа works.plumbing или дефолты (точки, метраж труб)."""
    p = room.works.plumbing
    if not p.enabled:
        return 0, Decimal(0)
    def_points = PLUMBING_POINTS.get(room.room_type)
    if def_points is None:
        def_points = 1  # тип без пресета, но сантехника включена явно
    points = p.points if p.points is not None else def_points
    pipe_m = Decimal(str(p.pipe_m)) if p.pipe_m is not None else Decimal(points) * PIPE_M_PER_POINT
    return points, pipe_m


def _finish_options(room: RoomInput) -> Dict[str, Any]:
    """works отделки (floor/walls/ceiling) → dict для calculate_materials/labor."""
    w = room.works

    def finish(sw) -> Any:
        return sw.finish if sw.enabled else None

    return {
        "floor": finish(w.floor),
        "walls": finish(w.walls),
        "ceiling": finish(w.ceiling),
        # Модификаторы живут на уровне поверхности. primer_two_coats — отдельно
        # для стен и потолка (#380): один флаг на обе поверхности перетирал бы
        # выбор одной из них при одновременной покраске стен и потолка.
        "wallpaper_pattern": bool(w.walls.enabled and w.walls.wallpaper_pattern),
        "primer_two_coats": bool(w.walls.enabled and w.walls.primer_two_coats),
        "ceiling_primer_two_coats": bool(w.ceiling.enabled and w.ceiling.primer_two_coats),
        "wall_condition": w.walls.wall_condition if w.walls.enabled else None,
    }


def _safe_package_size(value: Any) -> Decimal:
    """Фасовка материала защищённо: Material.package_size nullable, поэтому
    None и <=0 (в т.ч. Decimal(str(None)), падающий InvalidOperation) сводим
    к безопасному дефолту — 1 (штучная покупка), а не даём final_quantity
    обнулиться от умножения на 0."""
    if value is None:
        return Decimal(1)
    package_size = Decimal(str(value))
    return package_size if package_size > 0 else Decimal(1)


def pick_by_tier(tier: str, v_min: Decimal, v_avg: Decimal, v_max: Decimal) -> Decimal:
    """Выбирает значение в зависимости от уровня комплектации."""
    if tier == "min":
        return v_min
    if tier == "max":
        return v_max
    return v_avg


def _cached_material_price(
    cache: Dict[tuple, "MaterialPrice | None"], material_name: str, db: Session,
    parsers: list[BaseParser], region: str, store_names: List[str] | None,
) -> MaterialPrice | None:
    """get_material_price с мемоизацией в пределах одного /calculate.

    Одна позиция материала запрашивается до 3 раз за запрос: основная строка +
    min_item/max_item (см. _tier_item). Когда tier-варианты SKU не заведены,
    resolve_material для всех трёх уровней отдаёт один и тот же товар → три
    идентичных прохода get_material_price (цикл по парсерам + запросы к БД).
    Кэшируем по (материал, город, магазины) — ключ, полностью определяющий
    результат в рамках запроса; объект только читается вызывающими, не мутируется.
    """
    key = (material_name, region, tuple(store_names) if store_names else None)
    if key not in cache:
        cache[key] = get_material_price(
            material_name, db=db, parsers=parsers, region=region, store_names=store_names,
        )
    return cache[key]


def _tier_item(
    material_key: str, tier: str, needed_quantity: Decimal, db: Session,
    parsers: list[BaseParser], region: str, sources_by_id: Dict[int, str],
    price_cache: Dict[tuple, "MaterialPrice | None"], store_names: List[str] | None = None,
) -> MaterialTierItem:
    """SKU-вариант позиции для одного уровня комплектации (#349, min_item/avg_item/max_item).

    Резолвит SKU так же, как сама строка материала (resolve_material — с fallback
    на ближайший уровень, если у finish_key нет варианта именно этого tier), затем
    берёт цену тем же путём (get_material_price) и той же арифметикой band'ов
    (pick_by_tier), что и основной расчёт строки — числа обязаны совпасть с тем,
    что вернул бы отдельный /calculate с этим tier. needed_quantity — общая с
    родительской строкой потребность (base×waste ДО округления до упаковок): её
    округляем вверх до упаковок фасовкой ЭТОГО SKU (#306/#349), иначе стандарт и
    премиум с разной фасовкой (9 л против 10 л, плинтус 2.5 м против 3 м) показали бы
    одну и ту же «× N ед.» из родительской строки. Доп. обращений к БД/парсеру сверх
    обычных для resolve_material/get_material_price нет. price_cache — общий с
    основным циклом мемо цен (см. _cached_material_price).
    """
    material = resolve_material(db, material_key, tier)
    if material is None:
        return MaterialTierItem(name="", price=0.0, total=0.0, source="нет цены", source_url=None)

    ref_package_size = _safe_package_size(material.package_size)
    price_obj = _cached_material_price(
        price_cache, material.name, db, parsers, region, store_names,
    )
    if not price_obj:
        return MaterialTierItem(
            name=material.name, price=0.0, total=0.0, source="нет цены", source_url=None,
            unit=material.unit or "", package_size=float(ref_package_size),
        )

    # Фасовка КОНКРЕТНОГО товара за source_url (#306), иначе справочная у SKU.
    effective_package_size = (
        _safe_package_size(price_obj.package_size)
        if price_obj.package_size else ref_package_size
    )
    packs = packs_to_buy(needed_quantity / effective_package_size)
    final_quantity = Decimal(packs) * effective_package_size

    # Границы вилки SKU уже прижаты к коридору per-source внутри
    # get_material_price/_combine (#411) — здесь берём готовые price_min/max, та же
    # арифметика, что в основной строке, иначе числа min_item/max_item разошлись бы
    # с ответом отдельного /calculate с этим tier.
    price = pick_by_tier(tier, price_obj.price_min, price_obj.price_avg, price_obj.price_max)
    total = final_quantity * price * CONTINGENCY[tier]
    return MaterialTierItem(
        name=material.name,
        price=float(price),
        total=float(total),
        source=sources_by_id.get(price_obj.source_id, "unknown"),
        source_url=price_obj.source_url,
        unit=material.unit or "",
        package_size=float(effective_package_size),
        quantity=float(final_quantity),
        packs=packs,
        category_mismatch=detect_category_mismatch(
            price_obj.source_url, material.category_exclusions
        ),
    )

# tier выбирает границу вилки (min/avg/max) уже ВЫБРАННОГО SKU-варианта.
# Выбор самого варианта (эконом/стандарт/премиум — разные Material с одним
# finish_key) происходит раньше, в calculate_materials/_resolve_material (#331) —
# сюда попадает готовая цена одного конкретного товара.

@router.post("/calculate", response_model=EstimateResponse)
def calculate_estimate(
    request: EstimateRequest,
    db: Session = Depends(get_db),
    parsers: list[BaseParser] = Depends(get_material_parsers),
) -> EstimateResponse:
    # Источники цен — маленький справочник (~10 строк), грузим один раз вместо
    # точечного запроса на каждую строку материала/работы (устраняет N+1, #278).
    sources_by_id = {s.id: s.name for s in db.query(PriceSource).all()}

    # Валидация request.stores (#363): опечатка/несуществующий магазин не должна
    # молча откатываться на автоподбор — get_material_price не различает "магазин
    # не покрывает город" (штатный откат) и "такого магазина вообще нет"
    # (ошибка клиента). Проверяем по ПОЛНОМУ списку зарегистрированных парсеров
    # (без учёта города), а не по _select_regional_parsers — иначе валидный, но
    # непокрывающий город магазин ложно считался бы неизвестным.
    if request.stores:
        known_stores = {p.source_name for p in parsers}
        unknown_stores = sorted(set(request.stores) - known_stores)
        if unknown_stores:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Неизвестный магазин(ы) в stores: {', '.join(unknown_stores)}. "
                    f"Доступные магазины: {', '.join(sorted(known_stores))}."
                ),
            )

    # Мемо цен материалов на весь запрос: одну позицию смета запрашивает до 3 раз
    # (основная строка + min_item/max_item), а get_material_price каждый раз заново
    # гоняет цикл по парсерам и запросы к БД. Ключ полностью определяет результат
    # в пределах запроса (см. _cached_material_price).
    material_price_cache: Dict[tuple, "MaterialPrice | None"] = {}

    all_materials: List[Dict[str, Any]] = []
    all_labor: List[Dict[str, Any]] = []
    total_geometry = {
        'floor_area': Decimal(0),
        'ceiling_area': Decimal(0),
        'wall_area': Decimal(0),
        'perimeter': Decimal(0),
    }
    # Аккумуляторы для блока скрытых работ (#239): флаги сценария и объёмы, не
    # входящие в summary — считаются отдельно, поверх основной сметы.
    hidden = {'has_floor': False, 'has_walls': False, 'has_electric': False,
              'cable_m': Decimal(0), 'wet_floor': Decimal(0)}

    for room in request.rooms:
        try:
            geometry = calculate_room_geometry(
                points=[(p.x, p.y) for p in room.points],
                height=room.height,
                openings=[(o.type, o.width, o.height, o.depth) for o in room.openings],
                ceiling_shape=room.ceiling_shape.model_dump() if room.ceiling_shape else None,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

        for key in total_geometry:
            total_geometry[key] += Decimal(str(geometry[key]))

        # --- отделка (finish) по works комнаты ---
        finish_options = _finish_options(room)

        # Натяжной потолок (#191): закладные под светильники и ниша под штору —
        # отдельные строки потолочника, а не множитель площади. Считаем параметры
        # тут (нужна floor_area для дефолта светильников) и кладём в finish_options.
        if finish_options["ceiling"] == "stretch":
            light_points, curtain_niche_m = _resolve_stretch_ceiling(
                room, geometry['floor_area']
            )
            finish_options["ceiling_light_points"] = light_points
            finish_options["ceiling_curtain_niche_m"] = curtain_niche_m

        # Флаги сценария для скрытых работ (#239): по фактически выбранной отделке.
        if finish_options["floor"]:
            hidden['has_floor'] = True
        if finish_options["walls"]:
            hidden['has_walls'] = True
        # rough_only (#303): чистовая отделка и её материалы не считаются, остаётся
        # предчистовая подготовка (шпаклёвка стен, грунт/стартовая шпаклёвка материалом).
        include_finish = request.scope != "rough_only"
        all_materials.extend(calculate_materials(
            geometry=geometry, repair_options=finish_options, db=db,
            include_finish=include_finish, tier=request.tier,
        ))
        all_labor.extend(calculate_labor(
            geometry=geometry, repair_options=finish_options, db=db,
            sources_by_id=sources_by_id, include_finish=include_finish,
        ))

        # --- черновые работы (#190, #303): при rough_and_finish и rough_only ---
        if request.scope in ("rough_and_finish", "rough_only"):
            all_labor.extend(calculate_rough_labor(
                geometry=geometry, repair_options=finish_options,
                room_type=room.room_type, db=db,
                sources_by_id=sources_by_id,
            ))

        # --- инженерка по явным числам works (дефолты от типа/площади) ---
        sockets, lights, cable_m = _resolve_electric(room, geometry['floor_area'])
        points, pipe_m = _resolve_plumbing(room)

        # Накопить драйверы скрытых работ (#239): штробы под кабель, мокрая зона.
        if cable_m > 0:
            hidden['has_electric'] = True
            hidden['cable_m'] += cable_m
        # Гидроизоляция всплывает только по мокрой зоне — копим площадь пола
        # именно мокрых комнат, а не общий метраж (иначе вилка завышена).
        if points > 0 or room.room_type in WET_ROOM_TYPES:
            hidden['wet_floor'] += Decimal(str(geometry['floor_area']))
        all_materials.extend(calculate_engineering_materials(
            sockets=sockets, lights=lights, cable_m=cable_m, pipe_m=pipe_m, db=db,
            include_finish=include_finish, tier=request.tier,
        ))
        all_labor.extend(calculate_engineering_labor(
            sockets=sockets, lights=lights, cable_m=cable_m,
            plumbing_points=points, pipe_m=pipe_m, db=db,
            sources_by_id=sources_by_id, include_finish=include_finish,
        ))

    # Агрегация материалов с округлением до упаковок
    mat_groups: Dict[int, Dict] = {}
    for mat in all_materials:
        mid = mat['material_id']
        if mid not in mat_groups:
            mat_groups[mid] = {
                'name': mat['name'],
                'material_key': mat['material_key'],
                'unit': mat['unit'],
                'package_size': _safe_package_size(mat.get('package_size')),
                'quantity': Decimal(0),
                'base_quantity': Decimal(0),
                'pack_quantity': Decimal(0),
            }
        mat_groups[mid]['quantity'] += mat['quantity']
        mat_groups[mid]['base_quantity'] += mat['base_quantity']
        if mat.get('pack_quantity') is not None:
            mat_groups[mid]['pack_quantity'] += mat['pack_quantity']

    materials_response: List[MaterialItem] = []
    materials_sum = {'min': Decimal(0), 'avg': Decimal(0), 'max': Decimal(0)}

    for mid, group in mat_groups.items():
        name = group['name']
        base_quantity = group['base_quantity']
        # Эффективный запас группы: quantity/base_quantity — по построению совпадает
        # с накрученным по факту коэффициентом даже после суммирования нескольких комнат.
        waste_factor = (group['quantity'] / base_quantity) if base_quantity > 0 else Decimal(1)

        price_obj = _cached_material_price(
            material_price_cache, name, db, parsers, request.city, request.stores,
        )

        # package_size (#306): если цена пришла от парсера и он отдал фасовку
        # КОНКРЕТНОГО товара за source_url — считаем упаковки по ней, а не по
        # справочной Material.package_size, иначе то, что показано по ссылке,
        # и то, что легло в расчёт, могут разойтись (краска 2.5 л на карточке
        # против 9 л в смете). Нет цены/фасовки от парсера — прежнее поведение.
        effective_package_size = (
            _safe_package_size(price_obj.package_size)
            if price_obj is not None and price_obj.package_size
            else group['package_size']
        )
        packs = packs_to_buy(group['quantity'] / effective_package_size)
        final_quantity = Decimal(packs) * effective_package_size

        if not price_obj:
            logger.warning(f"Цена для материала '{name}' не найдена, показываем без цены")
            no_price_item = MaterialTierItem(
                name=name, price=0.0, total=0.0, source="нет цены", source_url=None,
                unit=group['unit'], package_size=float(effective_package_size),
                quantity=float(final_quantity), packs=packs,
            )
            materials_response.append(MaterialItem(
                name=name,
                quantity=float(final_quantity),
                base_quantity=float(base_quantity),
                waste_factor=float(waste_factor),
                package_size=float(effective_package_size),
                packs=packs,
                unit=group['unit'],
                tier=request.tier,
                price=0.0,
                total=0.0,
                price_min=0.0,
                price_avg=0.0,
                price_max=0.0,
                total_min=0.0,
                total_avg=0.0,
                total_max=0.0,
                source="нет цены",
                source_url=None,
                updated_at="",
                region=None,
                min_item=no_price_item,
                avg_item=no_price_item,
                max_item=no_price_item,
            ))
            continue

        price_avg = price_obj.price_avg
        # Категорийный band каждого источника уже прижат к коридору per-source внутри
        # get_material_price/_combine (#411); межисточниковая дисперсия прошла как есть,
        # межтоварный разброс уровней остаётся в min_item/max_item. Здесь — готовые границы.
        price_min = price_obj.price_min
        price_max = price_obj.price_max
        source_name = sources_by_id.get(price_obj.source_id, "unknown")
        updated_at = price_obj.updated_at.strftime("%Y-%m-%d") if price_obj.updated_at else ""
        # min_source/max_source — «источник, чья цена реально стала границей» (#348).
        # _combine уже занулил их, если границу задал кламп или это сам представитель.
        min_source_id = getattr(price_obj, "min_source_id", None)
        max_source_id = getattr(price_obj, "max_source_id", None)
        min_source_name = sources_by_id.get(min_source_id) if min_source_id else None
        max_source_name = sources_by_id.get(max_source_id) if max_source_id else None
        total_min = final_quantity * price_min * CONTINGENCY['min']
        total_avg = final_quantity * price_avg * CONTINGENCY['avg']
        total_max = final_quantity * price_max * CONTINGENCY['max']

        price = pick_by_tier(request.tier, price_min, price_avg, price_max)
        total = pick_by_tier(request.tier, total_min, total_avg, total_max)

        # min_item/avg_item/max_item (#349): для request.tier переиспользуем уже
        # посчитанные выше price/total/source — без лишнего resolve_material/
        # get_material_price; для двух остальных уровней резолвим SKU-вариант
        # тем же путём, что и основной расчёт (_tier_item).
        # Товар текущего tier из смежной категории (#406) — сверяем slug
        # source_url с category_exclusions резолвленного материала. Материал
        # берём по material_key/tier тем же путём, что и _tier_item (мемо
        # resolve_material тут не нужно — вызов дешёвый).
        current_material = resolve_material(db, group['material_key'], request.tier)
        current_mismatch = detect_category_mismatch(
            price_obj.source_url,
            current_material.category_exclusions if current_material else None,
        )
        current_tier_item = MaterialTierItem(
            name=name, price=float(price), total=float(total),
            source=source_name, source_url=price_obj.source_url,
            unit=group['unit'], package_size=float(effective_package_size),
            quantity=float(final_quantity), packs=packs,
            category_mismatch=current_mismatch,
        )
        tier_items = {request.tier: current_tier_item}
        for t in ("min", "avg", "max"):
            if t not in tier_items:
                # Потребность (не округлённая): каждый SKU округляет её вверх до
                # СВОИХ упаковок — фасовки уровней различаются (#306/#349).
                tier_items[t] = _tier_item(
                    group['material_key'], t, group['quantity'], db, parsers,
                    request.city, sources_by_id, material_price_cache,
                    store_names=request.stores,
                )

        materials_response.append(MaterialItem(
            name=name,
            quantity=float(final_quantity),
            base_quantity=float(base_quantity),
            waste_factor=float(waste_factor),
            package_size=float(effective_package_size),
            packs=packs,
            unit=group['unit'],
            tier=request.tier,
            price=float(price),
            total=float(total),
            price_min=float(price_min),
            price_avg=float(price_avg),
            price_max=float(price_max),
            total_min=float(total_min),
            total_avg=float(total_avg),
            total_max=float(total_max),
            source=source_name,
            source_url=price_obj.source_url,
            updated_at=updated_at,
            region=price_obj.region,
            sources=getattr(price_obj, "contributing_sources", None),
            min_source=min_source_name,
            min_source_url=getattr(price_obj, "min_source_url", None),
            max_source=max_source_name,
            max_source_url=getattr(price_obj, "max_source_url", None),
            min_item=tier_items["min"],
            avg_item=tier_items["avg"],
            max_item=tier_items["max"],
            category_mismatch=current_mismatch,
        ))

        materials_sum['min'] += final_quantity * price_min
        materials_sum['avg'] += final_quantity * price_avg
        materials_sum['max'] += final_quantity * price_max

    # Агрегация работ
    labor_groups: Dict[str, Dict] = {}
    for job in all_labor:
        service = job['service']
        if service not in labor_groups:
            labor_groups[service] = {
                'specialist': job['specialist'],
                'stage': job['stage'],
                'unit': job['unit'],
                'volume': Decimal(0),
            }
        labor_groups[service]['volume'] += job['volume']

    labor_response: List[LaborItem] = []
    labor_sum = {'min': Decimal(0), 'avg': Decimal(0), 'max': Decimal(0)}

    for service, group in labor_groups.items():
        labor_price = get_labor_price(service, db=db, region=request.city)
        if not labor_price:
            continue

        volume = group['volume']
        p_avg = labor_price.price_avg
        # Band каждого сайта уже прижат к коридору per-source внутри get_labor_price/
        # _combine (#411); межсайтовая (межподрядная) дисперсия прошла как есть — у
        # работ это единственный канал реального разброса (tier-вариантов нет).
        p_min = labor_price.price_min
        p_max = labor_price.price_max

        # Применяем непредвиденные расходы для каждой границы
        total_min = volume * p_min * CONTINGENCY['min']
        total_avg = volume * p_avg * CONTINGENCY['avg']
        total_max = volume * p_max * CONTINGENCY['max']

        # Выбор цены и итога для текущего уровня (tier)
        price = pick_by_tier(request.tier, p_min, p_avg, p_max)
        total = pick_by_tier(request.tier, total_min, total_avg, total_max)

        labor_source_name = sources_by_id.get(labor_price.source_id, "seed")
        updated_at = labor_price.updated_at.strftime("%Y-%m-%d") if labor_price.updated_at else ""
        # Источник границы (#348): _combine уже занулил, если границу задал кламп
        # или это сам представитель.
        labor_min_source_id = getattr(labor_price, "min_source_id", None)
        labor_max_source_id = getattr(labor_price, "max_source_id", None)
        labor_min_source_name = sources_by_id.get(labor_min_source_id) if labor_min_source_id else None
        labor_max_source_name = sources_by_id.get(labor_max_source_id) if labor_max_source_id else None

        labor_response.append(LaborItem(
            service=service,
            specialist=group['specialist'],
            stage=group['stage'],
            volume=float(volume),
            unit=group['unit'],
            tier=request.tier,
            price=float(price),
            total=float(total),
            price_min=float(p_min),
            price_avg=float(p_avg),
            price_max=float(p_max),
            total_min=float(total_min),
            total_avg=float(total_avg),
            total_max=float(total_max),
            source=labor_source_name,
            updated_at=updated_at,
            source_url=labor_price.source_url,
            region=labor_price.region,
            sources=getattr(labor_price, "contributing_sources", None),
            min_source=labor_min_source_name,
            min_source_url=getattr(labor_price, "min_source_url", None),
            max_source=labor_max_source_name,
            max_source_url=getattr(labor_price, "max_source_url", None),
        ))

        labor_sum['min'] += volume * p_min
        labor_sum['avg'] += volume * p_avg
        labor_sum['max'] += volume * p_max
    # Итог = материалы + работы, каждый со своим запасом на непредвиденные (CONTINGENCY).
    # Классового множителя ремонта больше нет (#222).
    mat_final = {k: materials_sum[k] * CONTINGENCY[k] for k in ('min', 'avg', 'max')}
    lab_final = {k: labor_sum[k] * CONTINGENCY[k] for k in ('min', 'avg', 'max')}

    summary = Summary(
        materials_min=float(mat_final['min']),
        materials_avg=float(mat_final['avg']),
        materials_max=float(mat_final['max']),
        labor_min=float(lab_final['min']),
        labor_avg=float(lab_final['avg']),
        labor_max=float(lab_final['max']),
        total_min=float(mat_final['min'] + lab_final['min']),
        total_avg=float(mat_final['avg'] + lab_final['avg']),
        total_max=float(mat_final['max'] + lab_final['max']),
    )

    # Блок «может всплыть доплатой» (#239): считается поверх основной сметы и
    # НЕ входит в summary. Объёмы — суммарная геометрия сценария, цены — seed-работы.
    hidden_raw = calculate_hidden_works(
        floor_area=total_geometry['floor_area'],
        wall_area=total_geometry['wall_area'],
        cable_m=hidden['cable_m'],
        has_floor=hidden['has_floor'],
        has_walls=hidden['has_walls'],
        has_electric=hidden['has_electric'],
        wet_floor_area=hidden['wet_floor'],
        city=request.city,
        db=db,
        sources_by_id=sources_by_id,
    )
    hidden_works = HiddenWorks(
        note=hidden_raw['note'],
        total_min=hidden_raw['total_min'],
        total_avg=hidden_raw['total_avg'],
        total_max=hidden_raw['total_max'],
        items=[HiddenWorkItem(**it) for it in hidden_raw['items']],
    )

    geometry_summary = GeometrySummary(
        floor_area=float(total_geometry['floor_area']),
        ceiling_area=float(total_geometry['ceiling_area']),
        wall_area=float(total_geometry['wall_area']),
        perimeter=float(total_geometry['perimeter']),
    )

    return EstimateResponse(
        scope=request.scope,
        summary=summary,
        geometry=geometry_summary,
        materials=materials_response,
        labor=labor_response,
        hidden_works=hidden_works,
    )
