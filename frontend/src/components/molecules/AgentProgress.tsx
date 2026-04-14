"use client";
import React from 'react';
import type { AgentPhase } from '@/store/useAgentStore';

export function AgentProgress({ phase }: { phase: AgentPhase }) {
  if (phase === 'idle') return null;

  const phaseTexts = {
    routing: "Đang định tuyến tới IT Worker...",
    retrieval: "Đang truy xuất cẩm nang nội bộ...",
    synthesizing: "Đang tổng hợp thông tin...",
    error: "Mô-đun tìm kiếm hiện đang bảo trì. Vui lòng thử từ khoá ngắn hơn.",
    idle: "",
  };

  if (phase === 'error') {
    return (
      <div className="p-3 my-2 rounded-2xl bg-danger/10 text-danger border border-danger/20 font-sans text-sm animate-in fade-in zoom-in w-fit">
        {phaseTexts.error}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4 bg-pane border border-white/5 rounded-2xl shadow-glass w-fit animate-in fade-in slide-in-from-bottom-2">
      <div className="text-sm font-display text-gray-300 animate-pulse">
        {phaseTexts[phase]}
      </div>
      <div className="h-1 w-48 bg-white/10 rounded-full overflow-hidden relative">
         <div className="absolute top-0 bottom-0 left-0 bg-primary animate-[translate_1.5s_infinite] w-1/3 rounded-full"></div>
      </div>
    </div>
  );
}
