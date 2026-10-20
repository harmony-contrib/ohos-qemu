// Each UI instance addresses its own actual session. A stale window callback
// can never dispatch to a replacement merely because a global current changed.
export class CaptionActions {
  private static closeHandlers: Map<string, () => void> = new Map();
  static register(session: string, close: () => void): void {
    if (CaptionActions.closeHandlers.has(session)) { throw new Error('duplicate real caption session'); }
    CaptionActions.closeHandlers.set(session, close);
  }
  static unregister(session: string): void { CaptionActions.closeHandlers.delete(session); }
  static close(session: string): void {
    const handler = CaptionActions.closeHandlers.get(session);
    if (handler !== undefined) { handler(); }
  }
}
