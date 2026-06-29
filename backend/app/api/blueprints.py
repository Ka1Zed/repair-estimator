from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.blueprint_service import BlueprintService
from app.schemas.blueprint import BlueprintUploadResponse

router = APIRouter(prefix="/api/blueprints", tags=["blueprints"])

# Максимальный размер файла: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Допустимые MIME типы
ALLOWED_CONTENT_TYPES = {
    'image/png',
    'image/jpeg',
    'image/jpg',
    'application/pdf'
}


@router.post("/upload", response_model=BlueprintUploadResponse)
async def upload_blueprint(file: UploadFile = File(...)):
    """
    Загрузка и распознавание архитектурного чертежа помещения.

    **Поддерживаемые форматы:** PNG, JPG, JPEG, PDF (до 10 MB)

    **Метод распознавания** выбирается автоматически по приоритету:
    1. Google Gemini Vision API (бесплатно, если есть GEMINI_API_KEY)
    2. Claude Vision API (платно, если есть ANTHROPIC_API_KEY)
    3. Ollama + LLaVA (локально, если запущен)

    Если ни один метод не настроен, ответ вернётся с `success: false` и
    предупреждением (сервер не падает).

    **⚠️ Важно:** Результат всегда требует ручной проверки и корректировки пользователем!

    Args:
        file: Загружаемый файл чертежа

    Returns:
        BlueprintUploadResponse с извлеченными данными

    Raises:
        HTTPException 422: Неподдерживаемый формат файла
        HTTPException 413: Файл слишком большой
        HTTPException 500: Ошибка обработки чертежа
    """
    # Валидация типа файла
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Неподдерживаемый формат файла. Допустимые форматы: PNG, JPG, JPEG, PDF"
        )

    # Чтение файла
    contents = await file.read()

    # Проверка размера
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )

    # Обработка чертежа
    try:
        service = BlueprintService()
        result = service.process_blueprint(contents, file.filename or "blueprint")
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки чертежа: {str(e)}"
        )


@router.get("/health")
async def blueprint_service_health():
    """
    Проверка доступности сервиса распознавания чертежей.

    Returns:
        Информация о доступных методах распознавания
    """
    service = BlueprintService()
    method = service._choose_method()

    return {
        "status": "ok",
        "available_method": method,
        "has_gemini_key": bool(service.gemini_key),
        "has_anthropic_key": bool(service.anthropic_key),
    }
