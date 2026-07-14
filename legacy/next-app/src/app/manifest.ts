import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Family App",
    short_name: "Family",
    description: "Gezinsapp voor taken, boodschappen, geld, agenda en Home Assistant.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f7f7f2",
    theme_color: "#256f5b",
    lang: "nl-NL",
    categories: ["productivity", "lifestyle", "utilities"],
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
    shortcuts: [
      {
        name: "Vandaag",
        short_name: "Vandaag",
        description: "Open het dagoverzicht.",
        url: "/vandaag",
        icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
      },
      {
        name: "Snel toevoegen",
        short_name: "Snel",
        description: "Voeg direct een taak, boodschap of bericht toe.",
        url: "/snel",
        icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
      },
      {
        name: "Noodkaart",
        short_name: "Nood",
        description: "Open belangrijke contacten en huisinformatie.",
        url: "/noodkaart",
        icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
      },
    ],
  };
}
