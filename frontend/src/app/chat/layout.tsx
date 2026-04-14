"use client";
import React from 'react';
import { Sidebar } from '@/components/organisms/Sidebar';
import { TelemetryDrawer } from '@/components/organisms/TelemetryDrawer';
import { useUIStore } from '@/store/useUIStore';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { isDrawerOpen } = useUIStore();

  return (
    <div className="flex h-screen w-full bg-background text-white font-sans overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col relative order-2 overflow-y-auto">
        {children}
      </main>

      {/* Conditional Right Pane */}
      <aside 
        className={`border-l border-white/10 bg-pane bg-glass-gradient backdrop-blur-xl shadow-glass order-3 transition-all duration-300 ease-in-out ${
          isDrawerOpen ? 'w-96 translate-x-0 opacity-100 visible flex-shrink-0' : 'w-0 translate-x-full opacity-0 invisible'
        }`}
      >
        <TelemetryDrawer />
      </aside>
    </div>
  );
}
