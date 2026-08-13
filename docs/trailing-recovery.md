# Trailing recovery

The signal trailing plan freezes profile parameters and targets. Action keys remain deterministic per signal/stage/action.

For the ladder profile:

- TP1 Partial: `NX-ID:TRAIL:1:PARTIAL`
- TP1 SL to BE: `NX-ID:TRAIL:1:SL`
- TP2 SL to TP1: `NX-ID:TRAIL:2:SL`
- Later stages continue the same pattern.

Before a partial close, NEXUS records `EXECUTING` with position ID, pre-volume, and existing exit tickets. After MT5 success it records `CONFIRMED`. Following interruption, it reads `history_deals_get(position=POSITION_ID)` and confirms a newly observed exit without submitting another close. An unresolved outcome becomes `UNKNOWN` and stops automatic replay.

SL actions are reconciled against the current position SL. Stop and freeze distances are both considered. A confirmed action is never moved backward or repeated.

Target recovery examines persisted stages/actions, current position state, position deal history, and M1 rates since the plan was armed. It is no longer limited to the current tick/current candle.

These safeguards are covered with fake-MT5 tests. Broker retcodes, filling modes, stop/freeze behavior, and restart timing still require controlled demo-account validation.
