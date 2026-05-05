---
name: engineering-methodology
description: Systematic approach to wiring, debugging, and hardening distributed systems. Audit-first, classify-then-plan, incremental-build, root-cause-fix, document-as-you-go. Use when tackling multi-component integration, test suite gaps, or operational readiness work.
---

# Engineering Methodology Skill

A battle-tested approach for wiring distributed systems, closing test-coverage gaps, and shipping reliable integrations. Born from wiring a 4-microservice payment platform with 17 Docker containers from 45% cross-component test coverage to full lifecycle coverage.

## When to Use This Skill

- Wiring inter-service flows in a multi-component system
- Auditing a test suite to find mock-vs-real coverage gaps
- Debugging state machine transitions or protocol mismatches
- Bringing a system from "documented but not running" to "running and verified"
- Assessing operational readiness for production

## Core Principle: Audit Before You Code

Never start implementing until you can answer three questions:
1. **What exists?** — Read the running code, not the documentation.
2. **What's tested?** — Trace each test to the actual HTTP calls it makes, not the feature it claims to test.
3. **What's the gap?** — Classify every flow as WIRED, STUB, MISSING, or BLOCKED.

### The Audit Matrix

For each integration point, classify its status:

| Status | Meaning | Action |
|--------|---------|--------|
| **WIRED** | Code exists, tests pass end-to-end | Verify, move on |
| **STUB** | Code skeleton exists but returns hardcoded values | Replace stub with real call |
| **MISSING** | No code exists at all | Implement from scratch |
| **BLOCKED** | External dependency not available (vendor, provider) | Document gap, add manual workaround, track as risk |

**Example:** In Project Nexus, the Payment Service had 6 REST clients documented but 0 implemented. The test suite had 75 passing tests, but 55% called simulators directly — the Payment Service never called any downstream service.

### The Test Coverage Audit

For each test in your suite, ask:

```
Does this test call Service A → Service B → Service C?
  YES → Cross-component test (real coverage)
  NO  → Isolated/direct test (validates simulator, not integration)
```

Track the ratio. If more than 50% of tests bypass the orchestration layer, the integration is not validated regardless of the pass rate.

## Methodology: The 7-Step Integration Cycle

### Step 1: Map the Target Flow

Before writing any code, produce a flow-by-flow table:

| Flow | Target (Documented) | Actual (Running) | Gap |
|------|---------------------|-------------------|-----|
| Proxy Resolution | Async JMS acmt.023/024 | Sync REST via PdoResolutionClient | Acmt023MessageListener has TODO body |
| FX Reservation | Payment calls FX Service | **WIRED** — FxClient | Sync only |
| ... | ... | ... | ... |

This table becomes your implementation plan. Each row is a task. The "Gap" column tells you exactly what to build.

### Step 2: Create Clients Following Existing Patterns

Find the pattern that already works and replicate it. Don't invent a new style.

**Pattern (from PdoResolutionClient):**
```java
@Service
@Slf4j
public class SomeClient {
    private final RestTemplate restTemplate;
    private final String serviceUrl;

    public SomeClient(@Value("${nexus.some.url:http://localhost:8080}") String serviceUrl) {
        this.serviceUrl = serviceUrl;
        this.restTemplate = new RestTemplate();
    }

    public Result call(String param) {
        String url = serviceUrl + "/api/v1/endpoint?param=" + param;
        try {
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            // parse and return
        } catch (RestClientException e) {
            log.error("Call failed: {}", e.getMessage());
            return new Result(null, e.getMessage());
        }
    }

    public record Result(String data, String error) {}
}
```

**Why this pattern works:**
- `@Value` with default means the service works locally without Docker
- `RestTemplate` is already on the classpath (Spring Web)
- Record types for results — immutable, no Lombok needed
- Error as a field, not an exception — lets the caller decide what to do

### Step 3: Wire the Orchestration

The orchestration service should drive the full lifecycle. Each step gets its own method:

