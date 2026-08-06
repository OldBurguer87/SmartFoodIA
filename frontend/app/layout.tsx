import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartFoodIA | Operação",
  description: "Central operacional da Olívia e dos pedidos.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
