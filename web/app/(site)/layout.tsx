import Header from "@/components/Header/Header";

// Every page except login and sign-up: the header bar on top of the page
export default function SiteLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <Header />
      {children}
    </>
  );
}
