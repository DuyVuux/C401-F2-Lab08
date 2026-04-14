import React from 'react';
import { cn } from '@/lib/utils';
import type { ChatMessage } from '@/store/useAgentStore';
import { CitationBadge } from '../molecules/CitationBadge';
import { User, Cpu } from 'lucide-react';

export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  // Chuyển block text để xử lý Citations (mô phỏng)
  // Thực tế có thể dùng Parser với RegEx để thế placeholder thành CitationBadge
  
  return (
    <div className={cn(
      "flex gap-4 p-4 w-full max-w-4xl mx-auto rounded-2xl animate-in fade-in slide-in-from-bottom-2",
      isUser ? "flex-row-reverse" : ""
    )}>
      {/* Avatar */}
      <div className={cn(
        "flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center border shadow-glass",
        isUser 
          ? "bg-secondary text-white border-white/10" 
          : "bg-primary/20 text-primary border-primary/30"
      )}>
        {isUser ? <User size={20} /> : <Cpu size={20} />}
      </div>

      {/* Content */}
      <div className={cn(
        "flex flex-col gap-2 max-w-[80%]",
        isUser ? "items-end" : "items-start"
      )}>
        <span className="text-xs text-gray-500 font-sans px-1">
          {isUser ? "Bạn" : "CS & IT Agent"}
        </span>
        <div className={cn(
          "p-4 rounded-2xl font-sans text-sm leading-relaxed whitespace-pre-wrap",
          isUser 
            ? "bg-secondary/40 border border-white/5 text-white rounded-tr-none" 
            : "bg-pane border border-primary/20 text-gray-100 rounded-tl-none shadow-glass"
        )}>
          {message.content}
          
          {/* Chèn citation block demo vào cuối text nếu có */}
          {!isUser && message.citations && (
            <div className="mt-2 pt-2 border-t border-white/10 flex flex-wrap gap-1 items-center">
              <span className="text-[11px] text-gray-400 mr-1">Nguồn tham khảo:</span>
              {message.citations.map(c => (
                <CitationBadge key={c.id} docId={c.id} label={c.label} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
