import { describe, expect, it } from "vitest";
import { serviceForEntity } from "@/lib/home-assistant";

describe("serviceForEntity", () => {
  it.each([
    ["light.keuken", { domain: "light", service: "toggle" }],
    ["switch.koffiezetapparaat", { domain: "switch", service: "toggle" }],
    ["scene.avond", { domain: "scene", service: "turn_on" }],
    ["script.vertrekken", { domain: "script", service: "turn_on" }],
    ["cover.gordijnen", { domain: "cover", service: "toggle" }],
    ["climate.woonkamer", { domain: "climate", service: "toggle" }],
    ["media_player.tv", { domain: "media_player", service: "media_play_pause" }],
  ])("maps %s to the expected Home Assistant service", (entityId, expected) => {
    expect(serviceForEntity(entityId)).toEqual(expected);
  });

  it("keeps unsupported domains read-only", () => {
    expect(serviceForEntity("sensor.temperatuur")).toBeNull();
    expect(serviceForEntity("binary_sensor.deur")).toBeNull();
  });
});
