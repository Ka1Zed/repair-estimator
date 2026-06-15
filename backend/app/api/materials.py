from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Material
from app.schemas.material import MaterialOut

router = APIRouter(prefix="/api")

@router.get("/materials", response_model=list[MaterialOut])
def get_materials(db: Session = Depends(get_db)):
    return db.execute(select(Material)).scalars().all()