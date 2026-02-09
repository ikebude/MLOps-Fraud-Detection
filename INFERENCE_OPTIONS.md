# Inference Backlog Options

You noticed the inference service processing records faster than they are created. This is because it is catching up on a **backlog** of older transactions.

## Options:

1.  **Process Everything (Recommended):**
    *   Let it run. It will eventually catch up and sync with the producer.
    *   **Pros:** Data consistency, full history scored.
    *   **Cons:** Updates for *new* transactions might be slightly delayed until backlog clears (though it prioritizes new ones).

2.  **Ignore Old Records:**
    *   Modify `src/inference/main.py` query to: `WHERE timestamp > NOW() - INTERVAL '1 hour'`.
    *   **Pros:** Immediate real-time behavior for *future* data.
    *   **Cons:** Thousands of historical transactions remain unscored.

3.  **Clear Database:**
    *   Delete all transactions to start fresh.
    *   **Pros:** Instant clean slate.
    *   **Cons:** Loss of data.

## Recommendation
Stick with **Option 1**. The "fast" processing is a feature (recovery), not a bug.

## Action Required
To fix the **FraudGuard Dashboard Crash**, please run:

```bash
docker-compose build fraudguard
docker-compose up -d fraudguard
```
