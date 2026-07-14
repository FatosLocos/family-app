import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function MealsPage() {
  redirect("/boodschappen?tab=maaltijden");
}
