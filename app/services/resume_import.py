import base64
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.schemas.jobs import (
    ImportedResumeCertification,
    ImportedResumeEducation,
    ImportedResumeLanguage,
    ImportedResumeLink,
    ImportedResumeProject,
    ImportedResumeWorkExperience,
    ResumeImportPreview,
)


_SECTION_ALIASES = {
    "summary": {"summary", "professional summary", "profile", "about", "about me"},
    "skills": {"skills", "technical skills", "core skills", "competencies"},
    "experience": {"experience", "work experience", "professional experience", "employment history"},
    "projects": {"projects", "selected projects"},
    "education": {"education", "academic background"},
    "certifications": {"certifications", "licenses", "licenses and certifications"},
    "languages": {"languages", "language"},
}

_LINK_PATTERN = re.compile(r"https?://[^\s)>\]]+|www\.[^\s)>\]]+")
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"(19|20)\d{2}")
_SKILL_SPLIT_PATTERN = re.compile(r"\s*[|,;/]\s*")


def parse_resume_upload(filename: str, content_base64: str) -> ResumeImportPreview:
    content = base64.b64decode(content_base64)
    raw_text = extract_resume_text(filename, content)
    return parse_resume_text(filename, raw_text)


def extract_resume_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(content)
    if suffix == ".docx":
        return _extract_docx_text(content)
    raise ValueError("Only PDF and DOCX resumes are supported.")


def parse_resume_text(filename: str, raw_text: str) -> ResumeImportPreview:
    normalized_text = _normalize_text(raw_text)
    lines = [line.strip() for line in normalized_text.splitlines()]
    section_map, preamble_lines = _split_sections(lines)
    warnings: list[str] = []
    ambiguous_sections: list[str] = []

    if not section_map:
        warnings.append("No clear ATS section headings were detected. Review all extracted fields carefully.")

    summary = _extract_summary(section_map, preamble_lines)
    if summary is None and preamble_lines:
        ambiguous_sections.append("summary")

    skills = _extract_skills(section_map)
    if "skills" not in section_map and skills:
        ambiguous_sections.append("skills")

    work_experiences = _extract_work_experiences(section_map.get("experience", []))
    if section_map.get("experience") and not work_experiences:
        warnings.append("Work experience section was detected but could not be reliably structured.")
        ambiguous_sections.append("experience")

    projects = _extract_projects(section_map.get("projects", []))
    if section_map.get("projects") and not projects:
        ambiguous_sections.append("projects")

    education = _extract_education(section_map.get("education", []))
    certifications = _extract_certifications(section_map.get("certifications", []))
    languages = _extract_languages(section_map.get("languages", []))
    links = _extract_links(normalized_text)

    if not languages and "languages" in section_map:
        ambiguous_sections.append("languages")

    return ResumeImportPreview(
        filename=filename,
        raw_text=normalized_text,
        summary=summary,
        skills=skills,
        work_experiences=work_experiences,
        projects=projects,
        education=education,
        certifications=certifications,
        languages=languages,
        links=links,
        warnings=warnings,
        ambiguous_sections=sorted(set(ambiguous_sections)),
    )


