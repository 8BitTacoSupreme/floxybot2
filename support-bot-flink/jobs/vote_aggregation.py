"""Flink job: Vote aggregation.

Windows: tumbling 1h + sliding 24h.
Aggregates votes to identify high-quality Q&A pairs for canon promotion.

TODO: Implement with PyFlink.
"""
