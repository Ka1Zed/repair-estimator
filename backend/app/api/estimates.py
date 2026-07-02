import logging
from decimal import Decimal
from math import ceil
from typing import Dict, List, Any, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import PriceSource
from app.schemas.estimate import (
    EstimateRequest, EstimateResponse, Summary, GeometrySummary,
    MaterialItem, LaborItem, RoomInput,
)
from app.services.geometry_service import calculate_room_geometry
from app.services.material_calc_service import (
    calculate_materials, calculate_engineering_materials, packs_to_buy,
)
from app.services.labor_calc_service import calculate_labor, calculate_engineering_labor
from app.services.repair_coeffs_service import CONTINGENCY
from app.services.price_aggregator_service import get_price, get_labor_price
from app.parsers.base import BaseParser
from app.parsers.megastroy_parser import MegastroyParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/estimates", tags=["estimates"])


def get_material_parser() -> BaseParser:
    '''Парсер цен материалов для расчёта сметы.

    Вынесен в зависимость FastAPI, чтобы тесты могли подменить его заглушкой
    (app.dependency_overrides) и не ходить в сеть. В проде — живой Мегастрой.
    '''
    return MegastroyParser()

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
        # Модификаторы живут на уровне поверхности (стены).
        "wallpaper_pattern": bool(w.walls.enabled and w.walls.wallpaper_pattern),
        "primer_two_coats": bool(w.walls.enabled and w.walls.primer_two_coats),
    }


