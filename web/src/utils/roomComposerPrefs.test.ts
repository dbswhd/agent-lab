import { describe, expect, it } from "vitest";
import {
  composerRoutingHintLine,
  detectPlanExecuteIntent,
  IMPLICIT_ROOM_PRESET,
  resolveComposerModeVariant,
  TOPIC_ONLY_COMPOSER,
} from "./roomComposerPrefs";
import { turnProfileForRoomPreset } from "./turnProfile";

const EXECUTE_TOPIC =
  "docs 오타 1건 수정 plan action을 만들어 dry-run 승인 merge Oracle PASS까지";

describe("roomComposerPrefs", () => {
  it("maps fast/supervisor presets to turn profiles", () => {
    expect(turnProfileForRoomPreset("fast")).toBe("quick");
    expect(turnProfileForRoomPreset("supervisor")).toBe("loop");
    expect(turnProfileForRoomPreset("other")).toBe("loop");
    expect(turnProfileForRoomPreset(null)).toBe("loop");
  });

  it("uses implicit supervisor preset in topic-only composer (P2)", () => {
    expect(TOPIC_ONLY_COMPOSER).toBe(true);
    expect(IMPLICIT_ROOM_PRESET).toBe("supervisor");
    expect(turnProfileForRoomPreset(IMPLICIT_ROOM_PRESET)).toBe("loop");
  });

  it("detects plan execute intent topics", () => {
    expect(detectPlanExecuteIntent(EXECUTE_TOPIC)).toBe(true);
    expect(
      detectPlanExecuteIntent(
        "room.py에서 consensus 라운드 cap 기본값이 뭐야?",
      ),
    ).toBe(false);
  });

  it("resolves composer mode variant from session and draft", () => {
    expect(
      resolveComposerModeVariant({
        consensusMode: false,
        topic: EXECUTE_TOPIC,
      }),
    ).toBe("plan");
    expect(
      resolveComposerModeVariant({
        consensusMode: false,
        topic: "GO",
        sessionTopic: EXECUTE_TOPIC,
      }),
    ).toBe("plan");
    expect(
      resolveComposerModeVariant({
        consensusMode: false,
        topic: "casual question",
        discussLight: true,
      }),
    ).toBe("discuss");
    expect(
      resolveComposerModeVariant({
        consensusMode: true,
        topic: EXECUTE_TOPIC,
      }),
    ).toBe("consensus");
  });

  it("shows routing hint for execute intent draft", () => {
    const hint = composerRoutingHintLine({
      draftTopic: EXECUTE_TOPIC,
      locale: "ko",
    });
    expect(hint).toContain("코드 변경과 검증 요청이 감지되어");
  });

  it("shows light discuss hint from run meta", () => {
    const hint = composerRoutingHintLine({
      run: { discuss_light: true },
      locale: "ko",
    });
    expect(hint).toContain("낮은 위험의 간단한 요청이라");
  });
});
