import { describe, expect, it } from "vitest";
import { mapHueLight } from "@/lib/hue";

describe("mapHueLight", () => {
  it("maps Hue CLIP v2 light resources", () => {
    expect(
      mapHueLight({
        id: "light-id",
        metadata: { name: "Keuken" },
        on: { on: true },
        dimming: { brightness: 74.6 },
        owner: { rid: "room-id" },
      }),
    ).toEqual({
      id: "light-id",
      rid: "light-id",
      name: "Keuken",
      on: true,
      brightness: 75,
      room: "room-id",
    });
  });

  it("uses safe fallbacks for partial resources", () => {
    expect(mapHueLight({ id: "x" })).toEqual({
      id: "x",
      rid: "x",
      name: "x",
      on: false,
      brightness: null,
      room: null,
    });
  });
});
