# System operations

The agent uses domain-scoped retrieval to expose only a small set of relevant tool schemas to the language model. Mandatory tools include the knowledge-base search and system capability search.

Every tool invocation should produce a structured trace with the request, selected tool, arguments, result status, latency, and error details. Secrets and authorization headers must never be written to traces.
