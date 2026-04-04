import base64
import zipfile
from io import BytesIO
from pathlib import Path

from app.api.routes.resume_profiles import confirm_resume_import, parse_resume_import
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import ConfirmResumeImportRequest, ParseResumeImportRequest
from app.services.resume_import import parse_resume_text


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document_body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{document_body}</w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def test_parse_resume_text_extracts_ats_sections() -> None:
    preview = parse_resume_text(
        "resume.docx",
        "\n".join(
            [
                "Jane Doe",
                "Backend Engineer with international team experience.",
                "https://linkedin.com/in/jane-doe",
                "",
                "Skills",
                "Python, FastAPI, SQL",
                "",
                "Work Experience",
                "Senior Backend Engineer | Example Co",
                "Remote | 2022 - Present",
                "- Built deterministic APIs",
                "",
                "Languages",
                "English (Professional working proficiency)",
            ]
        ),
    )

    assert preview.summary is not None
    assert "international team experience" in preview.summary
    assert preview.skills == ["Python", "FastAPI", "SQL"]
    assert preview.work_experiences[0].company == "Example Co"
    assert preview.languages[0].name == "English"
    assert preview.links[0].link_type == "linkedin"


def test_parse_resume_import_accepts_docx_payload() -> None:
    docx_bytes = _build_docx_bytes(
        [
            "Summary",
            "Backend engineer with ATS-friendly resume.",
            "Skills",
            "Python, FastAPI",
        ]
    )
    response = parse_resume_import(
        ParseResumeImportRequest(
            filename="resume.docx",
            content_base64=base64.b64encode(docx_bytes).decode("ascii"),
        )
    )

    assert response.summary == "Backend engineer with ATS-friendly resume."
    assert response.skills == ["Python", "FastAPI"]


def test_confirm_resume_import_persists_reviewed_structured_data(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "resume_import_confirm.db")

    workspace = confirm_resume_import(
        ConfirmResumeImportRequest(
            summary="Candidate summary source",
            skills=["Python", "FastAPI"],
            work_experiences=[
                {
                    "company": "Example Co",
                    "title": "Backend Engineer",
                    "location": "Remote",
                    "start_date": "2022",
                    "end_date": "Present",
                    "summary": "Delivered backend APIs.",
                    "highlights": ["Built deterministic workflows."],
                }
            ],
            links=[
                {
                    "label": "LinkedIn",
                    "url": "https://linkedin.com/in/example",
                    "link_type": "linkedin",
                }
            ],
        ),
        job_store=store,
    )

    assert workspace.candidate_profile.summary == "Candidate summary source"
    assert [skill.name for skill in workspace.skills] == ["FastAPI", "Python"] or [skill.name for skill in workspace.skills] == ["Python", "FastAPI"]
    assert workspace.work_experiences[0].company == "Example Co"
    assert workspace.links[0].url == "https://linkedin.com/in/example"
