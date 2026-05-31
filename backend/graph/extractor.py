import re
from typing import List, Tuple, Dict, Any

class EntityEdgeExtractor:
    """
    마크다운 텍스트에서 엔티티 및 관계(Edge)를 추출하는 파이프라인 클래스입니다.
    """

    # 위키링크 정규식 (예: [[Note Title]])
    WIKILINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")
    
    # 해시태그 정규식 (예: #tag_name, 공백이나 구두점으로 끝남)
    # 영문, 숫자, 한글, 언더바 등 지원
    TAG_PATTERN = re.compile(r"#([a-zA-Z0-9_\uac00-\ud7a3]+)")

    def extract_explicit_edges(self, source_node_id: str, markdown_content: str) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        마크다운 본문에서 위키링크와 태그를 파싱하여 명시적 엣지를 생성합니다.
        
        Args:
            source_node_id: 출발 노드 ID (현재 노트 등)
            markdown_content: 파싱할 마크다운 텍스트
            
        Returns:
            생성된 명시적 엣지 목록: List of (source_node_id, target_node_id, attrs)
        """
        edges = []
        
        # 1. 위키링크 추출
        wikilinks = set(self.WIKILINK_PATTERN.findall(markdown_content))
        for target in wikilinks:
            if target := target.strip():
                edges.append((
                    source_node_id, 
                    target, 
                    {"weight": 1.0, "edge_type": "explicit", "relation": "wikilink"}
                ))
                
        # 2. 태그 추출
        tags = set(self.TAG_PATTERN.findall(markdown_content))
        for tag in tags:
            if tag := tag.strip():
                # 태그 노드 식별을 위해 '#' 접두사 유지
                edges.append((
                    source_node_id, 
                    f"#{tag}", 
                    {"weight": 1.0, "edge_type": "explicit", "relation": "tag"}
                ))
                
        return edges

    async def extract_implicit_edges(self, source_node_id: str, content: str, llm_client: Any) -> List[Tuple[str, str, Dict[str, Any]]]:
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

        # LLM 프롬프트 구성 (System / User Message 형태로 확장을 고려)
        prompt_text = (
            "Analyze the following text and extract up to 3 core related keywords or entities. "
            "Return ONLY a comma-separated list of keywords, without any extra text.\n\n"
            f"Text: {content}"
        )
        
        try:
            # 의존성으로 주입받은 LLM 클라이언트를 통해 키워드 추출 (비동기 연동)
            # Langchain BaseChatModel의 ainvoke 지원 가정 (프로젝트의 ChatOpenAI 등)
            from langchain_core.messages import HumanMessage
            
            response = await llm_client.ainvoke([HumanMessage(content=prompt_text)])
            response_text = str(response.content).strip()
            
            # 파싱 로직 (쉼표 분리)
            extracted_keywords = [kw.strip() for kw in response_text.split(",") if kw.strip()]
            
            # 암묵적 엣지에는 명시적 엣지보다 낮은 기본 가중치 부여 (예: 0.5)
            # 추후 LLM 응답에 weight까지 포함시키도록 프롬프트 고도화 가능
            edges.extend(
                (
                    source_node_id,
                    keyword,
                    {"weight": 0.5, "edge_type": "implicit", "relation": "semantic_keyword"}
                )
                for keyword in extracted_keywords
            )
                
        except Exception as exc:
            # LLM 연동 실패 시 애플리케이션의 중단을 막기 위해 예외 캡처 및 로깅
            # 프로젝트 컨벤션에 따라 GraphLoadError 등으로 래핑할 수 있음
            import logging
            logging.error(f"[Graph Extraction] Failed to extract implicit edges for node {source_node_id}: {exc}")
            
        return edges
