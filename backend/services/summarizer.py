"""
AI-powered content summarizer and keyword extractor.
Supports: OpenAI, Google Gemini, Ollama.
"""
import json
import re
from typing import Optional

from backend.config import settings
from backend.models.schemas import (
    SummaryResult, NoteType, DeepAnalysisResult,
    SectionResult, SectionType, AtomicConcept,
)


SYSTEM_PROMPT = """당신은 지식 관리 전문가입니다. 주어진 텍스트를 분석하여 다음을 JSON 형식으로 반환해주세요:

1. "title": 문서의 핵심을 담은 간결한 제목 (한국어)
2. "summary": 3~5문장의 핵심 요약 (한국어)
3. "keywords": 주요 키워드 5~10개 (한국어, 배열 형태)
4. "key_points": 핵심 포인트 3~5개 (한국어, 배열 형태)
5. "note_type": 문서 유형 (source, article, book, paper, web, image 중 택1)
6. "related_topics": 이 문서와 관련될 수 있는 상위 주제 2~4개 (한국어, 배열 형태)

JSON만 반환하고, 다른 텍스트는 포함하지 마세요.
"""

USER_PROMPT_TEMPLATE = """다음 텍스트를 분석해주세요:

---
제목: {title}
소스: {source}

{text}
---
"""

# Minimum text length to trigger deep analysis
DEEP_ANALYSIS_THRESHOLD = 3000

DEEP_ANALYSIS_PROMPT = """당신은 학술 문서 분석 전문가입니다. 주어진 문서를 **논리적 섹션으로 분해**하고, **핵심 개념을 원자 단위로 추출**하여 JSON으로 반환해주세요.

반환 형식:
{
  "title": "문서의 핵심 제목 (한국어)",
  "overall_summary": "전체 문서 5~7문장 핵심 요약 (한국어)",
  "document_type": "paper / report / article / book 중 택1",
  "keywords": ["키워드1", "키워드2", ...],  // 5~10개
  "note_type": "source / article / book / paper / web 중 택1",
  "sections": [
    {
      "section_type": "background / introduction / methodology / results / discussion / conclusion / literature_review / analysis / other 중 택1",
      "title": "섹션 제목 (한국어)",
      "summary": "2~4문장 요약 (한국어)",
      "key_points": ["핵심1", "핵심2"],
      "importance": "high / medium / low",
      "evidence_type": "empirical / theoretical / statistical / qualitative / none 중 택1",
      "claims": ["주장1", "주장2"],
      "position": 1
    }
  ],
  "atomic_concepts": [
    {
      "name": "개념 이름 (한국어)",
      "definition": "1~2문장 정의 (한국어)",
      "related_topics": ["관련주제1", "관련주제2"],
      "importance": "high / medium / low"
    }
  ],
  "related_topics": ["상위주제1", "상위주제2"]
}

규칙:
- sections는 문서의 논리적 구조에 따라 3~8개로 분해
- atomic_concepts는 이 문서에서 가장 중요한 개념/용어 3~7개 추출
- 각 개념은 다른 문서에서도 재사용 가능한 독립적 지식 단위
- importance가 "high"인 항목은 핵심 내용
- JSON만 반환하고, 다른 텍스트는 포함하지 마세요.
"""


async def summarize_content(
    text: str,
    title: str = "",
    source: str = "",
    provider: Optional[str] = None,
) -> SummaryResult:
    """Summarize content and extract keywords using AI."""
    provider = provider or settings.ai_provider

    # Truncate text if too long (max ~8000 chars for summarization)
    truncated = _truncate_text(text, max_chars=8000)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title or "Unknown",
        source=source or "Unknown",
        text=truncated,
    )

    try:
        if provider == "openai":
            result = await _call_openai(user_prompt)
        elif provider == "gemini":
            result = await _call_gemini(user_prompt)
        elif provider == "ollama":
            result = await _call_ollama(user_prompt)
        else:
            raise ValueError(f"Unknown AI provider: {provider}")

        return _parse_ai_response(result, title)

    except Exception as e:
        # Fallback: return basic result
        return SummaryResult(
            title=title or "Untitled",
            summary=f"AI 요약 실패: {str(e)}",
            keywords=_extract_basic_keywords(text),
            key_points=["AI 요약을 사용할 수 없습니다."],
            note_type=NoteType.SOURCE,
            related_topics=[],
        )


async def _call_openai(user_prompt: str) -> str:
    """Call OpenAI API."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content or ""


async def _call_gemini(user_prompt: str) -> str:
    """Call Google Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
    response = model.generate_content(full_prompt)

    return response.text or ""


