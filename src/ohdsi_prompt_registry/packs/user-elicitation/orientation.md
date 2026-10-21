# Elicitation versus workflow ownership

Elicitation is a reusable conversation capability. A user can ask it to collect a preference directly, or a research workflow can ask it to resolve a comparator. Neither requires elicitation to know the complete study process.

The caller supplies the goal, context, justified constraints, and answer form. Elicitation asks clearly and returns what the user meant. The caller determines domain suitability and whether to advance. An understood answer can still be inappropriate for a study: `answered` does not mean scientifically valid.

For example, the user chooses Treatment B. Elicitation returns that choice. The research workflow checks the clinical comparison and its remaining required parameters before finalization. Standalone preference collection can simply end.

Prose governs the conversation; schemas govern machine exchanges. Neither alone proves that a dialog was displayed or that a human approved a workflow action. The host owns transport, persistence, and any enforceable transition checks.
