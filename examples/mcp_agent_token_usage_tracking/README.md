# Tracking Token Usage with AugmentedLLMs

This example demonstrates how to monitor token consumption across different LLM providers using the new `response_history` attribute of AugmentedLLMs.

## What you'll learn
- How to access and analyze token usage data
- Compare token efficiency between OpenAI and Anthropic models for identical queries
- Leverage the `response_history` property for advanced analytics

The introduction of the `response_history` attribute in the `AugmentedLLM` class enables not only token tracking but also opens up numerous other analytics possibilities. While this example focuses on token consumption comparison, the same approach can be applied to monitor response times, model behavior patterns, and other performance metrics.