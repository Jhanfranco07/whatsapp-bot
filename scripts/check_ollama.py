import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import LLMService
from app.llm.provider import LLMError


if __name__ == "__main__":
    service = LLMService()
    try:
        print("Estado:", service.health())
        result = service.classify(
            "Quisiera conocer cómo iniciar mi proceso para estudiar en la universidad"
        )
        print("Clasificación:", result)
    except LLMError as error:
        print(f"Error LLM: {error}")
        raise SystemExit(1) from error
