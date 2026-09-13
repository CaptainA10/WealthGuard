"""Reproducible synthetic dataset generation.

The dataset is 100% synthetic (cahier des charges §8: no real client data), but
the *market prices* are enriched with genuine historical closes pulled from
Yahoo Finance for 18 real tickers. Everything is seeded, so two runs on two
machines produce byte-identical CSVs.
"""
