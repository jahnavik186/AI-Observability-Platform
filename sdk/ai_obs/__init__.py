"""
ai-obs SDK
==========
One decorator. Any LLM. Full visibility.

Quickstart::

    from ai_obs import observe

    @observe(model="gpt-4o", provider="openai")
    def my_fn(prompt: str) -> str:
        ...

Scoring::

    from ai_obs import score, autoscore
    score(trace_id="abc-123", value=1.0, label="correct")
    autoscore(trace_id="abc-124", question="...", answer="...", reference="...")

Plugin exporters::

    from ai_obs import registry
    from ai_obs.exporters import WebhookExporter
    registry.register(WebhookExporter(url="https://..."))
"""

from ai_obs.decorator import observe
from ai_obs.scoring import score, autoscore
from ai_obs.client import ObsClient, get_client
from ai_obs.registry import ExporterRegistry, registry
from ai_obs.config import config

__all__ = [
    "observe",
    "score",
    "autoscore",
    "ObsClient",
    "get_client",
    "ExporterRegistry",
    "registry",
    "config",
]
__version__ = "0.2.0"
