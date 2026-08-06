# Testbed: Stablecoin POC with Fabric, Besu, and Solana

A full-stack stablecoin proof-of-concept with Fabric chaincode, Besu smart contracts,
Headscale overlay networking, and ISO 8583 payment rail integration.

## Services

### Core Platform
- **postgres** (postgres:16-alpine): Off-chain ledger for transaction history
  - Port: 5432
  - Memory: 512M
  - Healthcheck: pg_isready

- **besu-node** (hyperledger/besu:24.1.0): EVM chain for stablecoin ERC-20 and HTLC
  - Ports: 8545 (RPC), 8546 (WS)
  - Memory: 1G
  - Networks: platform-net
  - Depends on: postgres

- **stablecoin-service** (stablecoin-service:latest): FastAPI backend
  - Build: ./src/service
  - Port: 8000
  - Memory: 1G
  - Networks: platform-net, fabric-x-net
  - Depends on: postgres, besu-node
  - Env: DATABASE_URL, BESU_RPC_URL

- **stablecoin-switch** (stablecoin-switch:latest): Payment switch/routing
  - Build: ./src/switch
  - Port: 8001
  - Memory: 1G
  - Networks: platform-net, fabric-x-net
  - Depends on: postgres, besu-node

### Fabric-X
- **fabric-committer** (fabric-x-committer:latest): Fabric-X committer node
  - Memory: 1G
  - Networks: fabric-x-net
  - Depends on: postgres

- **fabric-endorser** (fabric-x-endorser:latest): Fabric-X endorser node
  - Memory: 1G
  - Networks: fabric-x-net
  - Depends on: postgres

### Overlay Network
- **headscale** (headscale/headscale:latest): Tailscale-compatible control server
  - Port: 8080
  - Memory: 128M
  - Networks: platform-net

### Observability
- **prometheus** (prom/prometheus:latest): Metrics collection
  - Port: 9090
  - Memory: 256M
  - Networks: platform-net

- **grafana** (grafana/grafana:latest): Dashboards
  - Port: 3000
  - Memory: 256M
  - Networks: platform-net
  - Depends on: prometheus

## Test Suites

- **integration**: scripts/e2e/integration/
  - Framework: pytest
  - Markers: not live
  - Required services: postgres, besu-node, stablecoin-service
  - Timeout: 300s

- **live**: scripts/e2e/live/
  - Framework: pytest
  - Markers: live
  - Required services: all
  - Timeout: 600s

## Infrastructure

Networks:
- platform-net: bridge (internal services)
- fabric-x-net: bridge (Fabric-X nodes)
- overlay-net: overlay (Headscale)

## Constraints

- Memory limits on all services (see above)
- Max containers: 20
- Privileged services: headscale

## Guardrails

- require_mem_limit: true
- require_healthcheck: true
- no_host_network: true
- no_privileged: true (except headscale)
