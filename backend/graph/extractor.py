import logging
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


class EntityEdgeExtractor:
    """
    마크다운 텍스트에서 엔티티 및 관계(Edge)를 추출하는 파이프라인 클래스입니다.
    """

    # 위키링크 정규식 (예: [[Note Title]])
    WIKILINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")

    # 해시태그 정규식 (예: #tag_name)
    # URL 파편화(예: http://example#section) 등에 매치되지 않도록 앞이 공백이거나 문자열의 시작점일 것 강제
    TAG_PATTERN = re.compile(r"(?:^|\s)#([a-zA-Z0-9_\uac00-\ud7a3]+)")

    def __init__(self, max_content_length: int = 4000):
        """
        Args:
            max_content_length: LLM 토큰 초과(Context Window Overflow) 방지를 위한 최대 텍스트 문자 수 제한.
                                설정값에 따라 주입(Injection) 가능. (기본 4000자는 약 1000~2000 토큰 마진)
        """
        self.max_content_length = max_content_length

    def extract_explicit_edges(
        self, source_node_id: str, markdown_content: str
    ) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        마크다운 본문에서 위키링크와 태그를 파싱하여 명시적 엣지를 생성합니다.
        중복된 위키링크나 태그는 정규화(Normalization) 후 엣지의 가중치(weight)에 등장 빈도로 반영됩니다.

        Args:
            source_node_id: 출발 노드 ID (현재 노트 등)
            markdown_content: 파싱할 마크다운 텍스트

        Returns:
            생성된 명시적 엣지 목록: List of (source_node_id, target_node_id, attrs)
        """
        edges = []

        # 1. 위키링크 추출 (등장 빈도 기반 가중치 부여)
        wikilink_matches = self.WIKILINK_PATTERN.findall(markdown_content)

        # 정규화된 canonical_target 리스트를 먼저 생성하여 동일한 타깃은 올바르게 집계되도록 함
        normalized_targets = []
        aliases_map: defaultdict[str, List[str]] = defaultdict(list)

        for raw_target in wikilink_matches:
            raw_target = raw_target.strip()
            if not raw_target:
                continue

            # [[Title|Alias]] 형태 지원: 좌측을 canonical ID로 사용
            if "|" in raw_target:
                canonical_target, alias = raw_target.split("|", 1)
                canonical_target = canonical_target.strip()
                alias = alias.strip()
            else:
                canonical_target = raw_target
                alias = None

            if not canonical_target:
                continue

            normalized_targets.append(canonical_target)
            if alias and alias not in aliases_map[canonical_target]:
                # 결정론적이고 손실 없는 별칭 수집 (중복 방지 리스트 추가)
                aliases_map[canonical_target].append(alias)

        wikilink_counts = Counter(normalized_targets)
        for canonical_target, count in wikilink_counts.items():
            attrs: Dict[str, Any] = {
                "weight": float(count),
                "edge_type": "explicit",
                "relation": "wikilink",
            }
            if canonical_target in aliases_map and aliases_map[canonical_target]:
                # 하위 호환성(Backwards Compatibility) 보장: 단일 스칼라 타입(가장 처음 발견된 별칭)
                attrs["alias"] = aliases_map[canonical_target][0]
                # 결정론적이고 손실 없는 전체 별칭 리스트 보존
                attrs["aliases"] = aliases_map[canonical_target]

            edges.append((source_node_id, canonical_target, attrs))

        # 2. 태그 추출 (등장 빈도 기반 가중치 부여)
        # 생성기 표현식에서 이미 tag.strip() 정규화가 선행되어 카운트 됨
        if tag_matches := self.TAG_PATTERN.findall(markdown_content):
            tag_counts = Counter(
                tag.strip() for tag in tag_matches if tag and tag.strip()
            )
            edges.extend(
                (
                    source_node_id,
                    f"#{tag}",
                    {
                        "weight": float(count),
                        "edge_type": "explicit",
                        "relation": "tag",
                    },
                )
                for tag, count in tag_counts.items()
            )

        return edges

    async def extract_implicit_edges(
        self, source_node_id: str, content: str, llm_client: Any
    ) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        LLM 또는 NLP 모듈을 연동하여 텍스트의 키워드 및 문맥 유사도 기반의
        암묵적 엣지(Implicit Edge)를 추출하고 가중치를 부여합니다.

        Args:
            source_node_id: 출발 노드 ID
            content: 분석할 텍스트 내용
            llm_client: LangChain 호환 LLM 인터페이스 또는 OpenAI 클라이언트 인스턴스 (의존성 주입)

        Returns:
            생성된 암묵적 엣지 목록: List of (source_node_id, target_node_id, attrs)
        """
        edges = []

        if not content.strip() or not llm_client:
            return edges

        # 긴 노트로 인한 LLM 토큰 초과 방어적 코딩 (Truncation)
        original_length = len(content)
        is_truncated = original_length > self.max_content_length

        if is_truncated:
            truncated_length = self.max_content_length
            logger.warning(
                "[Graph Extraction] Note '%s' exceeds max_content_length (%d chars). "
                "Truncating content for LLM safety (original_length=%d, truncated_length=%d).",
                source_node_id,
                self.max_content_length,
                original_length,
                truncated_length,
            )
            truncated_content = content[: self.max_content_length]
        else:
            truncated_content = content

        # Downstream consumers(로그 및 트레이싱)를 위해 관측 가능한(Observable) 메타데이터 구성
        truncation_metadata = {
            "is_truncated": is_truncated,
            "original_length": original_length,
            "used_length": len(truncated_content),
        }

        # LLM 프롬프트 구성 (System / User Message 형태로 확장을 고려)
        prompt_text = (
            "Analyze the following text and extract up to 3 core related keywords or entities. "
            "Return ONLY a comma-separated list of keywords, without any extra text.\n\n"
            f"Text: {truncated_content}"
        )

        try:
            # 구조화된 로깅(Structured Logging)에 메타데이터를 추가하여 디버깅 가시성 극대화
            logger.info(
                "[Graph Extraction] Invoking LLM for implicit edges (node_id=%s)",
                source_node_id,
                extra={
                    "node_id": source_node_id,
                    "truncation_metadata": truncation_metadata,
                },
            )

            response = await llm_client.ainvoke([HumanMessage(content=prompt_text)])
            response_text = str(response.content).strip()

            # 파싱 로직 (쉼표 분리) 및 중복 제거
            raw_keywords = [kw.strip() for kw in response_text.split(",") if kw.strip()]

            # 프롬프트 제약 보장: 최대 3개 키워드만 제한 및 순서 유지 중복 제거 방어 로직
            extracted_keywords = list(dict.fromkeys(raw_keywords))[:3]

            # 암묵적 엣지에는 명시적 엣지보다 낮은 기본 가중치 부여 (예: 0.5)
            edges.extend(
                (
                    source_node_id,
                    keyword,
                    {
                        "weight": 0.5,
                        "edge_type": "implicit",
                        "relation": "semantic_keyword",
                    },
                )
                for keyword in extracted_keywords
            )

        except Exception as exc:
            # LLM 연동 실패 시 애플리케이션의 중단을 막기 위해 예외 캡처 및 로깅
            # ai_bot_review_summary 체크리스트에 따라 logger.exception()을 사용하여 Stack Trace 기록
            logger.exception(
                f"[Graph Extraction] Failed to extract implicit edges for node {source_node_id}"
            )

        return edges
