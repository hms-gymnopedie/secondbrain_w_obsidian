"""
Obsidian vault writer.
Creates notes in the Obsidian vault with proper structure and linking.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.schemas import (
    SummaryResult, SourceType, DeepAnalysisResult,
    SectionResult, AtomicConcept,
)
from backend.services.metadata import (
    generate_note_content,
    sanitize_filename,
    find_related_notes,
    update_moc,
)


def init_vault(vault_path: Optional[str] = None) -> None:
    """Initialize the Obsidian vault directory structure."""
    vault = Path(vault_path or settings.vault_path).resolve()

    # Create directories
    dirs = [
        vault / ".obsidian",
        vault / "00_Inbox",
        vault / "01_Sources",
        vault / "02_MOC",
        vault / "templates",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Create .obsidian/app.json if not exists
    app_json = vault / ".obsidian" / "app.json"
    if not app_json.exists():
        import json
        app_config = {
            "strictLineBreaks": False,
            "showFrontmatter": True,
            "livePreview": True,
        }
        app_json.write_text(json.dumps(app_config, indent=2), encoding="utf-8")

    # Create graph.json for graph view settings
    graph_json = vault / ".obsidian" / "graph.json"
    if not graph_json.exists():
        import json
        graph_config = {
            "collapse-filter": False,
            "search": "",
            "showTags": True,
            "showAttachments": False,
            "hideUnresolved": False,
            "showOrphans": True,
            "collapse-color-groups": False,
            "colorGroups": [
                {"query": "tag:#moc", "color": {"a": 1, "rgb": 65399}},
                {"query": "tag:#source", "color": {"a": 1, "rgb": 4514943}},
            ],
            "collapse-display": False,
            "showArrow": True,
            "textFadeMultiplier": 0,
            "nodeSizeMultiplier": 1,
            "lineSizeMultiplier": 1,
            "collapse-forces": False,
            "centerStrength": 0.518713248970312,
            "repelStrength": 10,
            "linkStrength": 1,
            "linkDistance": 250,
        }
        graph_json.write_text(json.dumps(graph_config, indent=2), encoding="utf-8")

    # Create source note template
    template_path = vault / "templates" / "source_note.md"
    if not template_path.exists():
        template = """---
title: "{{title}}"
type: source
tags: []
source: ""
source_type: ""
created: {{date}}
status: inbox
related: []
---

# {{title}}

> [!summary]
> 요약을 작성하세요.

## 키워드

## 핵심 내용
-

## 관련 노트
-

## 원본 정보
- 소스:
- 처리일: {{date}}
"""
        template_path.write_text(template, encoding="utf-8")

    # Create MOC index if not exists
    moc_index = vault / "02_MOC" / "_Index.md"
    if not moc_index.exists():
        index_content = f"""---
title: "MOC 인덱스"
type: moc
created: {datetime.now().strftime("%Y-%m-%d")}
---

# 📚 Maps of Content

모든 주제별 MOC를 모아놓은 인덱스입니다.

