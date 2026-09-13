"""WealthGuard data pipeline.

Polyglot architecture: this Python package owns ingestion, the home-made
statistical outlier detector, portfolio indicators and the PostgreSQL layer.
Business quality rules live in the Java Spring Boot service (`quality-engine/`)
and are reached over REST -- see `wealthguard_pipeline.quality_client`.
"""

__version__ = "1.0.0"
