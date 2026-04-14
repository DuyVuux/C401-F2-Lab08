"use client";
import React, { useRef, useEffect } from 'react';
import { useAgentStore } from '@/store/useAgentStore';
import { ChatBubble } from '../molecules/ChatBubble';
import { ChatInput } from './ChatInput';
import { AgentProgress } from '../molecules/AgentProgress';

export function ChatInterface() {
  const { messages, currentPhase, addMessage, setPhase } = useAgentStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentPhase]);

  const handleSendMessage = (content: string) => {
    // 1. Add User Message
    addMessage({ id: Date.now().toString(), role: 'user', content });
    
    // 2. Trigger Agent Pipeline (Demo behavior)
    setPhase('routing');
    
    // Simulate delays & state changes
    setTimeout(() => setPhase('retrieval'), 1500);
    setTimeout(() => setPhase('synthesizing'), 3500);
    setTimeout(() => {
      setPhase('idle');
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'agent',
        content: `Tôi đã kiểm tra dữ liệu từ Knowledge Base. Theo quy trình hiện tại, hệ thống báo lỗi này liên quan đến VPN Gateway.\n\nVui lòng thử kết nối lại bằng server dự phòng hoặc khởi động lại client.`,
        citations: [
           { id: 'doc_vpn_01', label: 'Quy trình xử lý sự cố VPN v2.1' },
           { id: 'doc_network_03', label: 'IT-Helpdesk Manual' }
        ]
      });
    }, 5500);
  };

  return (
    <div className="relative flex-1 flex flex-col w-full h-full pb-[100px] overflow-hidden">
      <div className="flex-1 overflow-y-auto w-full p-4 md:p-8 space-y-6 scroll-smooth">
        
        {messages.map(msg => (
          <ChatBubble key={msg.id} message={msg} />
        ))}

        {currentPhase !== 'idle' && (
           <div className="flex w-full max-w-4xl mx-auto pl-14">
             <AgentProgress phase={currentPhase} />
           </div>
        )}
        
        <div ref={bottomRef} className="h-4" />
      </div>

      <ChatInput onSendMessage={handleSendMessage} disabled={currentPhase !== 'idle'} />
    </div>
  );
}
