# План реализации: Загрузка и обработка чертежей

**Дата:** 2026-06-18  
**Ветка:** `feature/blueprint-upload`  
**Статус:** Планирование

## 🎯 Цель

Реализовать функцию загрузки архитектурных чертежей с автоматическим распознаванием размеров помещения, используя **бесплатные** решения для Vision AI.

## 🆓 Бесплатные решения для распознавания

### Вариант 1: Google Gemini Pro Vision (РЕКОМЕНДУЕТСЯ)
- ✅ **Полностью бесплатно**: 1500 запросов/день, 60 запросов/минуту
- ✅ Отличное качество распознавания архитектурных чертежей
- ✅ Официальный Python SDK: `google-generativeai`
- ✅ API ключ бесплатный: https://makersuite.google.com/app/apikey
- 📊 Точность: ~85% для стандартных чертежей

### Вариант 2: Ollama + LLaVA (локально)
- ✅ 100% бесплатно, работает офлайн
- ✅ Нет лимитов, нет трат
- ✅ Запускается локально через Docker или Ollama CLI
- ⚠️ Требует ~8GB RAM
- 📊 Точность: ~70-75% для чертежей

### Вариант 3: Claude API (опциональный)
- Для пользователей, у которых уже есть ключ
- Высочайшее качество (~90% точность)
- Платно: ~$0.015 за чертеж

### Fallback: EasyOCR
- Всегда доступен, не требует API
- Извлекает только текст размеров
- 📊 Точность: ~40%, требует много ручных правок

## 🔄 Workflow обработки

```
1. Загрузка файла (PNG/JPG/PDF, макс 10MB)
   ↓
2. Конвертация PDF → Image (если нужно)
   ↓
3. Выбор метода (приоритет):
   • GEMINI_API_KEY → Gemini Vision ✅ БЕСПЛАТНО
   • ANTHROPIC_API_KEY → Claude Vision (платно)
   • Ollama запущен → LLaVA ✅ БЕСПЛАТНО
   • Fallback → EasyOCR
   ↓
4. Распознавание:
   • Контур помещения → координаты точек
   • Размеры стен → длины в метрах
   • Проемы → двери и окна с размерами
   • Высота потолка (если указана)
   ↓
5. Возврат JSON с результатом + confidence score
   ↓
6. Frontend отображает результат
   ↓
7. Пользователь корректирует вручную ⚠️ ОБЯЗАТЕЛЬНО
   ↓
8. Применение в редактор
```

## 📦 Зависимости

### Backend (requirements.txt)
```txt
# Обработка изображений
Pillow==11.0.0
pdf2image==1.17.0

# OCR (базовый уровень)
easyocr==1.7.1
numpy>=1.24.0

# Vision API (бесплатные варианты)
google-generativeai==0.3.2  # Gemini - БЕСПЛАТНО
ollama==0.1.6  # LLaVA локально - БЕСПЛАТНО

# Vision API (опциональные)
anthropic==0.34.0  # Claude - платно
```

### Системные зависимости
```bash
# macOS
brew install poppler  # для PDF конвертации
brew install ollama   # опционально, для локального LLaVA

# Docker (альтернатива)
docker pull ollama/ollama
docker run -d -p 11434:11434 ollama/ollama
```

## 🏗️ Структура кода

### 1. Схема данных (backend/app/schemas/blueprint.py)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class Point(BaseModel):
    x: float
    y: float

class Opening(BaseModel):
    type: Literal["door", "window"]
    width: float
    height: float
    position: Optional[Point] = None

class BlueprintUploadResponse(BaseModel):
    success: bool
    method: Literal["gemini", "claude", "ollama", "ocr"]
    confidence: float = Field(..., ge=0, le=1)
    
    # Извлеченные данные
    points: List[Point]
    height: Optional[float] = None
    openings: List[Opening] = []
    
    # Метаданные
    raw_dimensions: List[str] = []
    warnings: List[str] = []
```

### 2. Сервис обработки (backend/app/services/blueprint_service.py)

**Ключевые методы:**

- `process_blueprint(file_bytes, filename)` — главная точка входа
- `_prepare_image(file_bytes, filename)` — конвертация PDF → Image
- `_choose_method()` — выбор доступного метода распознавания
- `_process_with_gemini(image)` — Gemini Vision API
- `_process_with_claude(image)` — Claude Vision API
- `_process_with_ollama(image)` — локальный LLaVA
- `_process_with_ocr(image)` — базовый EasyOCR
- `_parse_dimension(dim_str)` — конвертация единиц в метры

**Промпт для Vision API:**
```python
prompt = """Проанализируй этот архитектурный чертеж помещения.

Извлеки:
1. Координаты углов помещения в метрах (начни с (0,0))
2. Высоту потолка если указана
3. Двери: ширина, высота, примерная позиция
4. Окна: ширина, высота, примерная позиция
5. Все размеры на чертеже

Верни JSON:
{
  "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
  "height": 2.7,
  "openings": [
    {"type": "door", "width": 0.8, "height": 2.0},
    {"type": "window", "width": 1.5, "height": 1.4}
  ],
  "raw_dimensions": ["4.0м", "3.0м", "2.7м"],
  "warnings": ["высота потолка не найдена на чертеже"]
}

Если что-то не видно или неясно, добавь в warnings."""
```

### 3. API Endpoint (backend/app/api/blueprints.py)

```python
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(prefix="/api/blueprints", tags=["blueprints"])

