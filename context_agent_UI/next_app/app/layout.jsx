import "./globals.css";

export const metadata = {
  title: "Document Agent",
  description: "Next.js frontend for the Document Agent workspace",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
