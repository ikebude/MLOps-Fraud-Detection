# Archive — superseded planning docs

The four documents in this folder (`EXECUTIVE_SUMMARY.md`, `IMPLEMENTATION_ROADMAP.md`,
`IMPLEMENTATION_CHECKLIST.md`, `MONIGUARD_ARCHITECTURAL_AUDIT.md`) describe an earlier
"enterprise upgrade" plan — a 12-week, 2-3-engineer effort adding Feast, Apache Spark/Flink
streaming, and GraphSAGE fraud-ring detection. That plan was never executed and is not the
current direction.

The current, approved spec for Moniguard v2 is `PRODUCT_SPECS.md` section 1 and
`PORTFOLIO_BUILD_PLAN.md` Workstream B (in `ikebude/chidi-who-am-ii`) — a simpler,
single-developer, free-tier-VM-runnable design: XGBoost + Isolation Forest + a lightweight
shared-device/IP graph feature, FastAPI, Airflow with skip-if-not-enough-labels retraining.

These are kept for historical context only. The root `README.md` reflects what's actually
built and measured.