## 주제 목록
"""
        moc_index.write_text(index_content, encoding="utf-8")


async def write_note(
    summary_result: SummaryResult,
    source_type: SourceType,
    source_name: str,
    source_url: str = "",
    vault_path: Optional[str] = None,
) -> str:
    """Write a note to the Obsidian vault. Returns the vault-relative path."""
    vault = Path(vault_path or settings.vault_path).resolve()

    # Ensure vault is initialized
    init_vault(str(vault))

    # Find related notes from existing vault
    related_notes = find_related_notes(summary_result.keywords, str(vault))
    if related_notes:
        summary_result.related_topics = list(
            set(summary_result.related_topics + related_notes)
        )

    # Generate note content
    content = generate_note_content(
        summary_result, source_type, source_name, source_url
    )

    # Determine filename and path
    filename = sanitize_filename(summary_result.title) + ".md"
    note_dir = vault / "01_Sources"
    note_path = note_dir / filename

    # Avoid overwriting - add number suffix if exists
    counter = 1
    while note_path.exists():
        filename = f"{sanitize_filename(summary_result.title)} ({counter}).md"
        note_path = note_dir / filename
        counter += 1

    # Write the note
    note_path.write_text(content, encoding="utf-8")

    # Update MOCs for each keyword
    for keyword in summary_result.keywords[:5]:  # Top 5 keywords
        update_moc(keyword, summary_result.title, str(vault))

    # Update related notes (add backlink)
    for related in related_notes:
        _add_backlink(related, summary_result.title, str(vault))

    return str(note_path.relative_to(vault))


def _safe_write(directory: Path, title: str, content: str) -> Path:
    """Write a note file, avoiding overwrites with number suffixes."""
    filename = sanitize_filename(title) + ".md"
    note_path = directory / filename
    counter = 1
    while note_path.exists():
        filename = f"{sanitize_filename(title)} ({counter}).md"
        note_path = directory / filename
        counter += 1
    note_path.write_text(content, encoding="utf-8")
    return note_path


async def write_deep_notes(
    analysis: DeepAnalysisResult,
    source_type: SourceType,
    source_name: str,
    source_url: str = "",
    vault_path: Optional[str] = None,
) -> str:
    """Write a hierarchical set of notes from deep analysis.

    Creates:
    1. Parent note (overview) in 01_Sources/
    2. Section notes in 01_Sources/{parent_title}/
    3. Atomic concept notes in 03_Concepts/
    4. MOC entries for keywords
    5. Cross-links between all notes

    Returns the vault-relative path of the parent note.
    """
    vault = Path(vault_path or settings.vault_path).resolve()
    init_vault(str(vault))

    # Ensure concept directory exists
    concepts_dir = vault / "03_Concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    parent_title = analysis.title
    section_titles = []
    concept_titles = []

    # --- 1. Write section notes ---
    section_dir = vault / "01_Sources" / sanitize_filename(parent_title)
    section_dir.mkdir(parents=True, exist_ok=True)

    for section in analysis.sections:
        section_content = _generate_section_note(
            section, parent_title, source_name, source_url
        )
        section_path = _safe_write(section_dir, section.title, section_content)
        section_titles.append(section.title)

    # --- 2. Write atomic concept notes ---
    for concept in analysis.atomic_concepts:
        # Only create if doesn't already exist
        existing = list(concepts_dir.glob(f"{sanitize_filename(concept.name)}*.md"))
        if existing:
            # Add backlink to existing concept note
            _add_backlink(concept.name, parent_title, str(vault))
        else:
            concept_content = _generate_concept_note(concept, parent_title)
            _safe_write(concepts_dir, concept.name, concept_content)
        concept_titles.append(concept.name)

    # --- 3. Write parent note ---
    parent_content = _generate_parent_note(
        analysis, source_type, source_name, source_url,
        section_titles, concept_titles
    )
    parent_path = _safe_write(vault / "01_Sources", parent_title, parent_content)

    # --- 4. Update MOCs ---
    for keyword in analysis.keywords[:7]:
        update_moc(keyword, parent_title, str(vault))

    # --- 5. Cross-link with existing related notes ---
    related_notes = find_related_notes(analysis.keywords, str(vault))
    for related in related_notes:
        if related != parent_title:
            _add_backlink(related, parent_title, str(vault))

    return str(parent_path.relative_to(vault))


def _generate_parent_note(
    analysis: DeepAnalysisResult,
    source_type: SourceType,
    source_name: str,
    source_url: str,
    section_titles: list[str],
    concept_titles: list[str],
) -> str:
    """Generate the parent overview note content."""
    now_str = datetime.now().strftime("%Y-%m-%d")
    keywords_yaml = ", ".join(analysis.keywords) if analysis.keywords else ""
    related_yaml = "\n".join(
        f'  - "[[{t}]]"' for t in analysis.related_topics
    )

    sections_links = "\n".join(
        f"  - [[{t}]]" for t in section_titles
    )
    concept_links = "\n".join(
        f"  - [[{t}]]" for t in concept_titles
    )

    content = f"""---
