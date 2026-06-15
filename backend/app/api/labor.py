from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import LaborService
from app.schemas.labor import LaborServiceOut

router = APIRouter(prefix="/api")

@router.get("/labor-services", response_model=list[LaborServiceOut])
def get_labor_services(db: Session = Depends(get_db)):
    return db.execute(select(LaborService)).scalars().all()