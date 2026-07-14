import { shortDate } from "@/lib/format";
import { dateKey } from "@/lib/date-keys";
import type { AppData, MealPlan } from "@/lib/types";

export type MealPlanningAction = {
  id: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};

export type MealPlanningInsight = {
  upcomingMeals: MealPlan[];
  weekMeals: MealPlan[];
  nextMeal: MealPlan | null;
  dinnerCoverage: number;
  mealTypesCovered: number;
  ingredientCount: number;
  openShopping: number;
  missingIngredients: string[];
  mealsWithoutIngredients: MealPlan[];
  score: number;
  totalChecks: number;
  percent: number;
  actions: MealPlanningAction[];
  nextAction: MealPlanningAction;
};

export function buildMealPlanningInsight(data: AppData, today = new Date().toISOString().slice(0, 10)): MealPlanningInsight {
  const nextWeek = addDays(today, 7);
  const upcomingMeals = data.mealPlans
    .filter((meal) => mealDateKey(meal) >= today)
    .sort((a, b) => mealDateKey(a).localeCompare(mealDateKey(b)));
  const weekMeals = upcomingMeals.filter((meal) => mealDateKey(meal) <= nextWeek);
  const nextMeal = upcomingMeals[0] ?? null;
  const dinnerCoverage = new Set(weekMeals.filter((meal) => meal.meal_type === "avondeten").map((meal) => mealDateKey(meal))).size;
  const mealTypesCovered = new Set(weekMeals.map((meal) => meal.meal_type)).size;
  const ingredientCount = weekMeals.reduce((sum, meal) => sum + splitIngredients(meal.ingredients).length, 0);
  const ingredientsOnList = new Set(data.shoppingItems.filter((item) => !item.checked).map((item) => normalizeIngredient(item.name)));
  const missingIngredients = uniqueIngredients(weekMeals.flatMap((meal) => splitIngredients(meal.ingredients))).filter(
    (ingredient) => !ingredientsOnList.has(normalizeIngredient(ingredient)),
  );
  const mealsWithoutIngredients = weekMeals.filter((meal) => splitIngredients(meal.ingredients).length === 0);
  const openShopping = data.shoppingItems.filter((item) => !item.checked).length;

  const actions: MealPlanningAction[] = [
    {
      id: "baseline",
      title: "Weekmenu gestart",
      detail: weekMeals.length > 0 ? `${weekMeals.length} maaltijd${weekMeals.length === 1 ? "" : "en"} gepland` : "Plan minimaal een maaltijd voor deze week.",
      href: "/boodschappen?tab=maaltijden",
      done: weekMeals.length > 0,
    },
    {
      id: "dinners",
      title: "Avondeten vooruit gepland",
      detail: dinnerCoverage >= 4 ? `${dinnerCoverage}/7 avonden gepland` : `${Math.max(0, 4 - dinnerCoverage)} avondmaaltijd${4 - dinnerCoverage === 1 ? "" : "en"} extra geeft rust`,
      href: "/boodschappen?tab=maaltijden",
      done: dinnerCoverage >= 4,
    },
    {
      id: "ingredients",
      title: "Ingrediënten ingevuld",
      detail: mealsWithoutIngredients.length === 0 ? "Alle weekmaaltijden hebben ingrediënten" : `${mealsWithoutIngredients.length} maaltijd${mealsWithoutIngredients.length === 1 ? "" : "en"} zonder ingrediënten`,
      href: "/boodschappen?tab=maaltijden",
      done: mealsWithoutIngredients.length === 0 && weekMeals.length > 0,
    },
    {
      id: "shopping",
      title: "Boodschappen sluiten aan",
      detail: missingIngredients.length === 0 ? "Alle weekingrediënten staan op de lijst of zijn afgevinkt" : `${missingIngredients.length} ingrediënt${missingIngredients.length === 1 ? "" : "en"} nog niet op de lijst`,
      href: "/boodschappen",
      done: missingIngredients.length === 0,
    },
    {
      id: "variety",
      title: "Variatie in eetmomenten",
      detail: mealTypesCovered >= 2 ? `${mealTypesCovered} eetmomenten gepland` : "Voeg lunch, ontbijt of snack toe als dat helpt.",
      href: "/boodschappen?tab=maaltijden",
      done: mealTypesCovered >= 2,
    },
  ];
  const score = actions.filter((action) => action.done).length;

  return {
    upcomingMeals,
    weekMeals,
    nextMeal,
    dinnerCoverage,
    mealTypesCovered,
    ingredientCount,
    openShopping,
    missingIngredients,
    mealsWithoutIngredients,
    score,
    totalChecks: actions.length,
    percent: Math.round((score / actions.length) * 100),
    actions,
    nextAction: actions.find((action) => !action.done) ?? {
      id: "week",
      title: "Weekmenu is op orde",
      detail: nextMeal ? `${nextMeal.title} staat klaar voor ${shortDate(nextMeal.planned_date)}.` : "Bekijk de weekplanning voor de komende gezinsmomenten.",
      href: "/week",
      done: true,
    },
  };
}

export function splitIngredients(ingredients: string | null) {
  return (ingredients ?? "")
    .split(/\r?\n|,/)
    .map((ingredient) => ingredient.trim())
    .filter(Boolean);
}

export function mealTypeLabel(mealType: string) {
  if (mealType === "ontbijt") return "Ontbijt";
  if (mealType === "lunch") return "Lunch";
  if (mealType === "snack") return "Snack";
  return "Avondeten";
}

function uniqueIngredients(ingredients: string[]) {
  const seen = new Set<string>();
  return ingredients.filter((ingredient) => {
    const key = normalizeIngredient(ingredient);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeIngredient(ingredient: string) {
  return ingredient.trim().toLowerCase();
}

function mealDateKey(meal: MealPlan) {
  return dateKey(meal.planned_date as string | Date) ?? "";
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
