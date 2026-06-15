import json

from app.services.knowledge_base import KnowledgeBase


def test_knowledge_base_reads_new_verified_context(tmp_path):
    path = tmp_path / "contexto.json"
    path.write_text(
        json.dumps(
            {
                "entradas": [
                    {
                        "palabras_clave": ["laboratorio de innovación"],
                        "respuesta": "Respuesta confirmada.",
                        "fuente_url": "https://www.usil.edu.pe/",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    entry = KnowledgeBase(path).find("¿Tienen laboratorio de innovación?")

    assert entry is not None
    assert KnowledgeBase.render(entry).startswith("Respuesta confirmada.")