@router.post("/calculate", response_model=EstimateResponse)
def calculate_estimate(
    request: EstimateRequest,
    db: Session = Depends(get_db),
    parser: BaseParser = Depends(get_material_parser),
) -> EstimateResponse:
    all_materials: List[Dict[str, Any]] = []
    all_labor: List[Dict[str, Any]] = []
    total_geometry = {
        'floor_area': Decimal(0),
        'ceiling_area': Decimal(0),
        'wall_area': Decimal(0),
        'perimeter': Decimal(0),
    }

    for room in request.rooms:
        try:
            geometry = calculate_room_geometry(
                points=[(p.x, p.y) for p in room.points],
                height=room.height,
                openings=[(o.type, o.width, o.height) for o in room.openings]
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

        for key in total_geometry:
            total_geometry[key] += Decimal(str(geometry[key]))

        # --- отделка (finish) по works комнаты ---
        finish_options = _finish_options(room)
        all_materials.extend(calculate_materials(
            geometry=geometry, repair_options=finish_options, db=db
        ))
        all_labor.extend(calculate_labor(
            geometry=geometry, repair_options=finish_options, db=db
        ))

        # --- инженерка по явным числам works (дефолты от типа/площади) ---
        sockets, lights, cable_m = _resolve_electric(room, geometry['floor_area'])
        points, pipe_m = _resolve_plumbing(room)
        all_materials.extend(calculate_engineering_materials(
            sockets=sockets, lights=lights, cable_m=cable_m, pipe_m=pipe_m, db=db
        ))
        all_labor.extend(calculate_engineering_labor(
            sockets=sockets, lights=lights, cable_m=cable_m,
            plumbing_points=points, pipe_m=pipe_m, db=db
        ))

    # Множитель строк детализации: непредвиденные расходы (avg). Класса ремонта больше нет (#222).
    # Нужен, чтобы сумма построчных total_avg точно совпадала с summary.*_avg.
    line_factor = CONTINGENCY['avg']

    # Агрегация материалов с округлением до упаковок
    mat_groups: Dict[int, Dict] = {}
    for mat in all_materials:
        mid = mat['material_id']
        if mid not in mat_groups:
            mat_groups[mid] = {
                'name': mat['name'],
                'unit': mat['unit'],
                'package_size': Decimal(str(mat.get('package_size', 1))),
                'quantity': Decimal(0),
                'base_quantity': Decimal(0),
                'pack_quantity': Decimal(0),
            }
        mat_groups[mid]['quantity'] += mat['quantity']
        mat_groups[mid]['base_quantity'] += mat.get('base_quantity', mat['quantity'])
        if mat.get('pack_quantity') is not None:
            mat_groups[mid]['pack_quantity'] += mat['pack_quantity']

    materials_response: List[MaterialItem] = []
    materials_sum = {'min': Decimal(0), 'avg': Decimal(0), 'max': Decimal(0)}

    for mid, group in mat_groups.items():
        name = group['name']
        packs = packs_to_buy(group['pack_quantity'])
        final_quantity = Decimal(packs) * group['package_size']
        base_quantity = group['base_quantity']
        # Эффективный запас группы: quantity/base_quantity — по построению совпадает
        # с накрученным по факту коэффициентом даже после суммирования нескольких комнат.
        waste_factor = (group['quantity'] / base_quantity) if base_quantity > 0 else Decimal(1)

        price_obj = get_price(name, parser=parser, region=request.city)
        if not price_obj:
            # Цены нет даже в seed — не теряем позицию молча, показываем её с пометкой.
            logger.warning(f"Цена для материала '{name}' не найдена, показываем без цены")
            materials_response.append(MaterialItem(
                name=name,
                quantity=float(final_quantity),
                base_quantity=float(base_quantity),
                waste_factor=float(waste_factor),
                package_size=float(group['package_size']),
                packs=packs,
                unit=group['unit'],
                price_avg=0.0,
                total_avg=0.0,
                source="нет цены",
                source_url=None,
                updated_at="",
                region=None
            ))
            continue

        price_avg = price_obj.price_avg
        # Строчный итог уже включает запас на непредвиденные (CONTINGENCY), чтобы
        # сумма строк совпадала с summary (см. line_factor). Класса ремонта больше нет (#222).
        total_avg = final_quantity * price_avg * line_factor
        source = db.query(PriceSource).filter(PriceSource.id == price_obj.source_id).first()
        source_name = source.name if source else "unknown"
        updated_at = price_obj.updated_at.strftime("%Y-%m-%d") if price_obj.updated_at else ""

        materials_response.append(MaterialItem(
            name=name,
            quantity=float(final_quantity),
            base_quantity=float(base_quantity),
            waste_factor=float(waste_factor),
            package_size=float(group['package_size']),
            packs=packs,
            unit=group['unit'],
            price_avg=float(price_avg),
            total_avg=float(total_avg),
            source=source_name,
            source_url=price_obj.source_url,
            updated_at=updated_at,
            region=price_obj.region
        ))

        materials_sum['min'] += final_quantity * price_obj.price_min
        materials_sum['avg'] += final_quantity * price_obj.price_avg
        materials_sum['max'] += final_quantity * price_obj.price_max

    # Агрегация работ
    labor_groups: Dict[str, Dict] = {}
    for job in all_labor:
        service = job['service']
        if service not in labor_groups:
            labor_groups[service] = {
                'specialist': job['specialist'],
                'unit': job['unit'],
                'volume': Decimal(0),
            }
        labor_groups[service]['volume'] += job['volume']

    labor_response: List[LaborItem] = []
    labor_sum = {'min': Decimal(0), 'avg': Decimal(0), 'max': Decimal(0)}

    for service, group in labor_groups.items():
        labor_price = get_labor_price(service, region=request.city)
        if not labor_price:
            continue

        volume = group['volume']
        price_avg = labor_price.price_avg
        # Строчный итог включает запас на непредвиденные (CONTINGENCY), как и у материалов.
        total_avg = volume * price_avg * line_factor
        labor_source = db.query(PriceSource).filter(
            PriceSource.id == labor_price.source_id
        ).first()
        labor_source_name = labor_source.name if labor_source else "seed"

        labor_response.append(LaborItem(
            service=service,
            specialist=group['specialist'],
            volume=float(volume),
            unit=group['unit'],
            price_avg=float(price_avg),
            total_avg=float(total_avg),
            source=labor_source_name,
            source_url=labor_price.source_url,
            region=labor_price.region,
            # Полный список сайтов, объединённых в вилку (#166); None для seed.
            sources=getattr(labor_price, "contributing_sources", None),
        ))

        labor_sum['min'] += volume * labor_price.price_min
        labor_sum['avg'] += volume * labor_price.price_avg
        labor_sum['max'] += volume * labor_price.price_max

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

    geometry_summary = GeometrySummary(
        floor_area=float(total_geometry['floor_area']),
        ceiling_area=float(total_geometry['ceiling_area']),
        wall_area=float(total_geometry['wall_area']),
        perimeter=float(total_geometry['perimeter']),
    )

    return EstimateResponse(
        summary=summary,
        geometry=geometry_summary,
        materials=materials_response,
        labor=labor_response
    )