title: "{analysis.title}"
type: {analysis.note_type.value}
document_type: {analysis.document_type}
tags: [{keywords_yaml}]
source: "{source_name}"
source_type: {source_type.value}
created: {now_str}
status: processed
analysis: deep
related:
{related_yaml}
---

# {analysis.title}

> [!summary]
> {analysis.overall_summary}

## 📑 문서 구조

이 문서는 **{len(section_titles)}개 섹션**과 **{len(concept_titles)}개 핵심 개념**으로 분해되었습니다.

### 섹션
{sections_links}

### 핵심 개념
{concept_links}

## 키워드
{' '.join('#' + kw for kw in analysis.keywords)}

## 원본 정보
- 소스: {source_name}"""

    if source_url:
        content += f"\n- URL: [{source_url}]({source_url})"

    content += f"\n- 유형: {analysis.document_type}"
    content += f"\n- 처리일: {now_str}"
    content += f"\n- 분석 방식: 심층 분해 (Deep Analysis)"

    return content


def _generate_section_note(
    section: SectionResult,
    parent_title: str,
    source_name: str,
    source_url: str,
) -> str:
    """Generate a section note content."""
    now_str = datetime.now().strftime("%Y-%m-%d")

    key_points_md = "\n".join(f"- {p}" for p in section.key_points) if section.key_points else "- (없음)"
    claims_md = "\n".join(f"- {c}" for c in section.claims) if section.claims else ""

    importance_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(section.importance, "⚪")

    content = f"""---
title: "{section.title}"
type: section
section_type: {section.section_type.value}
parent: "[[{parent_title}]]"
importance: {section.importance}
evidence_type: {section.evidence_type or 'none'}
position: {section.position}
created: {now_str}
---

# {section.title}

> [!info] 상위 문서: [[{parent_title}]] | 유형: `{section.section_type.value}` | 중요도: {importance_emoji} {section.importance}

## 요약
{section.summary}

## 핵심 포인트
{key_points_md}"""

    if claims_md:
        content += f"\n\n## 주요 주장\n{claims_md}"

    if section.evidence_type and section.evidence_type != "none":
        content += f"\n\n## 근거 유형\n`{section.evidence_type}` - 이 섹션의 논거는 {section.evidence_type} 기반입니다."

    content += f"\n\n---\n*출처: {source_name}*"

    return content


def _generate_concept_note(
    concept: AtomicConcept,
    parent_title: str,
) -> str:
    """Generate an atomic concept note."""
    now_str = datetime.now().strftime("%Y-%m-%d")
    related = "\n".join(f"- [[{t}]]" for t in concept.related_topics) if concept.related_topics else "- (없음)"

    importance_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(concept.importance, "⚪")

    return f"""---
title: "{concept.name}"
type: concept
importance: {concept.importance}
sources:
  - "[[{parent_title}]]"
created: {now_str}
---

# {concept.name}

> [!abstract] 중요도: {importance_emoji} {concept.importance}

## 정의
{concept.definition}

## 관련 주제
{related}

