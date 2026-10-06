# Narrative Audio Map — deferred production module

This is a future capability, not part of the live MVP and not advertised on the storefront.

The extension should link `NarrativeScene` to an audiobook and chapter, with ordered scene number, environment, characters, action, emotional context and transition notes. `AudioRecommendation` should reference the scene, record ambience, effects, music/cues, intensity, positioning, transitions, narration/background balance and continuity notes, and preserve its generation provenance.

Each recommendation supports **Accept**, **Modify** and **Reject**, with a staff identity and decision timestamp. Accepted or modified recommendations create a separate immutable `ApprovedAudioDecision`; generated recommendations must never silently overwrite approved creative decisions. A modification keeps both the original and the accepted revision. Continuity references should connect scenes across chapters.

Implementation can use a private production Blueprint, the existing role checks and audit log, and a migration for these tables. No model provider, API calls or recommendation generation is configured in this MVP.
