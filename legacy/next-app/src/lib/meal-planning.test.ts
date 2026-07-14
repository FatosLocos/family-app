import { describe, expect, it } from "vitest";
import { demoData } from "@/lib/demo-data";
import { buildMealPlanningInsight, splitIngredients } from "@/lib/meal-planning";
import type { AppData } from "@/lib/types";

describe("meal planning insight", () => {
  it("detects missing ingredients and weak dinner coverage", () => {
    const data: AppData = {
      ...demoData,
      mealPlans: [
        {
          id: "meal-1",
          household_id: "demo-household",
          planned_date: "2026-07-11",
          meal_type: "avondeten",
          title: "Pasta",
          notes: null,
          ingredients: "Pasta\nTomaten\nKaas",
        },
        {
          id: "meal-2",
          household_id: "demo-household",
          planned_date: "2026-07-12",
          meal_type: "lunch",
          title: "Restjes",
          notes: null,
          ingredients: null,
        },
      ],
      shoppingItems: [
        {
          id: "shop-1",
          list_id: "shopping-list-1",
          household_id: "demo-household",
          name: "Pasta",
          category: "Voorraad",
          quantity: "1 pak",
          checked: false,
        },
      ],
    };

    const insight = buildMealPlanningInsight(data, "2026-07-11");

    expect(insight.weekMeals).toHaveLength(2);
    expect(insight.dinnerCoverage).toBe(1);
    expect(insight.missingIngredients).toEqual(["Tomaten", "Kaas"]);
    expect(insight.mealsWithoutIngredients.map((meal) => meal.id)).toEqual(["meal-2"]);
    expect(insight.nextAction.id).toBe("dinners");
  });

  it("scores a complete weekmenu", () => {
    const data: AppData = {
      ...demoData,
      mealPlans: [
        ...["2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14"].map((date, index) => ({
          id: `dinner-${index}`,
          household_id: "demo-household",
          planned_date: date,
          meal_type: "avondeten" as const,
          title: `Avondeten ${index + 1}`,
          notes: null,
          ingredients: `Ingredient ${index + 1}`,
        })),
        {
          id: "lunch",
          household_id: "demo-household",
          planned_date: "2026-07-12",
          meal_type: "lunch",
          title: "Lunch",
          notes: null,
          ingredients: "Brood",
        },
      ],
      shoppingItems: [
        ...["Ingredient 1", "Ingredient 2", "Ingredient 3", "Ingredient 4", "Brood"].map((name, index) => ({
          id: `shop-${index}`,
          list_id: "shopping-list-1",
          household_id: "demo-household",
          name,
          category: null,
          quantity: null,
          checked: false,
        })),
      ],
    };

    const insight = buildMealPlanningInsight(data, "2026-07-11");

    expect(insight.score).toBe(insight.totalChecks);
    expect(insight.percent).toBe(100);
    expect(insight.missingIngredients).toHaveLength(0);
    expect(insight.nextAction.done).toBe(true);
  });

  it("splits comma and newline separated ingredients", () => {
    expect(splitIngredients("Pasta, Tomaten\nKaas")).toEqual(["Pasta", "Tomaten", "Kaas"]);
  });

  it("handles Date objects from local Postgres", () => {
    const data: AppData = {
      ...demoData,
      mealPlans: [
        {
          id: "meal-date",
          household_id: "demo-household",
          planned_date: new Date("2026-07-11T00:00:00.000Z") as unknown as string,
          meal_type: "avondeten",
          title: "Soep",
          notes: null,
          ingredients: "Tomaat",
        },
      ],
      shoppingItems: [],
    };

    const insight = buildMealPlanningInsight(data, "2026-07-11");

    expect(insight.weekMeals).toHaveLength(1);
    expect(insight.missingIngredients).toEqual(["Tomaat"]);
  });
});
