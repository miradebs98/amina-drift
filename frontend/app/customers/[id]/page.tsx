import { notFound } from "next/navigation";
import { getCase } from "@/lib/api";
import { ProfileView } from "@/components/profile/profile-view";

export default async function CustomerProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await getCase(id);
  if (!data) notFound();
  return <ProfileView data={data} />;
}
