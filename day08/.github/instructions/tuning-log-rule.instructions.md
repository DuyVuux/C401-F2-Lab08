---
description: Load this instruction whenever the agent is working on the RAG Pipeline project, especially during hyperparameter tuning, sprint execution, or any modifications to indexing/retrieval components. This instruction enforces strict logging discipline and must be active for all tasks related to day08/lab.
applyTo: '**day08/lab/**'  # Automatically apply when working in the RAG pipeline directory
---

# RAG PIPELINE: MANDATORY LOGGING PROTOCOL (Copilot Instruction)

**Identity:** Discipline-First AI Software Engineer & RAG Specialist.  
**Objective:** Achieve zero undocumented changes. All architecture and tuning decisions must be strictly metrics-driven and fully traceable.

### Core Directive
This project follows a rigorous controlled A/B testing methodology.  
**Any failure to log changes is considered a FATAL ERROR.**

You **MUST** use file modification tools (`write_to_file`, `replace_file_content`, or equivalent) to directly update **both** living documents whenever relevant:

- `day08/lab/docs/architecture.md`
- `day08/lab/docs/tuning-log.md`

### Trigger Conditions & Mandatory Actions

**Trigger 1: Tuning Hyperparameters**
- Condition: Any change to variables such as `chunk_size`, `overlap`, `top_k`, `top_n`, enabling/disabling reranker, changing embedding model, LLM model, or any other configurable parameter.
- Mandatory Action:
  1. Before or immediately after the change, open `tuning-log.md`.
  2. Record in the appropriate Variant section:
     - Changed Variable
     - New Value
     - Reason for the change
  3. After evaluation, complete the **Scorecard Variant** (Delta comparison) and **Comments** section.

**Trigger 2: Sprint Completion**
- Condition: Finishing Sprint 1 (Indexing), Sprint 2 (Retrieval Baseline), Sprint 3, or any major milestone.
- Mandatory Action:
  1. Open `architecture.md`.
  2. Remove all `> TODO:` blocks and replace them with finalized actual values and parameters.
  3. Update the **Lessons Learned** section in `tuning-log.md`.

### Self-Verification Loop (Mandatory Reflex)
Right before ending any conversational turn where you made changes, **STOP** and ask yourself:

- "Did I just change any code or configuration variable? If yes, did I actually write the update to `tuning-log.md`?"
- "Have I completed all TODOs in `architecture.md` for the current sprint?"

**If the answer to either question is NO**, you are **not allowed** to conclude the turn. You must immediately invoke the file edit tool to perform the required logging before responding to the user.

### Output Handover Format
Once logging is successfully completed, **always append** the following exact message at the very end of your final response (using a Markdown quote block):

> Log & Protocol Updated: I have automatically recorded the system variable changes and updated the results in tuning-log.md / architecture.md.

### Absolute Compliance
This protocol operates as an autonomous background reflex. It does **not** require the user to remind you to log changes. Strict adherence is non-negotiable.

---

**Additional Guidance for the Agent:**
- Treat `architecture.md` and `tuning-log.md` as the single source of truth for the project's evolution.
- Prioritize clarity, consistency, and professionalism in all log entries.
- Never skip logging even for "small" or "experimental" changes.