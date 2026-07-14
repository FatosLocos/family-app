import { getLocalUser } from "@/lib/local-auth";
import { getLocalAppData } from "@/lib/local-db";

export async function getUser() {
  return getLocalUser();
}

export async function getAppData(_userId?: string) {
  return getLocalAppData();
}