## 출처 문서
- [[{parent_title}]]
"""



def _add_backlink(
    existing_note_name: str,
    new_note_title: str,
    vault_path: str,
) -> None:
    """Add a backlink to an existing note pointing to the new note."""
    vault = Path(vault_path).resolve()

    # Find the existing note
    for md_file in vault.rglob("*.md"):
        if md_file.stem == existing_note_name:
            try:
                content = md_file.read_text(encoding="utf-8")
                backlink = f"[[{new_note_title}]]"

                # Only add if not already linked
                if backlink not in content:
                    # Try to add to "관련 노트" section
                    if "## 관련 노트" in content:
                        content = content.replace(
                            "## 관련 노트",
                            f"## 관련 노트\n- {backlink}",
                        )
                    else:
                        content += f"\n\n## 관련 노트\n- {backlink}\n"

                    md_file.write_text(content, encoding="utf-8")
            except Exception:
                pass
            break


def delete_note_from_vault(
    vault_path: str,
    note_title: str,
    keywords: list[str] = None,
) -> None:
    """Delete a note from the vault and clean up all references.

    1. Delete the note file itself
    2. Delete section subdirectory if it exists (deep analysis)
    3. Remove backlinks from other notes that reference this note
    4. Remove entries from MOC files
    """
    import re
    import shutil

    vault = Path(settings.vault_path).resolve()
    note_file = vault / vault_path

    print(f"🗑️ 삭제 시작: {note_file}")
    print(f"   Vault: {vault}")
    print(f"   파일 존재: {note_file.exists()}")

    # 1. Delete the note file
    if note_file.exists():
        note_file.unlink()
        print(f"   ✅ 파일 삭제 완료")
    else:
        print(f"   ⚠️ 파일을 찾을 수 없음")

    # 2. Delete section subdirectory (for deep analysis notes)
    section_dir = vault / "01_Sources" / sanitize_filename(note_title)
    if section_dir.exists() and section_dir.is_dir():
        shutil.rmtree(section_dir)
        print(f"   ✅ 섹션 폴더 삭제: {section_dir}")

    # 3. Remove backlinks from all other notes and cleanup orphans
    link_pattern = f"[[{note_title}]]"
    line_patterns = [
        f"- [[{note_title}]]",
        f"- {link_pattern}",
        f'- "{link_pattern}"',
    ]

    for md_file in vault.rglob("*.md"):
        if md_file == note_file:
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            if link_pattern not in content:
                continue

            original = content
            # Remove lines containing the link
            for pattern in line_patterns:
                content = content.replace(f"{pattern}\n", "")
                content = content.replace(pattern, "")

            # Also clean frontmatter related field
            content = re.sub(
                rf'- "\[\[{re.escape(note_title)}\]\]"\n?',
                "",
                content,
            )

            if content != original:
                md_file.write_text(content, encoding="utf-8")
                
                # Check for orphaned files
                file_str = str(md_file)
                
                # Clean up empty MOCs
                if "02_MOC" in file_str and md_file.name != "_Index.md":
                    remaining_links = re.findall(r"\[\[.+?\]\]", content)
                    if not remaining_links:
                        print(f"   🗑️ 빈 MOC 삭제: {md_file.name}")
                        md_file.unlink()
                        _remove_from_moc_index(md_file.stem)
                
                # Clean up empty Atomic Concepts
                elif "03_Concepts" in file_str:
                    sources_match = re.search(r"## 출처 문서\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
                    if sources_match:
                        source_links = re.findall(r"\[\[.+?\]\]", sources_match.group(1))
                        if not source_links:
                            print(f"   🗑️ 고아 원자 개념 삭제: {md_file.name}")
                            md_file.unlink()
                            
        except Exception as e:
            print(f"   ⚠️ 의존성 정리 중 오류 ({md_file.name}): {e}")
            continue


def _remove_from_moc_index(keyword: str) -> None:
    """Remove a keyword entry from the MOC index."""
    vault = Path(settings.vault_path).resolve()
    index_path = vault / "02_MOC" / "_Index.md"

    if not index_path.exists():
        return

    try:
        content = index_path.read_text(encoding="utf-8")
        link = f"- [[{keyword}]]"
        content = content.replace(f"{link}\n", "")
        content = content.replace(link, "")
        
        # Check if there are any remaining links
        remaining_links = re.findall(r"\[\[.+?\]\]", content)
        if not remaining_links:
            print(f"   🗑️ 빈 MOC 인덱스 파일 삭제: {index_path.name}")
            index_path.unlink()
        else:
            index_path.write_text(content, encoding="utf-8")
    except Exception:
        pass