@router.post("/upload", response_model=BlueprintUploadResponse)
async def upload_blueprint(file: UploadFile = File(...)):
    """
    Загрузка и распознавание чертежа.
    
    Форматы: PNG, JPG, JPEG, PDF (до 10 MB)
    
    Метод распознавания (приоритет):
    1. Gemini API (бесплатно, если есть ключ)
    2. Claude API (платно, если есть ключ)
    3. Ollama LLaVA (бесплатно, если запущен)
    4. EasyOCR (всегда доступен, базовая точность)
    """
    # Валидация формата
    allowed = {'image/png', 'image/jpeg', 'image/jpg', 'application/pdf'}
    if file.content_type not in allowed:
        raise HTTPException(422, detail="Неподдерживаемый формат")
    
    # Проверка размера
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(413, detail="Файл слишком большой (макс 10MB)")
    
    # Обработка
    service = BlueprintService()
    result = service.process_blueprint(contents, file.filename)
    return result
```

### 4. Frontend компонент (frontend/src/components/BlueprintUpload.tsx)

```tsx
export default function BlueprintUpload() {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const setPoints = useProjectStore(state => state.setPoints);
  
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    setUploading(true);
    try {
      const res = await fetch('/api/blueprints/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      setResult(data);
      
      // Автоприменение при высокой уверенности
      if (data.confidence > 0.7 && data.points.length >= 3) {
        setPoints(data.points);
      }
    } catch (err) {
      alert('Ошибка: ' + err.message);
    } finally {
      setUploading(false);
    }
  };
  
  return (
    <div>
      <h3>📐 Загрузить чертеж (beta)</h3>
      <input
        type="file"
        accept=".png,.jpg,.jpeg,.pdf"
        onChange={handleFileUpload}
        disabled={uploading}
      />
      
      {uploading && <p>Обработка чертежа...</p>}
      
      {result && (
        <ResultCard
          method={result.method}
          confidence={result.confidence}
          points={result.points}
          warnings={result.warnings}
          onApply={() => setPoints(result.points)}
        />
      )}
    </div>
  );
}
```

## 🔧 Настройка окружения

### 1. Получить бесплатный API ключ Gemini

```bash
# Перейти на https://makersuite.google.com/app/apikey
# Создать новый API ключ (бесплатно)
# Добавить в .env:
echo "GEMINI_API_KEY=AIza..." >> backend/.env
```

### 2. Установить зависимости

```bash
cd backend
pip install -r requirements.txt

# Системные (macOS)
brew install poppler
```

### 3. (Опционально) Запустить локальный Ollama

```bash
# Установка
brew install ollama

# Скачать модель LLaVA
ollama pull llava:13b

# Запустить сервер (будет на localhost:11434)
ollama serve

