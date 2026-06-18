import json
from pathlib import Path

from fastapi import APIRouter

from app.db.session import SessionLocal
from app.db.models import RoomType

router = APIRouter(prefix="/api", tags=["room-types"])

SEED_PATH = Path(__file__).resolve().parent.parent / "db" / "seed_data"


@router.get("/room-types")
def get_room_types():
    '''
    Отдает справочник типов комнат:
    - roomTypes: правила по каждому типу (из БД)
    - finishOptions: подписи вариантов отделки (из seed-файла)
    '''
    session = SessionLocal()
    try:
        types = session.query(RoomType).all()
        room_types = {rt.key: rt.rules for rt in types}
    finally:
        session.close()

    # finishOptions берем из того же JSON, что и сид
    with open(SEED_PATH / "room_types.json", encoding="utf-8") as f:
        finish_options = json.load(f).get("finishOptions", {})

    return {
        "finishOptions": finish_options,
        "roomTypes": room_types,
    }