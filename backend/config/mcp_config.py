# backend/config/mcp_config.py

"""
MCP (Model Context Protocol) 관련 설정
외부 도구 연결 설정을 관리합니다.
"""

import os
from pydantic import BaseModel, Field
from pathlib import Path


class ObsidianConfig(BaseModel):
    """Obsidian 연결 설정"""

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
        """Vault 경로 유효성 검사"""
        if not self.enabled:
            return True
        return self.vault_path != "" and Path(self.vault_path).exists()


class NotionConfig(BaseModel):
    """Notion 연결 설정 (Phase 5 예정)"""

    api_key: str = Field(default_factory=lambda: os.getenv("NOTION_API_KEY", ""))
    database_id: str = Field(
        default_factory=lambda: os.getenv("NOTION_DATABASE_ID", "")
    )
    enabled: bool = Field(default=False)


class MCPConfig(BaseModel):
    """통합 MCP 설정"""

    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    notion: NotionConfig = Field(default_factory=NotionConfig)

    def validate_setup(self):
        """MCP 설정 상태 출력"""
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
