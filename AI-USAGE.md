# AI Usage Disclosure

## AI Assistance

This project was developed with substantial assistance from an AI coding agent (Antigravity).

AI assistance was used for:
- **Project Analysis:** Analyzing the provided mock services, data structures, pagination behaviour, and technical requirements.
- **Architecture Support:** Exploring and implementing the asynchronous FastAPI architecture, retry strategy, failure isolation, circuit breaker, and observability mechanisms.
- **Implementation Assistance:** Drafting and modifying portions of the application code, adapters, orchestrator logic, tests, and supporting documentation.
- **Testing & Debugging:** Assisting with test creation, verification workflows, debugging, and investigation of implementation issues.
- **Documentation:** Assisting with README, architecture, decision, analysis, and other project documentation.

All generated or modified code was reviewed, tested, and accepted under human direction.

## Human Oversight & Decision-Making

The human developer remained responsible for the final technical direction, review, scope, and engineering decisions throughout the project.

This included:
- **Architecture & Resilience Strategy:** Defining and reviewing the system architecture, failure-isolation boundaries, retry limits, backoff strategy, and circuit-breaker behaviour required for the Day-2 40% failure scenario.
- **Code Review & Verification:** Reviewing generated code, running the test suite, investigating failures, and verifying that implementation changes preserved the required API behaviour.
- **Engineering Judgement:** Evaluating proposed features against the problem requirements and deciding which features were appropriate to implement.
- **Identity Matching Decision:** Investigating the supplied datasets and explicitly rejecting automated cross-system identity matching because missing DOB values and duplicate names could produce unsafe false positives. This decision was made in accordance with the requirement that false positives are worse than missed matches.
- **Project Scope:** Deciding which resilience and observability improvements provided genuine value and avoiding unnecessary features that could introduce additional risk or change the required API contract.
- **Final Audit:** Reviewing the repository, documentation, tests, requirements, and git state before submission.

The final implementation was locally tested and reviewed against the Brite Spark 2026 Problem 3 requirements.
