# AI Usage Disclosure

## AI Assistance
This project was developed with the assistance of an AI agent (Antigravity). The AI helped in the following ways:
- **Project Analysis:** Analyzed the provided mock services, identifying data structures, pagination behavior, and exact requirements.
- **Architecture Planning:** Designed the asynchronous FastAPI architecture, including the retry policy and failure isolation mechanisms.
- **Implementation:** Drafted the application skeleton, adapter code for HTTP parsing, and orchestrator logic.
- **Testing:** Assisted in writing test cases.

## Human Oversight
- All architectural decisions and resilience boundaries (3 attempts max, linear backoff) were guided by the problem's strict constraint of handling a 40% failure rate without modification.
- Code was reviewed and executed locally to verify compliance with the hackathon rules.