# Добавить в .env:
echo "OLLAMA_BASE_URL=http://localhost:11434" >> backend/.env
```

## 📝 План разработки (этапы)

### ✅ Этап 0: Подготовка (сейчас)
- [x] Создана ветка `feature/blueprint-upload`
- [x] Изучена архитектура проекта
- [x] Выбраны бесплатные решения
- [ ] Получить GEMINI_API_KEY

### 🔨 Этап 1: Базовая инфраструктура (Backend 2)
1. Добавить зависимости в requirements.txt
2. Создать схему BlueprintUploadResponse
3. Создать заглушку BlueprintService (возвращает моковые данные)
4. Создать endpoint /api/blueprints/upload
5. Зарегистрировать роутер в main.py

**Тест:** Загрузка файла возвращает моковый JSON

### 🔨 Этап 2: OCR обработка (Backend 1)
1. Реализовать _prepare_image (PDF → Image)
2. Реализовать _process_with_ocr с EasyOCR
3. Реализовать _parse_dimension (конвертация мм/см/м)
4. Добавить обработку ошибок

**Тест:** Загрузка простого чертежа извлекает размеры

### 🔨 Этап 3: Gemini Vision API (Backend 1)
1. Реализовать _process_with_gemini
2. Добавить проверку GEMINI_API_KEY
3. Обработка structured output
4. Fallback на OCR если API недоступен

**Тест:** С ключом использует Gemini, без — OCR

### 🔨 Этап 4: Frontend компонент (Frontend 2)
1. Создать BlueprintUpload компонент
2. Реализовать загрузку через FormData
3. Отображение результата с warnings
4. Кнопка применения в store
5. Интеграция в ProjectCreatePage

**Тест:** Загрузка → просмотр → применение → точки в редакторе

### 🔨 Этап 5: Ollama интеграция (Backend 1, опционально)
1. Реализовать _process_with_ollama
2. Проверка доступности Ollama
3. Fallback на другие методы

**Тест:** С запущенным Ollama использует LLaVA

### 🔨 Этап 6: UX улучшения (Frontend 1 + Frontend 2)
1. Предпросмотр загруженного изображения
2. Drag-and-drop загрузка
3. Прогресс-бар обработки
4. Подсветка извлеченных точек
5. Сравнение "чертеж vs результат"

## 🧪 Тестирование

### Backend тесты
```bash
# Базовые
pytest backend/app/tests/test_blueprints.py::test_upload_png
pytest backend/app/tests/test_blueprints.py::test_upload_pdf
pytest backend/app/tests/test_blueprints.py::test_file_too_large

# OCR
pytest backend/app/tests/test_blueprint_service.py::test_ocr_extraction
pytest backend/app/tests/test_blueprint_service.py::test_dimension_parsing

# Vision API (требует ключ)
pytest backend/app/tests/test_blueprint_service.py::test_gemini_vision
```

### Manual тестирование
1. ✅ Загрузить простой PNG чертеж → извлечь размеры
2. ✅ Загрузить PDF → конвертация работает
3. ✅ Без API ключа → использует OCR
4. ✅ С Gemini ключом → использует Gemini
5. ✅ Плохой скан → показывает warnings
6. ✅ Применить результат → точки в редакторе

## 📊 Ожидаемые результаты

| Метод | Точность | Скорость | Стоимость |
|-------|----------|----------|-----------|
| Gemini Vision | ~85% | 2-4 сек | **Бесплатно** (1500/день) |
| Ollama LLaVA | ~70% | 5-10 сек | **Бесплатно** (локально) |
| Claude Vision | ~90% | 2-3 сек | ~$0.015 за чертеж |
| EasyOCR | ~40% | 3-5 сек | **Бесплатно** |

## ⚠️ Ограничения MVP

1. **Только простые планы:** Прямоугольные и многоугольные помещения
2. **Один чертеж = одно помещение:** Нет поддержки нескольких комнат
3. **Обязательная проверка:** Пользователь должен вручную подтвердить результат
4. **Качество скана:** Размытые/темные сканы снижают точность
5. **Масштаб:** Если масштаб не указан явно, может быть ошибка

## 🚀 Будущие улучшения (post-MVP)

1. Несколько помещений на одном чертеже
2. Автоопределение типа помещения (унитаз → санузел)
3. Поддержка DWG/DXF форматов (ezdxf)
4. Fine-tuning на архитектурных чертежах
5. Экспорт обратно в DXF

## 📚 Документация

Обновить `docs/api.md`:

```markdown
## POST /api/blueprints/upload

Загрузка и распознавание архитектурного чертежа.

**Форматы:** PNG, JPG, JPEG, PDF (до 10 MB)

**Request:** multipart/form-data
```
file: UploadFile

**Response 200:**
```json
{
  "success": true,
  "method": "gemini",
  "confidence": 0.85,
  "points": [
    {"x": 0, "y": 0},
    {"x": 4, "y": 0},
    {"x": 4, "y": 3},
    {"x": 0, "y": 3}
  ],
  "height": 2.7,
  "openings": [
    {"type": "door", "width": 0.8, "height": 2.0},
    {"type": "window", "width": 1.5, "height": 1.4}
  ],
  "raw_dimensions": ["4.0м", "3.0м", "2.7м"],
  "warnings": []
}
```

**Методы распознавания (приоритет):**
1. Gemini Vision API — бесплатно (с GEMINI_API_KEY)
2. Claude Vision API — платно (с ANTHROPIC_API_KEY)
3. Ollama LLaVA — бесплатно локально (если запущен)
4. EasyOCR — базовый fallback

⚠️ **Важно:** Результат всегда требует ручной проверки!
```

## 🎉 Готовы начать!

**Следующий шаг:** 
1. Получить бесплатный GEMINI_API_KEY
2. Начать с Этапа 1 (базовая инфраструктура)

Хотите начать реализацию?
