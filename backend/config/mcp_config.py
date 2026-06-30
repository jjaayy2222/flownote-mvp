# backend/config/mcp_config.py

"""
MCP (Model Context Protocol) 및 외부 도구 연결 설정 모듈입니다.
MCP (Model Context Protocol) and external tool connection configuration module.

이 모듈은 Obsidian, Notion 등 외부 도구와의 연동을 위한 환경 변수를
Pydantic 모델을 통해 검증하고 로드합니다.
This module validates and loads environment variables for integrating with external tools
like Obsidian and Notion using Pydantic models.
"""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ObsidianConfig(BaseModel):
    """
    Obsidian Vault 연결 및 동기화 설정 모델입니다.
    Obsidian Vault connection and synchronization configuration model.

    환경 변수 `OBSIDIAN_VAULT_PATH`, `OBSIDIAN_SYNC_INTERVAL`, `OBSIDIAN_SYNC_ENABLED`를 통해 구성되며,
    Vault 경로의 유효성을 런타임에 검사하는 프로퍼티를 제공합니다.
    """

    model_config = ConfigDict(extra="ignore")

    vault_path: str = Field(
        default_factory=lambda: os.getenv("OBSIDIAN_VAULT_PATH", "")
    )
    sync_interval: int = Field(
        default_factory=lambda: int(os.getenv("OBSIDIAN_SYNC_INTERVAL", "300"))
    )
    enabled: bool = Field(
        default_factory=lambda: os.getenv("OBSIDIAN_SYNC_ENABLED", "true").lower()
        == "true"
    )

    @property
    def is_valid(self) -> bool:
        """
        현재 설정된 Vault 경로가 유효하고 존재하는지 검사합니다.
        Validates whether the configured Vault path is valid and exists on the filesystem.

        기능이 비활성화(`enabled=False`)된 경우 항상 True를 반환합니다.

        Returns:
            bool: 비활성화 상태이거나(True), 경로가 존재할 경우 True. 그렇지 않으면 False.
        """
        if not self.enabled:
            return True
        return self.vault_path != "" and Path(self.vault_path).exists()


class NotionConfig(BaseModel):
    """
    Notion API 연결 설정 모델입니다 (Phase 5 예정).
    Notion API connection configuration model (Planned for Phase 5).

    환경 변수 `NOTION_API_KEY`, `NOTION_DATABASE_ID`를 통해 구성됩니다.
    현재는 비활성화 상태(`enabled=False`)를 기본값으로 갖습니다.
    """

    model_config = ConfigDict(extra="ignore")

    api_key: str = Field(default_factory=lambda: os.getenv("NOTION_API_KEY", ""))
    database_id: str = Field(
        default_factory=lambda: os.getenv("NOTION_DATABASE_ID", "")
    )
    enabled: bool = Field(default=False)


class MCPConfig(BaseModel):
    """
    모든 외부 도구(MCP) 구성을 통합 관리하는 최상위 설정 모델입니다.
    Top-level configuration model that aggregates all external tool (MCP) settings.

    Obsidian 및 Notion 설정 인스턴스를 포함하며, 전체 초기화 상태를 검증하는 메서드를 제공합니다.
    """

    model_config = ConfigDict(extra="ignore")

    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    notion: NotionConfig = Field(default_factory=NotionConfig)

    def validate_setup(self):
        """
        현재 구성된 MCP(외부 도구) 연결 상태를 표준 출력(STDOUT)으로 로깅합니다.
        Logs the current status of MCP (external tool) configurations to standard output.

        Obsidian의 경우 활성화 여부 및 경로 유효성을 확인하고,
        Notion의 경우 Phase 5 예정 상태임을 표시합니다.
        """
        print("\n🔌 MCP Configuration Status:")
        print("=" * 30)

        # Obsidian
        obs_status = "✅ Ready" if self.obsidian.is_valid else "❌ Invalid Path"
        if not self.obsidian.enabled:
            obs_status = "⚪️ Disabled"
        print(f"  Obsidian: {obs_status}")
        if self.obsidian.enabled and not self.obsidian.is_valid:
            print(f"    - Path: {self.obsidian.vault_path} (Not Found)")

        # Notion
        notion_status = "⚪️ Disabled (Phase 5)"
        print(f"  Notion:   {notion_status}")
        print("=" * 30)


# 전역 설정 인스턴스
mcp_config = MCPConfig()
