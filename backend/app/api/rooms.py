from fastapi import APIRouter
from app.schemas.room import RoomCalculateRequest, RoomCalculateResponse
from app.services.geometry_service import floor_area, perimeter, wall_area

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

@router.post("/calculate", response_model=RoomCalculateResponse)
async def calculate_room_geometry(request: RoomCalculateRequest):
    """
    Рассчитывает геометрию помещения по точкам пола и высоте.
    """
    points = [(p.x, p.y) for p in request.points]   # преобразуем в список кортежей
    height = request.height

    # Вызываем сервисные функции
    floor = floor_area(points)
    perim = perimeter(points)
    walls = wall_area(points, height)

    # Площадь потолка равна площади пола
    ceiling = floor

    return RoomCalculateResponse(
        floor_area=floor,
        ceiling_area=ceiling,
        perimeter=perim,
        wall_area=walls
    )