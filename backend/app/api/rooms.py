from fastapi import APIRouter, HTTPException, status
from app.schemas.room import RoomCalculateRequest, RoomCalculateResponse
from app.services.geometry_service import floor_area, perimeter, wall_area

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

@router.post("/calculate", response_model=RoomCalculateResponse)
async def calculate_room_geometry(request: RoomCalculateRequest):
    """
    Рассчитывает геометрию помещения по точкам пола и высоте.
    """
    points = [(p.x, p.y) for p in request.points]
    height = request.height
    openings = request.openings

    try:
        floor = floor_area(points)
        perim = perimeter(points)
        walls = wall_area(points, height, openings)
    except ValueError as e:
        # Преобразуем доменное исключение в HTTP 422 с тем же сообщением
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e)
        )

    return RoomCalculateResponse(
        floor_area=floor,
        ceiling_area=floor,
        perimeter=perim,
        wall_area=walls
    )
