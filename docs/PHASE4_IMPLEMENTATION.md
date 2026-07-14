# Phase 4 Implementation

Phase 4 turns the former research track into four bounded, testable capabilities.

## Acceptance paths

1. Open **Adaptive collaboration**, submit a tool request for a coworker, and
   verify the tool is absent until an Owner/Admin approves the proposal.
2. Add two long-term coworker memories using the same `subject: value` subject,
   choose **Scan**, and resolve the surfaced conflict. Both original rows remain;
   each affected coworker receives a provenance-linked resolution memory.
3. Create an Agent Team with at least two members, start consensus with two or more
   options, and watch the background tasks produce attributed votes. Majority,
   unanimity, and confidence-weighted rules can decide or explicitly deadlock.
4. Open **Live voice**, choose a coworker, allow browser microphone access, and
   speak. Responses are synthesized when supported. Typed fallback remains
   available; tool calls still pause in the standard approval inbox.

## Operational notes

- Live voice needs browser SpeechRecognition and SpeechSynthesis support. It uses
  continuous speech around the existing text model pipeline; provider-native
  audio-to-audio can replace that transport later without changing trust controls.
- Consensus requires working model credentials and workers, exactly like ordinary
  background tasks. Invalid model vote output is retained on its task but does not
  become a fabricated vote.
- Attach the safe `propose_capability` tool to coworkers that should be able to
  raise their own gaps. The tool can only create a pending proposal.

## Verification

`core.tests.test_phase4` covers non-granting proposals, administrator-only review,
conflict detection/resolution, consensus decisions/deadlocks, and the voice/chat
seam. The normal full backend suite, migration drift check, frontend lint, and
production build remain the release gates.
