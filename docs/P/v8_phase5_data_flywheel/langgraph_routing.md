# LangGraph Fallback Routing Architecture (v8.0 Phase 5)

## Overview
This document outlines the conversational flow and intelligent fallback routing mechanism implemented in `backend/agent/chat/graph.py` and `backend/agent/chat/nodes.py`. 

To prevent repetitive LLM hallucinations and continuous negative feedback, the LangGraph orchestration utilizes a threshold-based fallback mechanism. If a user leaves a `thumbs down ("down")` rating twice within the last 3 turns, the RAG pipeline dynamically falls back to an external web search (Tavily).

## Architecture Diagram

```mermaid
graph TD
    %% Node Styling
    classDef startNode fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef endNode fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef router fill:#ffe0b2,stroke:#f57c00,stroke-width:2px;
    classDef ragNode fill:#bbdefb,stroke:#1976d2,stroke-width:2px;
    classDef fallbackNode fill:#ffcdd2,stroke:#d32f2f,stroke-width:2px,stroke-dasharray: 5 5;
    classDef responderNode fill:#c8e6c9,stroke:#388e3c,stroke-width:2px;

    %% Nodes
    START((START)):::startNode
    ROUTER{router_edge}:::router
    RAG[standard_rag_node<br>FAISS Internal Search]:::ragNode
    FALLBACK[fallback_search_node<br>Tavily Web Search]:::fallbackNode
    RESPONDER[responder_node]:::responderNode
    END((END)):::endNode

    %% Edges
    START -->|initial_state + feedback_history| ROUTER

    %% Route Conditions
    ROUTER -->|is_simple_greeting| RESPONDER
    ROUTER -->|should_fallback == standard_rag| RAG
    ROUTER -->|should_fallback == fallback_search| FALLBACK

    %% Next Steps
    RAG -->|PlannerResult| RESPONDER
    FALLBACK -->|PlannerResult| RESPONDER

    RESPONDER --> END
```

## Route Definitions
- **responder**: For simple greetings, bypassing any search overhead.
- **standard_rag**: Standard routing path utilizing internal FAISS document embedding retrieval.
- **fallback_search**: Triggered upon unfulfilled queries tracking `negative_count >= FALLBACK_THRESHOLD` out of the temporal window. Employs Tavily API for Deep Web Research, isolating its context from RAG leftovers to avoid hallucination contamination.
