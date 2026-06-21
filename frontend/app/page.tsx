import { redirect } from "next/navigation";

// Demo opens on Coinbase (rises on the SEC suit → falls on the dismissal).
export default function Home() {
  redirect("/customers/coinbase-global");
}