```java
@Transactional
public Payment initiatePayment(String uetr, String pacs008Xml, String sourcePspId) {
    Payment payment = createAndValidate(uetr, pacs008Xml, sourcePspId);
    payment = reserveFxQuote(payment);    // Step 2
    if (payment.getCurrentState() == FAILED) return payment;
    payment = executeLeg1(payment);       // Step 3
    if (payment.getCurrentState() == FAILED) return payment;
    payment = executeSanctionsCheck(payment); // Step 4
    if (payment.getCurrentState() == FAILED) return payment;
    payment = executeLeg2(payment);       // Step 5
    return payment;
}
```

**Key rules:**
- Each step is a separate `@Transactional` method so later failures don't roll back earlier confirmed steps
- Check state after each step — don't assume success
- On failure, call `failPayment()` which fires the correct state machine event or sets state directly

### Step 4: Handle the State Machine

State machines are unforgiving. Invalid transitions throw exceptions. When wiring new paths:

1. **List every transition you need** before writing code
2. **Add missing transitions** to the state machine definition
3. **Create a `failPayment()` helper** that handles multiple failure entry points

```java
private Payment failPayment(Payment payment) {
    payment.setFailedAt(Instant.now());
    if (stateMachine.canTransition(payment.getCurrentState(), PaymentEvent.VALIDATION_FAILURE)) {
        stateMachine.fireEvent(payment, PaymentEvent.VALIDATION_FAILURE);
    } else {
        // Direct state set for states without a specific failure event
        payment.setCurrentState(PaymentState.FAILED);
    }
    return paymentRepository.save(payment);
}
```

The `canTransition` check prevents `IllegalStateException` from invalid transitions.

### Step 5: Test Incrementally — One Flow at a Time

After wiring each client:
1. Rebuild the Docker image: `mvn package -DskipTests && docker-compose build`
2. Restart: `docker-compose -f docker-compose.nexus.yml up -d`
3. Run the relevant E2E scenario: `./scripts/e2e-scenario-1-happy-path.sh`
4. Verify the state transition chain in the test output

**Do not wire all clients then test.** Wire one, test it, fix what breaks, then wire the next.

### Step 6: Fix Root Causes, Not Symptoms

When a test fails:

| Symptom | Likely Root Cause | Wrong Fix | Right Fix |
|---------|------------------|-----------|-----------|
| `Invalid state transition: VALIDATED_OK -> FX_QUOTE_EXPIRED` | State machine missing transition from VALIDATED_OK to FAILED for FX failures | Catch and swallow the exception | Add `VALIDATED_OK + VALIDATION_FAILURE → FAILED` transition + `failPayment()` helper |
| FX lockQuote returns 404 | Client uses `quoteId` field but FX service uses `optionId` in the path | Add fallback URL | Extract `optionId` from rate options response, use it in lock path |
| UETR duplicate error in E2E | Previous test run left data in payment table | Use different UETR each run | Truncate payment tables before E2E runs |
| Docker build uses cached JAR | Build context hasn't changed so Docker caches the old layer | `docker-compose build --no-cache` | Run `mvn package -DskipTests` before `docker-compose build` |

**The pattern:** Every error message is a signal. Read it carefully. If the fix is "ignore this error," you're fixing the symptom.

### Step 7: Document as You Go

After each wired flow, update:

1. **The audit matrix** — change status from STUB to WIRED
2. **Memory** — update architecture-reality.md with what changed
3. **Risk register** — if a flow can't be wired, add a risk entry (SR-1, SR-2, etc.)
4. **Gotchas list** — add any non-obvious behavior you discovered

## The Scope Boundary

Every integration project has things you CAN wire and things you CAN'T. Be explicit about what's out of scope and why:

| Item | Why Out of Scope |
|------|-----------------|
| Gateway-messaging MDBs | Service not deployed as container |
| JMS async flows | Sync REST works; async is target architecture |
| Cross-border ActiveMQ bridge | Requires broker config; REST proxy sufficient |
| pacs.002 XML generation | Complex XML templating; state tracking covers behavior |
| Sanctions screening | No real provider; auto-pass is correct for reference impl |

