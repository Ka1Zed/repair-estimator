from fastapi import FastAPI
# импорт роутеров(Backend 2)
from app.api.materials import router as materials_router
from app.api.labor import router as labor_router
from app.api.rooms import router as rooms_router

app = FastAPI()
# подключение роутеров к приложению(Backend 2)
app.include_router(materials_router)
app.include_router(labor_router)
app.include_router(rooms_router)

@app.get("/")
def root():
    return {"message": "Hello World"}

# endpoint для проверки работоспособности
@app.get("/health")
def health_check():
    return {"status": "ok"}

