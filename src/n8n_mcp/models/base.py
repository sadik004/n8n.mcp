"""
Base model specification for n8n MCP Server.
Configured with extra='ignore' and populate_by_name=True to prevent crashes on unannounced n8n API schema changes.
"""

from pydantic import BaseModel, ConfigDict


class N8nBaseModel(BaseModel):
    """Base model enforcing robust API parsing and field alias tolerance."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        from_attributes=True,
    )
