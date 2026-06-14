from fastapi import FastAPI
from app.api.materials import router as materials_router

app = FastAPI()
app.include_router(materials_router)

@app.get("/")
def root():
    return {"message": "Hello World"}
