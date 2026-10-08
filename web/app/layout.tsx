import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";

// Archivo is variable in weight and width: the display type uses font-stretch 110–125%,
// so the width axis ("wdth") has to be loaded too
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  axes: ["wdth"],
});

export const metadata: Metadata = {
  title: "OpenArt",
  description: "Find open calls for artists, check your eligibility and prepare your application.",
};

// The header lives in app/(site)/layout.tsx: the login and sign-up pages
// (app/(auth)/) are full-screen and carry their own wordmark
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={archivo.variable}>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
