"""
Obsidian vault writer.
Creates notes in the Obsidian vault with proper structure and linking.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.schemas import SummaryResult, SourceType
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
    2. Remove backlinks from other notes that reference this note
    3. Remove entries from MOC files
    """
    import re

    vault = Path(settings.vault_path).resolve()
    note_file = vault / vault_path

    # 1. Delete the note file
    if note_file.exists():
        note_file.unlink()

    # 2. Remove backlinks from all other notes
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
        except Exception:
            continue

    # 3. Remove entries from MOC files
    if keywords:
        moc_dir = vault / "02_MOC"
        if moc_dir.exists():
            for keyword in keywords:
                moc_file = moc_dir / f"{sanitize_filename(keyword)}.md"
                if moc_file.exists():
                    try:
                        content = moc_file.read_text(encoding="utf-8")
                        original = content
                        for pattern in line_patterns:
                            content = content.replace(f"{pattern}\n", "")
                            content = content.replace(pattern, "")

                        if content != original:
                            # Check if MOC has no more note links
                            remaining_links = re.findall(r"\[\[.+?\]\]", content)
                            if not remaining_links:
                                # Delete empty MOC
                                moc_file.unlink()
                                # Remove from index
                                _remove_from_moc_index(keyword)
                            else:
                                moc_file.write_text(content, encoding="utf-8")
                    except Exception:
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
        index_path.write_text(content, encoding="utf-8")
    except Exception:
        pass