async def _call_ollama(user_prompt: str) -> str:
    """Call local Ollama API."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": f"{SYSTEM_PROMPT}\n\n{user_prompt}",
                "stream": False,
                "format": "json",
            },
            timeout=120.0,
        )
        result = response.json()
        return result.get("response", "")


def _parse_ai_response(response_text: str, fallback_title: str = "") -> SummaryResult:
    """Parse AI response JSON into SummaryResult."""
    try:
        # Try to extract JSON from response
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(response_text)

        return SummaryResult(
            title=data.get("title", fallback_title or "Untitled"),
            summary=data.get("summary", ""),
            keywords=data.get("keywords", []),
            key_points=data.get("key_points", []),
            note_type=NoteType(data.get("note_type", "source")),
            related_topics=data.get("related_topics", []),
        )
    except (json.JSONDecodeError, ValueError) as e:
        return SummaryResult(
            title=fallback_title or "Untitled",
            summary=response_text[:500] if response_text else "파싱 실패",
            keywords=[],
            key_points=[],
            note_type=NoteType.SOURCE,
            related_topics=[],
        )


def _truncate_text(text: str, max_chars: int = 8000) -> str:
    """Truncate text to max characters while trying to keep complete sentences."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    # Try to cut at the last sentence boundary
    last_period = max(
        truncated.rfind(". "),
        truncated.rfind(".\n"),
        truncated.rfind("다. "),
        truncated.rfind("다.\n"),
    )
    if last_period > max_chars * 0.5:
        truncated = truncated[: last_period + 1]

    return truncated + "\n\n[... 이하 생략 ...]"


def _extract_basic_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Fallback: extract basic keywords from text without AI."""
    import re
    from collections import Counter

    # Simple word frequency based keyword extraction
    words = re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", text)
    # Filter common stop words
    stop_words = {"있는", "하는", "것을", "이는", "대한", "위한", "통해", "따라", "에서", "으로", "the", "and", "for", "with"}
    filtered = [w for w in words if w.lower() not in stop_words]
    counter = Counter(filtered)
    return [word for word, _ in counter.most_common(max_keywords)]


def should_deep_analyze(text: str) -> bool:
    """Determine if a document should use deep analysis based on length."""
    return len(text.strip()) >= DEEP_ANALYSIS_THRESHOLD


async def analyze_document_deep(
    text: str,
    title: str = "",
    source: str = "",
    provider: Optional[str] = None,
) -> DeepAnalysisResult:
    """Perform deep hierarchical analysis on a large document."""
    provider = provider or settings.ai_provider

    # Allow more text for deep analysis (up to 15K chars)
    truncated = _truncate_text(text, max_chars=15000)

    user_prompt = f"""다음 문서를 심층 분석해주세요:

---
제목: {title or 'Unknown'}
소스: {source or 'Unknown'}

{truncated}
---
"""

    try:
        if provider == "openai":
            result = await _call_openai_deep(user_prompt)
        elif provider == "gemini":
            result = await _call_gemini_deep(user_prompt)
        elif provider == "ollama":
            result = await _call_ollama_deep(user_prompt)
        else:
            raise ValueError(f"Unknown AI provider: {provider}")

        return _parse_deep_response(result, title)

    except Exception as e:
        # Fallback: return basic result
        return DeepAnalysisResult(
            title=title or "Untitled",
            overall_summary=f"심층 분석 실패: {str(e)}",
            keywords=_extract_basic_keywords(text),
            sections=[],
            atomic_concepts=[],
        )


async def _call_openai_deep(user_prompt: str) -> str:
    """Call OpenAI API for deep analysis."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": DEEP_ANALYSIS_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


async def _call_gemini_deep(user_prompt: str) -> str:
    """Call Google Gemini API for deep analysis."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    full_prompt = f"{DEEP_ANALYSIS_PROMPT}\n\n{user_prompt}"
    response = model.generate_content(full_prompt)
    return response.text or ""


async def _call_ollama_deep(user_prompt: str) -> str:
    """Call local Ollama API for deep analysis."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": f"{DEEP_ANALYSIS_PROMPT}\n\n{user_prompt}",
                "stream": False,
                "format": "json",
            },
            timeout=180.0,
        )
        result = response.json()
        return result.get("response", "")


def _parse_deep_response(response_text: str, fallback_title: str = "") -> DeepAnalysisResult:
    """Parse deep analysis AI response JSON."""
    try:
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(response_text)

        sections = []
        for i, sec in enumerate(data.get("sections", [])):
            try:
                section_type = SectionType(sec.get("section_type", "other"))
            except ValueError:
                section_type = SectionType.OTHER

            sections.append(SectionResult(
                section_type=section_type,
                title=sec.get("title", f"섹션 {i + 1}"),
                summary=sec.get("summary", ""),
                key_points=sec.get("key_points", []),
                importance=sec.get("importance", "medium"),
                evidence_type=sec.get("evidence_type", ""),
                claims=sec.get("claims", []),
                position=sec.get("position", i + 1),
            ))

        concepts = []
        for concept in data.get("atomic_concepts", []):
            concepts.append(AtomicConcept(
                name=concept.get("name", ""),
                definition=concept.get("definition", ""),
                related_topics=concept.get("related_topics", []),
                importance=concept.get("importance", "medium"),
            ))

        return DeepAnalysisResult(
            title=data.get("title", fallback_title or "Untitled"),
            overall_summary=data.get("overall_summary", ""),
            document_type=data.get("document_type", ""),
            keywords=data.get("keywords", []),
            note_type=NoteType(data.get("note_type", "source")),
            sections=sections,
            atomic_concepts=concepts,
            related_topics=data.get("related_topics", []),
        )

    except (json.JSONDecodeError, ValueError) as e:
        return DeepAnalysisResult(
            title=fallback_title or "Untitled",
            overall_summary=response_text[:500] if response_text else "파싱 실패",
            keywords=[],
            sections=[],
            atomic_concepts=[],
        )

