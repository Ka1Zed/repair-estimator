import secrets
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Project
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListItem, ProjectShareResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        city=project.city,
        rooms=project.rooms,
        scope=project.scope,
        share_token=project.share_token,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectResponse:
    project = Project(
        name=body.name,
        city=body.city,
        rooms=[r.model_dump() for r in body.rooms],
        scope=body.scope,
        share_token=secrets.token_urlsafe(16),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_response(project)


@router.get("", response_model=List[ProjectListItem])
def list_projects(db: Session = Depends(get_db)) -> List[ProjectListItem]:
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [
        ProjectListItem(
            id=p.id, name=p.name, city=p.city,
            created_at=p.created_at, updated_at=p.updated_at,
        )
        for p in projects
    ]


# Статичный путь /share/{token} регистрируем раньше /{project_id}, чтобы не
# зависеть от того, что project_id типизирован как int (иначе "share" туда не
# попадёт по конвертеру пути, но порядок всё равно нагляднее так).
@router.get("/share/{share_token}", response_model=ProjectShareResponse)
def get_project_by_share_token(share_token: str, db: Session = Depends(get_db)) -> ProjectShareResponse:
    project = db.query(Project).filter(Project.share_token == share_token).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectShareResponse(
        name=project.name,
        city=project.city,
        rooms=project.rooms,
        scope=project.scope,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return _to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    project.name = body.name
    project.city = body.city
    project.rooms = [r.model_dump() for r in body.rooms]
    project.scope = body.scope
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    db.delete(project)
    db.commit()
