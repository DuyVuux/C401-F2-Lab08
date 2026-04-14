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

  const handleSendMessage = async (content: string) => {
    // 1. Add User Message
    addMessage({ id: Date.now().toString(), role: 'user', content });
    
    // 2. Trigger Agent Pipeline
    setPhase('routing');
    
    try {
      // Simulate slightly distinct phases for UX, while waiting for real backend
      const phaseTimers = [
        setTimeout(() => setPhase('retrieval'), 1000),
        setTimeout(() => setPhase('synthesizing'), 2000)
      ];

      const res = await fetch('http://localhost:8001/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: content })
      });

      phaseTimers.forEach(clearTimeout);

      if (!res.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await res.json();
      
      setPhase('idle');
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'agent',
        content: data.final_answer || "Tôi không thể tìm thấy câu trả lời.",
        citations: (data.sources || []).map((src: string, i: number) => ({
           id: `doc_${i}`,
           label: src
        }))
      });
    } catch (error) {
      console.error("Chat API error:", error);
      setPhase('error');
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'agent',
        content: "Xin lỗi hệ thống đang gặp sự cố. Không kết nối được với server backend.",
      });
      setTimeout(() => setPhase('idle'), 2000);
    }
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