def _extract_pdf_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(content)
        handle.flush()
        result = subprocess.run(
            ["pdftotext", "-layout", handle.name, "-"],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise ValueError("PDF parsing failed.")
    return result.stdout


def _extract_docx_text(content: bytes) -> str:
    with tempfile.SpooledTemporaryFile() as buffer:
        buffer.write(content)
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as archive:
            document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        paragraph_text = "".join(texts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)
    return "\n".join(paragraphs)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sections(lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    sections: dict[str, list[str]] = {}
    preamble: list[str] = []
    current_section: str | None = None

    for line in lines:
        if not line:
            if current_section is not None:
                sections.setdefault(current_section, []).append("")
            elif preamble and preamble[-1] != "":
                preamble.append("")
            continue

        normalized = re.sub(r"[:\s]+$", "", line.strip().lower())
        matched_section = next(
            (section for section, aliases in _SECTION_ALIASES.items() if normalized in aliases),
            None,
        )
        if matched_section is not None:
            current_section = matched_section
            sections.setdefault(current_section, [])
            continue

        if current_section is None:
            preamble.append(line)
        else:
            sections.setdefault(current_section, []).append(line)

    return sections, preamble


def _extract_summary(section_map: dict[str, list[str]], preamble_lines: list[str]) -> str | None:
    summary_lines = [line for line in section_map.get("summary", []) if line]
    if summary_lines:
        return "\n".join(summary_lines).strip()

    cleaned = [
        line for line in preamble_lines
        if line
        and not _EMAIL_PATTERN.search(line)
        and not _LINK_PATTERN.search(line)
        and len(line.split()) > 4
    ]
    if not cleaned:
        return None
    return " ".join(cleaned[:3]).strip()


def _extract_skills(section_map: dict[str, list[str]]) -> list[str]:
    skill_lines = [line for line in section_map.get("skills", []) if line]
    skills: list[str] = []
    for line in skill_lines:
        stripped = line.lstrip("-• ").strip()
        if not stripped:
            continue
        for chunk in _SKILL_SPLIT_PATTERN.split(stripped):
            normalized = chunk.strip()
            if normalized:
                skills.append(normalized)
    return _dedupe_strings(skills)


def _extract_work_experiences(lines: list[str]) -> list[ImportedResumeWorkExperience]:
    entries = _split_blocks(lines)
    experiences: list[ImportedResumeWorkExperience] = []
    for block in entries:
        if not block:
            continue
        header = block[0]
        title, company = _split_title_company(header)
        if not title and not company:
            continue
        location = None
        start_date = None
        end_date = None
        summary = None
        highlights: list[str] = []
        for line in block[1:]:
            if _looks_like_date_line(line) and (start_date is None and end_date is None):
                start_date, end_date, location = _parse_meta_line(line)
                continue
            if line.startswith(("-", "•")):
                highlights.append(line.lstrip("-• ").strip())
                continue
            if summary is None:
                summary = line
            else:
                highlights.append(line)
        experiences.append(
            ImportedResumeWorkExperience(
                company=company or "Unknown Company",
                title=title or "Unknown Title",
                location=location,
                start_date=start_date,
                end_date=end_date,
                summary=summary,
                highlights=highlights,
            )
        )
    return experiences


def _extract_projects(lines: list[str]) -> list[ImportedResumeProject]:
    projects: list[ImportedResumeProject] = []
    for block in _split_blocks(lines):
        if not block:
            continue
        name = block[0]
        role = None
        summary = None
        technologies: list[str] = []
        url = None
        for line in block[1:]:
            if _LINK_PATTERN.search(line):
                url = _LINK_PATTERN.search(line).group(0)
                continue
            if line.lower().startswith("technologies:"):
                technologies.extend(comma_parts(line.split(":", 1)[1]))
                continue
            if role is None and ("|" in line or " at " in line.lower()):
                role = line
                continue
            if summary is None:
                summary = line
        projects.append(
            ImportedResumeProject(
                name=name,
                role=role,
                summary=summary,
                technologies=_dedupe_strings(technologies),
                url=url,
            )
        )
    return projects


def _extract_education(lines: list[str]) -> list[ImportedResumeEducation]:
    items: list[ImportedResumeEducation] = []
    for block in _split_blocks(lines):
        if not block:
            continue
        degree, institution = _split_degree_institution(block[0])
        start_date = None
        end_date = None
        summary = None
        field = None
        for line in block[1:]:
            if _looks_like_date_line(line) and start_date is None and end_date is None:
                start_date, end_date, _ = _parse_meta_line(line)
                continue
            if field is None and line.lower().startswith("field"):
                field = line.split(":", 1)[-1].strip()
                continue
            if summary is None:
                summary = line
        items.append(
            ImportedResumeEducation(
                institution=institution or "Unknown Institution",
                degree=degree or "Unknown Degree",
                field_of_study=field,
                start_date=start_date,
                end_date=end_date,
                summary=summary,
            )
        )
    return items


def _extract_certifications(lines: list[str]) -> list[ImportedResumeCertification]:
    items: list[ImportedResumeCertification] = []
    for line in [line for line in lines if line]:
        parts = [part.strip() for part in re.split(r"\s+\|\s+|\s+-\s+", line) if part.strip()]
        if not parts:
            continue
        name = parts[0]
        issuer = parts[1] if len(parts) > 1 else "Unknown Issuer"
        items.append(
            ImportedResumeCertification(
                name=name,
                issuer=issuer,
                issued_on=parts[2] if len(parts) > 2 else None,
            )
        )
    return items


def _extract_languages(lines: list[str]) -> list[ImportedResumeLanguage]:
    items: list[ImportedResumeLanguage] = []
    for line in [line for line in lines if line]:
        stripped = line.lstrip("-• ").strip()
        if not stripped:
            continue
        if "(" in stripped and ")" in stripped:
            name, proficiency = stripped.split("(", 1)
            items.append(
                ImportedResumeLanguage(
                    name=name.strip(),
                    proficiency=proficiency.rstrip(")").strip(),
                )
            )
            continue
        parts = [part.strip() for part in re.split(r"\s+\|\s+|\s+-\s+|:\s*", stripped) if part.strip()]
        if len(parts) >= 2:
            items.append(ImportedResumeLanguage(name=parts[0], proficiency=parts[1]))
    return items


def _extract_links(text: str) -> list[ImportedResumeLink]:
    urls = _dedupe_strings([_normalize_url(match.group(0)) for match in _LINK_PATTERN.finditer(text)])
    links: list[ImportedResumeLink] = []
    for url in urls:
        lower = url.lower()
        link_type = None
        label = url
        if "linkedin.com" in lower:
            link_type = "linkedin"
            label = "LinkedIn"
        elif "github.com" in lower:
            link_type = "github"
            label = "GitHub"
        elif "portfolio" in lower:
            link_type = "portfolio"
            label = "Portfolio"
        links.append(ImportedResumeLink(label=label, url=url, link_type=link_type))
    return links


def _split_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _split_title_company(header: str) -> tuple[str | None, str | None]:
    if "|" in header:
        left, right = [part.strip() for part in header.split("|", 1)]
        return left or None, right or None
    if " at " in header.lower():
        parts = re.split(r"\s+at\s+", header, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return parts[0].strip() or None, parts[1].strip() or None
    return header.strip() or None, None


def _split_degree_institution(header: str) -> tuple[str | None, str | None]:
    if "|" in header:
        left, right = [part.strip() for part in header.split("|", 1)]
        return left or None, right or None
    if " - " in header:
        left, right = [part.strip() for part in header.split(" - ", 1)]
        return left or None, right or None
    return header.strip() or None, None


def _looks_like_date_line(line: str) -> bool:
    lower = line.lower()
    return bool(_YEAR_PATTERN.search(line) or "present" in lower)


def _parse_meta_line(line: str) -> tuple[str | None, str | None, str | None]:
    parts = [part.strip() for part in re.split(r"\s+\|\s+| · ", line) if part.strip()]
    date_part = next((part for part in parts if _looks_like_date_line(part)), None)
    location = next((part for part in parts if part != date_part), None)
    start_date = None
    end_date = None
    if date_part:
        date_parts = re.split(r"\s*-\s*|\s+to\s+", date_part, maxsplit=1)
        start_date = date_parts[0].strip() if date_parts else None
        end_date = date_parts[1].strip() if len(date_parts) > 1 else None
    return start_date, end_date, location


def comma_parts(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_url(value: str) -> str:
    return value if value.startswith("http") else f"https://{value}"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result
