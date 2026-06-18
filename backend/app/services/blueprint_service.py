"""
Сервис для обработки и распознавания архитектурных чертежей.

Поддерживает несколько методов распознавания:
1. Google Gemini Vision API (бесплатно, высокое качество)
2. Claude Vision API (платно, высочайшее качество)
3. Ollama + LLaVA (локально, бесплатно)
4. EasyOCR (fallback, базовое качество)
"""

import os
import io
import base64
import logging
from typing import Dict, Any
from PIL import Image

logger = logging.getLogger(__name__)


class BlueprintService:
    """Сервис распознавания архитектурных чертежей"""

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ocr_reader = None  # Ленивая инициализация EasyOCR

    def process_blueprint(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Главная точка входа для обработки чертежа.

        Args:
            file_bytes: Содержимое файла
            filename: Имя файла (для определения типа)

        Returns:
            Словарь с результатом распознавания
        """
        logger.info(f"Обработка чертежа: {filename}")

        # 1. Подготовка изображения
        try:
            image = self._prepare_image(file_bytes, filename)
        except Exception as e:
            logger.error(f"Ошибка подготовки изображения: {e}")
            return self._error_response(f"Ошибка обработки файла: {str(e)}")

        # 2. Выбор метода распознавания и обработка
        method = self._choose_method()
        logger.info(f"Выбран метод распознавания: {method}")

        # ЗАГЛУШКА: пока возвращаем моковые данные
        return self._mock_response(method)

    def _prepare_image(self, file_bytes: bytes, filename: str) -> Image.Image:
        """
        Конвертация файла в PIL Image (поддержка PDF и изображений).

        Args:
            file_bytes: Содержимое файла
            filename: Имя файла

        Returns:
            PIL Image объект
        """
        if filename.lower().endswith('.pdf'):
            # TODO: Реализовать конвертацию PDF → Image (pdf2image)
            raise NotImplementedError("Конвертация PDF будет реализована в следующем этапе")

        # Открываем как изображение
        return Image.open(io.BytesIO(file_bytes))

    def _choose_method(self) -> str:
        """
        Выбор доступного метода распознавания по приоритету:
        1. Gemini (если есть ключ)
        2. Claude (если есть ключ)
        3. Ollama (если доступен)
        4. OCR (всегда доступен)

        Returns:
            Название метода: 'gemini', 'claude', 'ollama' или 'ocr'
        """
        if self.gemini_key:
            return "gemini"

        if self.anthropic_key:
            return "claude"

        # TODO: Проверить доступность Ollama
        # if self._is_ollama_available():
        #     return "ollama"

        return "ocr"

    def _mock_response(self, method: str) -> Dict[str, Any]:
        """
        Заглушка: возвращает моковый результат распознавания.
        Будет заменена на реальную обработку в следующих этапах.

        Args:
            method: Метод распознавания

        Returns:
            Моковый результат
        """
        return {
            "success": True,
            "method": method,
            "confidence": 0.85,
            "points": [
                {"x": 0, "y": 0},
                {"x": 4, "y": 0},
                {"x": 4, "y": 3},
                {"x": 0, "y": 3}
            ],
            "height": 2.7,
            "openings": [
                {"type": "door", "width": 0.8, "height": 2.0}
            ],
            "raw_dimensions": ["4.0м", "3.0м", "2.7м"],
            "warnings": [
                "⚠️ Это тестовые данные. Реальное распознавание будет реализовано в следующем этапе."
            ]
        }

    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """
        Формирование ответа об ошибке.

        Args:
            error_message: Сообщение об ошибке

        Returns:
            Словарь с информацией об ошибке
        """
        return {
            "success": False,
            "method": "none",
            "confidence": 0.0,
            "points": [],
            "height": None,
            "openings": [],
            "raw_dimensions": [],
            "warnings": [error_message]
        }
