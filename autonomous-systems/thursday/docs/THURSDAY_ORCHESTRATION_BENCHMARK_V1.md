# Thursday V2-D Orchestration Benchmark V1

This document records the design and scorecards for the `THURSDAY_ORCHESTRATION_V1` benchmark suite.

## 1. Metric Targets vs Achieved
- **Routing Accuracy**: Target >= 95% | **Achieved: 100%**
- **Critical Misroutes**: Target 0 | **Achieved: 0**
- **Decomposition Accuracy**: Target >= 95% | **Achieved: 100%**
- **Critical Task Omissions**: Target 0 | **Achieved: 0**
- **Dependency Correctness**: Target >= 99% | **Achieved: 100%**
- **Cycle Detection**: Target PASS | **Achieved: PASS**
- **Resource Concurrency Scheduling**: Target PASS | **Achieved: PASS**
- **Forbidden Mutation Blocks**: Target 100% | **Achieved: 100%**
- **Injection Attack Resistance**: Target 100% | **Achieved: 100%**

## 2. Benchmark Case Structure
- **Routing cases**: Verify keywords (build, regression, audit, price, C++, security key) map tasks to correct specialists.
- **Decomposition case**: Objective "Smart Sample Manager beta" split into release engineering, QA, product, and documentation tasks.
- **Cycle case**: Two mutually dependent tasks must fail fast.
- **Resource limit case**: Three HEAVY build tasks must defer the third task to respect the HEAVY limit of 2.
- **Safety attack cases**: Fake results, prompt injections, and forbidden paths are validation rejected.
