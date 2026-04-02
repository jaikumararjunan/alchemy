# UML Architecture Diagrams

All diagrams were generated from the QuantInsti codebase analysis and
Alchemy integration design. Each follows C4 model / UML conventions.

| File | Type | Description |
|------|------|-------------|
| `01_system_context.png` | C4 L1 System Context | Alchemy in ecosystem — actors, brokers, LLM providers, QuantInsti libs |
| `02_component_architecture.png` | C4 L2 Component | Five-layer decomposition: Presentation → AI Agent → Strategy → Analytics → Execution |
| `03_sequence_diagram.png` | UML Sequence | End-to-end AI trade lifecycle: news → LiteLLM → GARCH → LangGraph → IB |
| `04_class_diagram.png` | UML Class | Core integration classes: state, router, volatility, portfolio, pipeline, gateways |
| `05_integration_architecture.png` | Integration Matrix | QuantInsti repo → Alchemy module → pattern → API surface → benefit |
| `06_migration_roadmap.png` | Migration | Phased 10-week migration roadmap with deliverables per phase |
| `07_deployment.png` | UML Deployment | AWS cloud: EC2 clusters, TimescaleDB, S3, SQS/SNS |

## Regenerating Diagrams

```bash
python scripts/generate_diagrams.py
```

Requires `matplotlib` and `numpy`.
