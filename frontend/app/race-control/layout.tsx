import RaceControlShell from "./components/RaceControlShell";

export default function RaceControlLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <RaceControlShell>{children}</RaceControlShell>;
}
