import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'CS & IT Helpdesk AI',
  description: 'Trợ lý nội bộ AI-powered bằng RAG và Multi-Agent',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className="dark">
      <body className="antialiased selection:bg-primary/30 selection:text-white">
        {children}
      </body>
    </html>
  );
}
