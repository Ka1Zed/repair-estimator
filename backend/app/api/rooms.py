from fastapi import APIRouter, HTTPException, status
from app.schemas.room import RoomCalculateRequest, RoomCalculateResponse
from app.services.geometry_service import floor_area, perimeter, wall_area

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("/calculate", response_model=RoomCalculateResponse)
async def calculate_room_geometry(request: RoomCalculateRequest):
    points = [(p.x, p.y) for p in request.points]
    height = request.height

    openings = []
    for o in request.openings:
        if o.reveal_depth is not None:
            openings.append((o.type, o.width, o.height, o.reveal_depth))
        else:
            openings.append((o.type, o.width, o.height))

    try:
        result = calculate_room_geometry(points, height, openings)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

    return RoomCalculateResponse(
        floor_area=result['floor_area'],
        ceiling_area=result['ceiling_area'],
        perimeter=result['perimeter'],
        wall_area=result['wall_area']
    )
