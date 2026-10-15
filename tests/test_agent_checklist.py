"""
What an application needs (src/agent/checklist.py): questions and "write" materials to draft,
"gather" materials to collect, each matched to the uploaded document that covers it, if any.
"""

from src.agent.checklist import build_checklist, item_key, matching_document
from src.models.opportunity import ApplicationQuestion, RequiredMaterial
from tests.test_matcher import opp


def material(item, kind, details=None):
    return RequiredMaterial(item=item, details=details, quote=f"Send your {item}.", kind=kind)


CALL = opp("call",
           application_questions=[ApplicationQuestion(question="Why this residency?", limit="max 300 words")],
           required_materials=[material("Motivation letter", "write"), material("CV", "gather", "max 2 pages"),
                               material("Portfolio", "gather"), material("Budget", "gather"),
                               material("Artist statement", "write"), material("Letters", None)])


def test_questions_first_then_materials_with_their_kind():
    items = build_checklist(CALL)
    assert [(i.title, i.kind, i.source) for i in items] == [
        ("Why this residency?", "write", "question"), ("Motivation letter", "write", "material"),
        ("CV", "gather", "material"), ("Portfolio", "gather", "material"), ("Budget", "gather", "material"),
        ("Artist statement", "write", "material"), ("Letters", "gather", "material")]   # unclassified -> gather
    assert items[0].limit == "max 300 words" and items[2].limit == "max 2 pages"


def test_uploaded_documents_cover_only_what_they_are():
    by_title = {i.title: i.document for i in build_checklist(CALL)}
    assert by_title["CV"] == "cv" and by_title["Portfolio"] == "portfolio"
    assert by_title["Budget"] is None and by_title["Motivation letter"] is None
    assert by_title["Artist statement"] == "statement"   # a text to write, but the uploaded one can be adapted


def test_document_rules():
    assert matching_document("short curriculum vitae (CV)") == "cv"
    assert matching_document("Résumé") == "cv"
    assert matching_document("examples of your work") == "portfolio"
    assert matching_document("Electronic artistic dossier") == "portfolio"
    assert matching_document("statement describing your artistic practice") == "statement"
    # not the artist's own statement or document
    assert matching_document("Statement of intent") is None
    assert matching_document("Director's CV") is None
    assert matching_document("biography of the curator") is None


def test_keys_follow_the_text_not_the_position():
    moved = opp("call", required_materials=[material("Budget", "gather"), material("CV", "gather")])
    keys = {i.title: i.key for i in build_checklist(moved)}
    assert keys["CV"] == item_key("m", "CV") == item_key("m", " cv ")
    assert keys["CV"] == {i.title: i.key for i in build_checklist(CALL)}["CV"]


def test_the_same_item_twice_is_listed_once():
    twice = opp("call", required_materials=[material("CV", "gather"), material("CV", "gather")])
    assert len(build_checklist(twice)) == 1


def test_the_english_copy_is_used_when_there_is_one():
    call = opp("call", required_materials=[material("Lebenslauf", "gather")],
               required_materials_en=[material("CV", "gather")])
    assert [i.title for i in build_checklist(call)] == ["CV"]


def test_a_question_that_repeats_a_material_to_write_is_listed_once():
    """LVA50's call: one sentence extracted as two question fragments and as two materials to write."""
    call = opp("call",
               application_questions=[ApplicationQuestion(question="Please submit your abstract", limit="max 250 words"),
                                      ApplicationQuestion(question="with contact details, affiliation and short bio",
                                                          limit="max 100 words"),
                                      ApplicationQuestion(question="Why this abstract?", limit="max 50 words")],
               required_materials=[material("abstract", "write", "max 250 words"), material("contact details", "gather"),
                                   material("short bio", "write", "max 100 words")])
    assert [(i.title, i.kind) for i in build_checklist(call)] == [
        ("Why this abstract?", "write"),   # another limit: a question of its own
        ("abstract", "write"), ("contact details", "gather"), ("short bio", "write")]
