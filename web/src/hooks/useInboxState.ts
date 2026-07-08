import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { fetchInboxSummary, fetchSessionInbox } from "../api/client";

// Two real modes the human cares about: items to act on, and the activity feed.
// (Former kind/discuss sub-filters are now conveyed by per-row badges.)
export type InboxSegment = "inbox" | "activity";

export interface InboxState {
  inboxPendingCount: number;
  inboxPendingQuestions: number;
  inboxPendingBuilds: number;
  inboxPendingSkillDrafts: number;
  globalInboxPending: number;
  setGlobalInboxPending: (n: number) => void;
  inboxReloadKey: number;
  setInboxReloadKey: Dispatch<SetStateAction<number>>;
  inboxSegment: InboxSegment;
  setInboxSegment: Dispatch<SetStateAction<InboxSegment>>;
  showInboxPopup: boolean;
  setShowInboxPopup: Dispatch<SetStateAction<boolean>>;
  refreshInboxPending: () => Promise<void>;
  syncInboxPendingCount: (count: number) => void;
  inboxPendingNonQuestions: number;
  titlebarInboxPending: number | undefined;
}

export function useInboxState(sessionId: string | null): InboxState {
  const [inboxPendingCount, setInboxPendingCount] = useState(0);
  const [inboxPendingQuestions, setInboxPendingQuestions] = useState(0);
  const [inboxPendingBuilds, setInboxPendingBuilds] = useState(0);
  const [inboxPendingSkillDrafts, setInboxPendingSkillDrafts] = useState(0);
  const [globalInboxPending, setGlobalInboxPending] = useState(0);
  const [inboxReloadKey, setInboxReloadKey] = useState(0);
  const [inboxSegment, setInboxSegment] = useState<InboxSegment>("inbox");
  const [showInboxPopup, setShowInboxPopup] = useState(false);

  const refreshInboxPending = useCallback(async () => {
    if (!sessionId) {
      setInboxPendingCount(0);
      setInboxPendingQuestions(0);
      setInboxPendingBuilds(0);
      setInboxPendingSkillDrafts(0);
      return;
    }
    try {
      const payload = await fetchSessionInbox(sessionId);
      setInboxPendingCount(payload.pending_count ?? 0);
      setInboxPendingQuestions(payload.pending_questions ?? 0);
      setInboxPendingBuilds(payload.pending_builds ?? 0);
      setInboxPendingSkillDrafts(payload.pending_skill_drafts ?? 0);
    } catch {
      setInboxPendingCount(0);
      setInboxPendingQuestions(0);
      setInboxPendingBuilds(0);
      setInboxPendingSkillDrafts(0);
    }
  }, [sessionId]);

  const syncInboxPendingCount = useCallback((count: number) => {
    setInboxPendingCount(Math.max(0, count));
  }, []);

  useEffect(() => {
    void refreshInboxPending();
  }, [refreshInboxPending, inboxReloadKey]);

  useEffect(() => {
    let cancelled = false;
    const loadSummary = () => {
      void fetchInboxSummary()
        .then((payload) => {
          if (cancelled) return;
          setGlobalInboxPending(
            Math.max(
              0,
              (payload.total_pending ?? 0) - (payload.pending_questions ?? 0),
            ),
          );
        })
        .catch(() => {
          if (!cancelled) setGlobalInboxPending(0);
        });
    };
    loadSummary();
    const timer = window.setInterval(loadSummary, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [sessionId, inboxReloadKey, inboxPendingCount]);

  const inboxPendingNonQuestions = useMemo(() => {
    const typedCount = inboxPendingBuilds + inboxPendingSkillDrafts;
    return Math.max(0, typedCount || inboxPendingCount - inboxPendingQuestions);
  }, [
    inboxPendingBuilds,
    inboxPendingCount,
    inboxPendingQuestions,
    inboxPendingSkillDrafts,
  ]);

  const titlebarInboxPending = useMemo(() => {
    if (inboxPendingNonQuestions > 0) return inboxPendingNonQuestions;
    return globalInboxPending > 0 ? globalInboxPending : undefined;
  }, [globalInboxPending, inboxPendingNonQuestions]);

  return {
    inboxPendingCount,
    inboxPendingQuestions,
    inboxPendingBuilds,
    inboxPendingSkillDrafts,
    globalInboxPending,
    setGlobalInboxPending,
    inboxReloadKey,
    setInboxReloadKey,
    inboxSegment,
    setInboxSegment,
    showInboxPopup,
    setShowInboxPopup,
    refreshInboxPending,
    syncInboxPendingCount,
    inboxPendingNonQuestions,
    titlebarInboxPending,
  };
}
