"""
Скачивание весов модели распознавания речи и silero VAD при сборке образа.

Скрипт сознательно не импортирует пакет app: в Dockerfile он копируется до кода
приложения, чтобы тяжёлый слой с весами (около 1 ГБ) не пересобирался при каждой
правке кода. Раскладка каталогов (MODELS_DIR/<модель> и MODELS_DIR/silero-vad)
должна совпадать с model_dir() и vad_dir() из app/transcription.py — это
проверяет tests/test_download_script.py.

Переменные окружения: MODELS_DIR, TRANSCRIPTION_MODEL, TRANSCRIPTION_QUANTIZATION.
"""

import os
from pathlib import Path

import onnx_asr


def main() -> None:
    """Скачивает модель и VAD в MODELS_DIR; onnx-asr сразу проверяет их загрузкой."""
    models_dir = Path(os.getenv("MODELS_DIR", "/opt/models"))
    model = os.getenv("TRANSCRIPTION_MODEL", "gigaam-v3-e2e-rnnt")
    quantization = os.getenv("TRANSCRIPTION_QUANTIZATION") or None

    print(f"Скачивание модели {model} (quantization={quantization}) в {models_dir}")
    onnx_asr.load_model(model, models_dir / model, quantization=quantization)
    # CTC int8 восстанавливает короткие реплики, которые RNN-T возвращает пустыми.
    fallback = "gigaam-v3-e2e-ctc"
    onnx_asr.load_model(fallback, models_dir / fallback, quantization="int8")
    onnx_asr.load_vad("silero", models_dir / "silero-vad")
    print("Веса модели и VAD готовы")


if __name__ == "__main__":
    main()
