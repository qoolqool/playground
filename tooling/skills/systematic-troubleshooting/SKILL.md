---
name: systematic-troubleshooting
description: >
  Break out of circular debugging by recognizing when contradictory evidence means
  the approach is wrong, not the data. Replace fragile workarounds with clean,
  direct solutions.
---

# Systematic Troubleshooting (Break the Loop)

## When to Use

- You've been going in circles with contradictory evidence
- A workaround keeps failing in new and interesting ways
- You're getting results that "can't both be true" (e.g., CouchDB says deleted but peer query returns old value)
- The user suggests a simpler approach you dismissed
- You've made 3+ attempts at the same class of fix without success

## The Pattern

### 1. Recognize the Loop

**Signals you're in a loop:**
- You keep re-running the same commands hoping for different results
- You're explaining away contradictions instead of resolving them
- You're adding more complexity to a workaround that was supposed to be "simple"
- The user calls you out on it

**When you detect a loop, STOP. Do not make another attempt.**

### 2. State the Contradiction Clearly

Write down exactly what contradicts:

```
Tool A says:  X
Tool B says:  not X
These cannot both be true unless [unlikely explanation].
```

Example from the CouchDB reset bug:
```
peer chaincode query BalanceOf reserve-pool → 5,200,000
CouchDB GET /BAL~did:example:reserve-pool → 404 "deleted"
Peer config says CORE_LEDGER_STATE_COUCHDBCONFIG_COUCHDBADDRESS=localhost:5984
```

### 3. Ask: "Is the Approach Wrong, Not the Data?"

When evidence contradicts, the most likely explanation is **your mental model is wrong**, not the tools. Common causes:

| Symptom | Likely Root Cause |
|---------|-------------------|
| CouchDB says deleted, peer says old value | Direct CouchDB manipulation creates tombstones; peer reads from different source or has cache |
| Invoke fails with TLS/cert error after CouchDB purge | State divergence between peers causes endorsement failures |
| Workaround works once then breaks | The workaround creates hidden state that breaks the next operation |

### 4. Listen to the User's Suggestion

When the user says "why not just reinitialise the DB?" — **try it immediately**. Do not explain why it won't work. Do not list reasons to keep debugging the broken approach. The user has context you don't.

**Rule:** If the user suggests a simpler approach, try it before making another attempt at the current approach.

### 5. Replace, Don't Patch

When a workaround is fundamentally broken:
- **Don't** add more error handling, retries, or edge cases
- **Don't** try to "fix" the workaround
- **Do** replace the entire approach with something clean

Example:
```
❌ Bad: "Let me add more error handling to the CouchDB key deletion"
❌ Bad: "Let me try deleting keys one at a time instead of in bulk"
✅ Good: "Drop the entire CouchDB database and restart peers"
```

### 6. Verify All Sources Are Consistent

After applying the fix, verify that ALL data sources agree:

```bash
# Check all CouchDB instances
for db in couchdb0 couchdb1 couchdb2; do
  docker exec "$db" curl -s http://admin:adminpw@localhost:5984/stablechannel_stablecoin/_all_docs
done

# Check peer query
peer chaincode query -C stablechannel -n stablecoin -c '{"Args":["BalanceOf","did:example:reserve-pool"]}'

# Check service API
curl http://service/api/v1/token/balance/did:example:reserve-pool
```

If any source disagrees, the fix is incomplete.

### 7. Run the Full Test Suite

A single passing test is not enough. Run the full E2E suite to catch regressions:

```bash
pytest scripts/e2e/live/wired_01_happy_flow.py -v -s
```

## Pitfalls

- **Explaining away contradictions** — "Maybe the peer has a cache" without evidence is a sign you're in denial. Prove it or drop it.
- **Adding complexity to a broken approach** — If a workaround needs more workarounds, the original approach is wrong.
- **Ignoring the user's suggestion** — The user has context you don't. Try their suggestion first.
- **Only checking one data source** — If you only check the peer query, you miss the CouchDB tombstones. Check ALL sources.
- **Not restarting after CouchDB changes** — Dropping a CouchDB database requires peer restart to take effect.

## Verification

- [ ] All data sources agree (CouchDB, peer query, service API)
- [ ] All CouchDB instances have identical state
- [ ] Full E2E test suite passes
- [ ] The fix is simpler than the workaround it replaced
- [ ] You can explain why the old approach was wrong
