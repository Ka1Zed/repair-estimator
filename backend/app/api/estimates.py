import logging
from decimal import Decimal
from typing import Dict, List, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import LaborService, LaborPrice, PriceSource
from app.schemas.estimate import (
    EstimateRequest, EstimateResponse, Summary, GeometrySummary,
    MaterialItem, LaborItem
)
from app.services.geometry_service import calculate_room_geometry
from app.services.material_calc_service import calculate_materials, packs_to_buy
from app.services.labor_calc_service import calculate_labor
from app.services.repair_coeffs_service import apply_repair_coeffs
from app.services.price_aggregator_service import get_price
from app.parsers.megastroy_parser import MegastroyParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/estimates", tags=["estimates"])


@router.post("/calculate", response_model=EstimateResponse)
def calculate_estimate(
    request: EstimateRequest,
    db: Session = Depends(get_db)
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
        geometry = calculate_room_geometry(
            points=[(p.x, p.y) for p in room.points],
            height=room.height,
            openings=[(o.type, o.width, o.height) for o in room.openings]
        )

        for key in total_geometry:
            total_geometry[key] += Decimal(str(geometry[key]))

        materials = calculate_materials(
            geometry=geometry,
            repair_options=request.repair_options.model_dump(),
            db=db
        )
        all_materials.extend(materials)

        labor = calculate_labor(
            geometry=geometry,
            repair_options=request.repair_options.model_dump(),
            db=db
        )
        all_labor.extend(labor)

    parser = MegastroyParser()

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
                'pack_quantity': Decimal(0),
            }
        mat_groups[mid]['quantity'] += mat['quantity']
        if mat.get('pack_quantity') is not None:
            mat_groups[mid]['pack_quantity'] += mat['pack_quantity']

    materials_response: List[MaterialItem] = []
    materials_sum = {'min': Decimal(0), 'avg': Decimal(0), 'max': Decimal(0)}

    for mid, group in mat_groups.items():
        name = group['name']
        packs = packs_to_buy(group['pack_quantity'])
        final_quantity = Decimal(packs) * group['package_size']

        price_obj = get_price(name, parser=parser)
        if not price_obj:
            logger.warning(f"Цена для материала '{name}' не найдена, пропускаем")
            continue

        price_avg = price_obj.price_avg
        total_avg = final_quantity * price_avg
        source = db.query(PriceSource).filter(PriceSource.id == price_obj.source_id).first()
        source_name = source.name if source else "unknown"
        updated_at = price_obj.updated_at.strftime("%Y-%m-%d") if price_obj.updated_at else ""

        materials_response.append(MaterialItem(
            name=name,
            quantity=float(final_quantity),
            unit=group['unit'],
            price_avg=float(price_avg),
            total_avg=float(total_avg),
            source=source_name,
            updated_at=updated_at
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
        labor_service = db.query(LaborService).filter(LaborService.name == service).first()
        if not labor_service:
            continue
        labor_price = db.query(LaborPrice).filter(
            LaborPrice.labor_service_id == labor_service.id
        ).first()
        if not labor_price:
            continue

        volume = group['volume']
        price_avg = labor_price.price_avg
        total_avg = volume * price_avg

        labor_response.append(LaborItem(
            service=service,
            specialist=group['specialist'],
            volume=float(volume),
            unit=group['unit'],
            price_avg=float(price_avg),
            total_avg=float(total_avg),
            source="seed"
        ))

        labor_sum['min'] += volume * labor_price.price_min
        labor_sum['avg'] += volume * labor_price.price_avg
        labor_sum['max'] += volume * labor_price.price_max

    coeff_result = apply_repair_coeffs(
        materials=materials_sum,
        labor=labor_sum,
        repair_type=request.repair_type
    )

    summary = Summary(
        materials_min=float(coeff_result['materials_min']),
        materials_avg=float(coeff_result['materials_avg']),
        materials_max=float(coeff_result['materials_max']),
        labor_min=float(coeff_result['labor_min']),
        labor_avg=float(coeff_result['labor_avg']),
        labor_max=float(coeff_result['labor_max']),
        total_min=float(coeff_result['total_min']),
        total_avg=float(coeff_result['total_avg']),
        total_max=float(coeff_result['total_max']),
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
