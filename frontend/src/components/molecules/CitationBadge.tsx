"use client";
import React from 'react';
import { useUIStore } from '@/store/useUIStore';
import { cn } from '@/lib/utils';

interface CitationBadgeProps {
  docId: string;
  label: string;
}

export function CitationBadge({ docId, label }: CitationBadgeProps) {
  const { openCitationContext } = useUIStore();

  return (
    <button 
      onClick={() => openCitationContext(docId)}
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 mx-1",
        "text-[11px] font-medium text-citation bg-citation/10",
        "rounded border border-citation/20 transition-all",
        "hover:bg-citation/20 hover:scale-105 focus:ring-2 focus:ring-citation/50"
      )}
      aria-label={`Xem tài liệu nguồn: ${label}`}
      title="Bấm để xem chi tiết tài liệu"
    >
      [{label}]
    </button>
  );
}
