# integration_tests/README.md
# Integration Tests for MaestroCat

This directory contains integration tests to evaluate the performance and latency of the MaestroCat voice agent pipeline.

## Test Files

1. `latency_test.py` - Measures the latency of individual components and the overall pipeline
2. `stress_test.py` - Evaluates system performance under concurrent load

## Running the Tests

Before running the tests, ensure all required services are running:

```bash
# Start the services
docker-compose up -d

# Verify services are running
docker-compose ps
```

Then run the tests:

```bash
# Run latency tests
python -m integration_tests.latency_test

# Run stress tests
python -m integration_tests.stress_test
```

## Test Configuration

Tests use the same configuration as the main application (`config/maestrocat.yaml`).

## Interpreting Results

The tests will output detailed timing information including:
- Average response time
- Minimum and maximum response times
- Standard deviation
- Component-level metrics (STT, LLM, TTS latencies)
- Throughput metrics for stress tests

For optimal performance, target latencies should be:
- STT latency: < 200ms
- LLM first token: < 300ms
- TTS first audio: < 150ms
- Total latency: < 500ms typical