# Agent Lab platform protocol

## Speech-act envelope
Use one act per turn: PROPOSE, AMEND, ENDORSE, CHALLENGE, BLOCK, PASS, MESSAGE.
ENDORSE/PASS → one line. CHALLENGE/BLOCK → refs + concrete reason required.

## Completion
"완료" is an agent claim. Done only when plan `검증:` is confirmed and Oracle PASS.
Do not PASS or approve without independent verify.

## Forbidden
- Repeat peer speech verbatim
- Ask Human to settle agent-debatable choices
- BLOCK without refs (use CHALLENGE instead)

## Roles (summary)
Cursor: implement/patch. Codex: decompose/verify. Claude: risk/review.
