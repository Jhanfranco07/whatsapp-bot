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


def test_knowledge_base_semantic_match_without_exact_keyword(tmp_path):
    path = tmp_path / "contexto.json"
    path.write_text(
        json.dumps(
            {
                "entradas": [
                    {
                        "tema": "admision",
                        "palabras_clave": ["proceso de admision pregrado"],
                        "respuesta": "Postulación confirmada.",
                        "fuente_url": "https://www.usil.edu.pe/",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    entry = KnowledgeBase(path).find("quiero postular a pregrado")

    assert entry is not None
    assert entry["respuesta"] == "Postulación confirmada."


def test_knowledge_base_add_entry(tmp_path):
    path = tmp_path / "contexto.json"
    path.write_text(json.dumps({"entradas": []}), encoding="utf-8")

    item = KnowledgeBase.add_entry(
        {
            "palabras_clave": ["campus"],
            "respuesta": "Campus confirmado.",
            "fuente_url": "https://www.usil.edu.pe/",
        },
        path,
    )

    assert item["id"] == "contexto_1"
    assert KnowledgeBase(path).find("campus")["respuesta"] == "Campus confirmado."
