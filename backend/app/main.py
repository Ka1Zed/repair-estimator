from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
# импорт роутеров(Backend 2)
from app.api.materials import router as materials_router
from app.api.labor import router as labor_router
from app.api.rooms import router as rooms_router
from app.api.admin import router as admin_router 
from app.api.room_types import router as room_types_router

app = FastAPI()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],  # адрес фронта (Vite dev)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# подключение роутеров к приложению(Backend 2)
app.include_router(materials_router)
app.include_router(labor_router)
app.include_router(rooms_router)
app.include_router(admin_router)
app.include_router(room_types_router)

@app.get("/")
def root():
    return {"message": "Hello World"}

# endpoint для проверки работоспособности
@app.get("/health")
def health_check():
    return {"status": "ok"}