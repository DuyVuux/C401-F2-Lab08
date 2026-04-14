"use client";
import React from 'react';
import Link from 'next/link';
import { MessageSquare, LayoutDashboard, Settings } from 'lucide-react';

export function Sidebar() {
  return (
    <aside className="w-16 md:w-[260px] h-full flex flex-col border-r border-white/5 bg-background text-gray-400">
      <div className="p-4 md:p-6 mb-4 mt-2">
        <h1 className="hidden md:block text-xl font-display font-semibold text-white">CS Agent</h1>
        <div className="md:hidden flex justify-center w-full text-primary">
           <CpuIcon className="w-6 h-6" />
        </div>
      </div>
      
      <nav className="flex-1 flex flex-col gap-2 px-3">
        <Link href="/" className="flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-white/5 text-white transition-colors group">
          <MessageSquare size={20} className="group-hover:text-primary transition-colors"/>
          <span className="hidden md:block font-medium">Hội thoại IT</span>
        </Link>
        <Link href="/" className="flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-white/5 transition-colors group">
          <LayoutDashboard size={20} className="group-hover:text-primary transition-colors"/>
          <span className="hidden md:block font-medium">Ops Metrics</span>
        </Link>
      </nav>

      <div className="p-4 border-t border-white/5">
        <button className="flex items-center justify-center md:justify-start gap-3 w-full p-2 md:px-3 hover:bg-white/5 rounded-xl transition-colors">
          <Settings size={20} />
          <span className="hidden md:block text-sm">Cài đặt</span>
        </button>
      </div>
    </aside>
  );
}

const CpuIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>
);
