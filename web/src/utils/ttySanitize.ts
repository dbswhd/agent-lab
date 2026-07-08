/** Strip PTY/CLI control noise (ANSI cursor toggles, bare CSI) from auth/terminal text. */

/* eslint-disable no-control-regex -- intentional ANSI / control char scrubbing */
const ANSI_OR_CSI = /\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])/g;
/* eslint-enable no-control-regex */

const BARE_BRACKET_SEQ = /\[[0-9;?]*[a-zA-Z]/g;

export function stripTerminalControlSequences(text: string): string {
  return text
    .replace(ANSI_OR_CSI, "")
    .replace(BARE_BRACKET_SEQ, "")
    .replace(/\r/g, "");
}
