backend/
├── __init__.py
├── api
│   ├── __init__.py
│   ├── endpoints
│   │   ├── __init__.py
│   │   ├── classify.py
│   │   ├── conflict_resolver.py
│   │   ├── conflict_resolver_agent.py
│   │   ├── dashboard.py
│   │   ├── metadata.py
│   │   └── search.py
│   ├── models
│   │   ├── __init__.py
│   │   └── conflict_models.py
│   ├── models.py
│   └── routes.py
├── chunking.py
├── classifier
│   ├── __init__.py
│   ├── conflict_resolver.py
│   ├── context_injector.py
│   ├── data
│   │   └── user_context_mapping.json
│   ├── keyword_classifier.py
│   ├── langchain_integration.py
│   ├── metadata_classifier.py
│   ├── para_agent.py
│   ├── para_agent_wrapper.py
│   ├── para_classifier.py
│   ├── prompts
│   │   ├── backup_20251107
│   │   │   ├── conflict_resolution_prompt.txt
│   │   │   ├── keyword_classification_prompt.txt
│   │   │   ├── metadata_classification_prompt.txt
│   │   │   └── para_classification_prompt.txt
│   │   ├── bacoup_20251107_2
│   │   │   ├── conflict_resolution_prompt.txt
│   │   │   ├── keyword_classification_prompt.txt
│   │   │   ├── metadata_classification_prompt.txt
│   │   │   ├── onboarding_suggest_areas.txt
│   │   │   └── para_classification_prompt.txt
│   │   ├── conflict_resolution_prompt.txt
│   │   ├── keyword_classification_prompt.txt
│   │   ├── metadata_classification_prompt.txt
│   │   ├── onboarding_suggest_areas.txt
│   │   └── para_classification_prompt.txt
│   └── snapshot_manager.py
├── config.py
├── dashboard
│   ├── __init__.py
│   └── dashboard_core.py
├── data
├── data_manager.py
├── database
│   ├── __init__.py
│   ├── connection.py
│   └── metadata_schema.py
├── embedding.py
├── exceptions.py
├── export.py
├── faiss_search.py
├── main.py
├── metadata.py
├── modules
│   ├── __init__.py
│   ├── pdf_helper.py
│   └── vision_helper.py
├── routes
│   ├── __init__.py
│   ├── api_models.py
│   ├── api_routes.py
│   ├── classifier_routes.py
│   ├── conflict_routes.py
│   └── onboarding_routes.py
├── search_history.py
├── services
│   ├── __init__.py
│   ├── conflict_service.py
│   ├── gpt_helper.py
│   └── parallel_processor.py
├── utils.py
└── validators.py

15 directories, 68 files
