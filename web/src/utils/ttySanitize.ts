/** Strip PTY/CLI control noise (ANSI cursor toggles, bare CSI) from auth/terminal text. */
export function stripTerminalControlSequences(text: string): string {
  return text
    .replace(/\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, "")
    .replace(/\[[\?0-9;]*[a-zA-Z]/g, "")
    .replace(/\r/g, "");
}
