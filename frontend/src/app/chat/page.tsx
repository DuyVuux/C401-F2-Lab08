import React from 'react';
import { ChatInterface } from '@/components/organisms/ChatInterface';

export default function ChatPage() {
  return (
    <div className="flex flex-col h-full w-full bg-background relative">
      <header className="absolute top-0 w-full p-4 md:px-8 border-b border-white/5 bg-background/80 backdrop-blur-md z-10 hidden md:block">
        <h2 className="text-xl font-display font-semibold text-white">Trợ Lý Ảo CNTT</h2>
        <p className="text-xs text-gray-400">Kết nối nền tảng Knowledge Base v2.1</p>
      </header>
      
      <div className="flex-1 w-full pt-0 md:pt-20">
         <ChatInterface />
      </div>
    </div>
  );
}