Documenting scope boundaries prevents scope creep and sets expectations for what "done" looks like.

## Operational Readiness Assessment

After wiring is complete, assess operational maturity:

### Monitoring Gaps Checklist

- [ ] Prometheus metrics (`/actuator/prometheus` returns 200)
- [ ] Docker healthchecks (every container has one)
- [ ] Structured logging (MDC correlation IDs, JSON format)
- [ ] Alerting rules (Alertmanager or equivalent)
- [ ] Distributed tracing (OpenTelemetry or equivalent)
- [ ] Readiness vs liveness probes separated

### Settlement Risk Register

For financial/payment systems, create a risk register:

| ID | Risk | Current Mitigation | Required Mitigation |
|----|------|-------------------|---------------------|
| SR-1 | Leg 1 confirmed, Leg 2 fails — funds held | WIRED — auto-compensation | Verify Leg 2 reversal for non-time-critical |
| SR-2 | Payment stuck in pending state | Timer-based timeout | Alert on timeout breach |
| SR-3 | SLA breach not enforced | Config exists, no policing | Add scheduled check + alert |

### Headcount Impact

```
Current FTEs (manual reconciliation)  = 21-24
Target FTEs (integrations wired)      = 14-16
Delta (cost of not wiring)            = +8 FTEs
```

Unwired integrations have a quantifiable headcount cost. This is the business case for finishing the wiring.

## Common Failure Patterns

### 1. "The tests pass but the integration doesn't work"

Tests call simulators directly, bypassing the orchestration service. The service is never exercised.

**Fix:** Make the test submit through the orchestration endpoint and verify the end state, not just the simulator response.

### 2. "Docker build succeeds but changes don't appear"

Docker caches the JAR layer if the build context hasn't changed.

**Fix:** `mvn package -DskipTests` before `docker-compose build`. Or add `--no-cache` to docker build.

### 3. "State machine throws IllegalStateException"

You're firing an event from a state that doesn't have that transition defined.

**Fix:** Add the transition to the state machine definition, or use a `canTransition()` check before firing.

### 4. "FX/SAP client returns unexpected fields"

API contracts between your service and simulators may use different field names (e.g., `optionId` vs `quoteId`, `quoteReference` vs `quoteId`).

**Fix:** Read the simulator source code to see what it actually returns. Don't assume the field names from documentation.

### 5. "Cross-border calls fail with connection refused"

The calling service can't reach the destination service because they're on different Docker networks.

**Fix:** Add both services to a shared network (e.g., `wan-network`) with static IPs.

## Quick Reference: Docker Networking for Cross-Border

```
# In docker-compose.nexus.yml, add services to shared network:
sap-sgp:
  networks:
    wan-network:
      ipv4_address: 172.22.1.41

sap-mys:
  networks:
    wan-network:
      ipv4_address: 172.22.1.42

# Payment services need env vars pointing at cross-border targets:
payment-service-sgp:
  environment:
    NEXUS_DESTINATION_SAP_URL: http://sap-mys:8080
    NEXUS_FX_URL: http://fx.sgp.nexus.local:8080
```

## Quick Reference: Maven + Docker Rebuild

```bash
# After code changes, always:
cd /project/services/payment-service
mvn package -DskipTests

# Then rebuild Docker image:
cd /project
docker-compose -f docker-compose.nexus.yml build payment-service-sgp payment-service-mys

# Then restart:
docker-compose -f docker-compose.nexus.yml up -d

# Then verify:
docker-compose -f docker-compose.nexus.yml logs payment-service-sgp --tail=50
```

## Quick Reference: State Machine Debugging

```bash
# Check payment state transitions:
curl -s http://localhost:9090/api/v1/payments/{uetr} | jq '.currentState'

# Check service health:
curl -s http://localhost:9090/actuator/health | jq '.status'

# Check specific service connectivity:
docker-compose -f docker-compose.nexus.yml exec payment-service-sgp \
  curl -s http://sap-sgp:8080/api/v1/balance/FXP-001
```