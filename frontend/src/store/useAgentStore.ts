import { create } from 'zustand';

export type AgentPhase = 'routing' | 'retrieval' | 'synthesizing' | 'idle' | 'error';

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  citations?: { id: string; label: string }[];
}

interface AgentState {
  currentPhase: AgentPhase;
  messages: ChatMessage[];
  setPhase: (phase: AgentPhase) => void;
  addMessage: (msg: ChatMessage) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  currentPhase: 'idle',
  messages: [
    {
      id: '1',
      role: 'agent',
      content: 'Xin chào, tôi là AI Trợ lý Nội bộ CS & IT Helpdesk. Bạn cần chuẩn đoán hệ thống nào hôm nay?',
    }
  ],
  setPhase: (phase) => set({ currentPhase: phase }),
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
}));
