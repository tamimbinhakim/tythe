export const metadata = {
  title: "Tythe · streaming demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: 32 }}>{children}</body>
    </html>
  );
}
