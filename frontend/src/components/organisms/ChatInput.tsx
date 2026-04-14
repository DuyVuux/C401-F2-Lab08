"use client";
import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { Send } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (msg: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSendMessage, disabled }: ChatInputProps) {
  const [input, setInput] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !disabled) {
        onSendMessage(input);
        setInput("");
      }
    }
  };

  return (
    <div className={cn(
      "absolute bottom-6 left-1/2 -translate-x-1/2 w-[80%] max-w-3xl",
      "bg-pane backdrop-blur-xl p-2 rounded-2xl flex items-end",
      "border border-white/10 shadow-glass focus-within:border-white/30 transition-all",
      disabled ? "opacity-50 pointer-events-none" : ""
    )}>
      <textarea 
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        className="flex-1 bg-transparent border-none outline-none text-white placeholder-gray-500 font-sans p-3 resize-none h-[48px] max-h-32 text-sm leading-relaxed"
        placeholder="Nhập câu hỏi hoặc dùng /policy, /ticket để gọi nhanh Agent..."
        rows={1}
      />
      <button 
        onClick={() => { onSendMessage(input); setInput(""); }}
        disabled={!input.trim() || disabled}
        className="bg-primary hover:bg-primary-hover disabled:bg-gray-700 disabled:opacity-50 p-2.5 rounded-xl text-white transition-colors h-[40px] w-[40px] flex items-center justify-center mb-[4px] mr-1"
        aria-label="Gửi truy vấn"
      >
        <Send size={18} />
      </button>
    </div>
  );
}
