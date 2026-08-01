# ADR-008: Reactive State Transaction Semantics & Batching Models

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
Applications frequently need to modify multiple reactive state signals within a single user action. If each write immediately triggers dependency recomputation and DOM patch generation, intermediate states can cause visual flickering, redundant rendering computations, and race conditions.

Furthermore, if an error occurs halfway through a multi-variable state update, partial state modifications can leave the application in an invalid state unless transactional rollback is enforced.

## Decision

### 1. Distinction: `ctx.batch()` vs `ctx.transaction()`

| Feature | `ctx.batch()` | `ctx.transaction()` |
| :--- | :--- | :--- |
| **Primary Goal** | Render coalescing & notification deduplication | All-or-nothing atomicity & error rollback |
| **Rollback on Error** | No: writes before the error remain applied | **Yes**: rolls back all writes within block to baseline |
| **Event Emission** | Emits coalesced patches upon exit | Emits patches **only upon successful commit** |
| **Use Case** | Performance optimization for multi-signal updates | Consistency enforcement across interdependent state variables |

### 2. Transaction Atomicity & Rollback Mechanics
```python
with ctx.transaction():
    ctx.write(s_source_balance, ctx.read(s_source_balance) - amount)
    validate_business_rules()  # If this raises, s_source_balance is rolled back
    ctx.write(s_dest_balance, ctx.read(s_dest_balance) + amount)
```
- Upon entering `ctx.transaction()`, the context records snapshot values for any modified state references.
- If an unhandled exception propagates out of the block, the transaction context restores the original snapshot values and discards pending mutation events.
- If the block exits cleanly, modifications are committed to the underlying `StateBackend`, and downstream reactive dependencies (`gx.computed`) are evaluated.

### 3. Read Isolation & "Read-Your-Own-Writes"
- Inside `with ctx.transaction():`, calling `ctx.read(ref)` returns the uncommitted value written earlier within the same transaction block.
- Concurrent requests in other sessions or views continue to read the committed value until the transaction successfully commits.

### 4. Nesting Behavior
- Nested transaction blocks (`with ctx.transaction(): with ctx.transaction(): ...`) behave as a unified atomic transaction.
- An exception in any inner block aborts the entire outermost transaction, rolling back all modifications across all nesting levels.

## Consequences
- **Positive:** Guarantees state consistency: applications never persist half-applied state updates.
- **Positive:** High rendering performance: patch emissions are coalesced into a single atomic browser update.
- **Boundaries:** Local state transactions are bounded to RADUI memory and backend state; distributed external calls must use the Transactional Outbox (ADR-002).
