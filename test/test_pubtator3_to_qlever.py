import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).parent.parent))

from pubs.scripts.pubtator3_to_qlever import main as pubtator3_to_qlever_main


NF = Namespace("http://nf-osi.github.com/terms#")


def test_companion_rdf_marks_publications_as_in_full_text_index(tmp_path, monkeypatch):
    pubtator_dir = tmp_path / "pubtator3"
    output_dir = tmp_path / "qlever_text"
    pubtator_dir.mkdir()

    sample = {
        "PubTator3": [
            {
                "pmid": "12345678",
                "passages": [
                    {
                        "infons": {"section_type": "TITLE"},
                        "text": "NF1 mutations in schwannoma",
                        "annotations": [
                            {
                                "infons": {
                                    "type": "Gene",
                                    "identifier": "4763",
                                    "name": "NF1",
                                    "valid": True,
                                },
                                "text": "NF1",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    (pubtator_dir / "PMC1234567.json").write_text(json.dumps(sample), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pubtator3_to_qlever.py",
            "--pubtator-dir",
            str(pubtator_dir),
            "--output-dir",
            str(output_dir),
        ],
    )
    pubtator3_to_qlever_main()

    graph = Graph()
    graph.parse(output_dir / "text_entities.ttl", format="turtle")

    publication = URIRef("https://pubmed.ncbi.nlm.nih.gov/12345678")
    assert (publication, NF.inFullTextIndex, Literal(True)) in graph
