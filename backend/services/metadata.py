"""
Metadata generator for Obsidian notes.
Creates YAML frontmatter and manages links between notes.
"""
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml

from backend.config import settings
from backend.models.schemas import SummaryResult, SourceType


def generate_frontmatter(
    summary_result: SummaryResult,
    source_type: SourceType,
    source_name: str,
    source_url: str = "",
) -> str:
    """Generate YAML frontmatter for an Obsidian note."""
    frontmatter = {
        "title": summary_result.title,
        "type": summary_result.note_type.value,
        "tags": summary_result.keywords,
        "aliases": [summary_result.title] if summary_result.title else [],
        "source": source_url or source_name,
        "source_type": source_type.value,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "status": "processed",
        "related": [f"[[{topic}]]" for topic in summary_result.related_topics],
    }

    # Clean up empty values
    frontmatter = {k: v for k, v in frontmatter.items() if v}

    return yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def generate_note_content(
    summary_result: SummaryResult,
    source_type: SourceType,
    source_name: str,
    source_url: str = "",
) -> str:
    """Generate full Obsidian note content with frontmatter."""
    frontmatter = generate_frontmatter(summary_result, source_type, source_name, source_url)

    # Build tags line
    tags_line = " ".join([f"#{kw.replace(' ', '_')}" for kw in summary_result.keywords])

    # Build key points
    key_points = "\n".join([f"- {point}" for point in summary_result.key_points])

    # Build related notes links
    related_links = "\n".join(
        [f"- [[{topic}]]" for topic in summary_result.related_topics]
    )

    # Source info
    source_info = source_url if source_url else source_name
    source_line = f"- 소스: {source_info}"
    if source_url:
        source_line = f"- 소스: [{source_name}]({source_url})"

    note = f"""---
{frontmatter.strip()}
---

# {summary_result.title}

> [!summary]
> {summary_result.summary}

## 키워드
{tags_line}

## 핵심 내용
{key_points}

## 관련 노트
{related_links if related_links else "- (관련 노트 없음)"}

## 원본 정보
{source_line}
- 유형: {source_type.value}
- 처리일: {datetime.now().strftime("%Y-%m-%d %H:%M")}
"""
    return note


def sanitize_filename(title: str) -> str:
    """Sanitize a title to be used as a filename."""
    # Remove characters not allowed in filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', "", title)
    # Replace multiple spaces with single space
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100].strip()
    return sanitized or "Untitled"


def find_related_notes(
    keywords: List[str],
    vault_path: Optional[str] = None,
) -> List[str]:
    """Scan existing vault notes to find related ones based on keywords."""
    vault = Path(vault_path or settings.vault_path).resolve()
    related = []

    if not vault.exists():
        return related

    for md_file in vault.rglob("*.md"):
        # Skip templates
        if "templates" in str(md_file):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")

            # Check if any keyword appears in the note
            for keyword in keywords:
                if keyword.lower() in content.lower():
                    note_name = md_file.stem
                    if note_name not in related:
                        related.append(note_name)
                    break
        except Exception:
            continue

    return related[:10]  # Limit to 10 related notes


def update_moc(
    keyword: str,
    note_title: str,
    vault_path: Optional[str] = None,
) -> None:
    """Update or create a Map of Content (MOC) note for a keyword."""
    vault = Path(vault_path or settings.vault_path).resolve()
    moc_dir = vault / "02_MOC"
    moc_dir.mkdir(parents=True, exist_ok=True)

    moc_filename = sanitize_filename(keyword) + ".md"
    moc_path = moc_dir / moc_filename

    note_link = f"- [[{note_title}]]"

    if moc_path.exists():
        content = moc_path.read_text(encoding="utf-8")
        if note_link not in content:
            content += f"\n{note_link}"
            moc_path.write_text(content, encoding="utf-8")
    else:
        moc_content = f"""---
title: "{keyword}"
type: moc
created: {datetime.now().strftime("%Y-%m-%d")}
---

# {keyword}

이 MOC는 **{keyword}** 관련 노트를 모아놓은 페이지입니다.

## 관련 노트
{note_link}
"""
        moc_path.write_text(moc_content, encoding="utf-8")

    # Update index
    _update_moc_index(keyword, vault_path)


def _update_moc_index(keyword: str, vault_path: Optional[str] = None) -> None:
    """Update the MOC index file."""
    vault = Path(vault_path or settings.vault_path).resolve()
    index_path = vault / "02_MOC" / "_Index.md"

    link = f"- [[{keyword}]]"

    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        if link not in content:
            content += f"\n{link}"
            index_path.write_text(content, encoding="utf-8")
    else:
        index_content = f"""---
title: "MOC 인덱스"
type: moc
created: {datetime.now().strftime("%Y-%m-%d")}
---

# 📚 Maps of Content

모든 주제별 MOC를 모아놓은 인덱스입니다.

## 주제 목록
{link}
"""
        index_path.write_text(index_content, encoding="utf-8")
