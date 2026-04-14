"use client";
import React from 'react';
import { useUIStore } from '@/store/useUIStore';
import { X, FileText } from 'lucide-react';

export function TelemetryDrawer() {
  const { isDrawerOpen, activeCitationId, closeDrawer } = useUIStore();

  if (!isDrawerOpen) return null;

  return (
    <div className="h-full flex flex-col pt-4 overflow-hidden relative">
      <div className="px-5 py-3 flex items-center justify-between border-b border-white/5 pb-4">
        <h2 className="font-display font-semibold text-lg flex items-center gap-2">
           <FileText size={18} className="text-citation" />
           Chi tiết Tài Liệu
        </h2>
        <button 
          onClick={closeDrawer} 
          className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-white"
        >
           <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 font-sans">
        <div className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">
           Document ID: {activeCitationId || 'N/A'}
        </div>
        
        {/* Placeholder Content */}
        <div className="space-y-6">
           <div>
              <h3 className="text-sm font-semibold mb-2 text-primary">Quy trình xử lý sự cố VPN v2.1</h3>
              <p className="text-sm text-gray-300 leading-relaxed bg-white/5 p-4 rounded-xl shadow-inner border border-white/5">
                Trường hợp cấu hình VPN Client báo lỗi &quot;Gateway Timeout 504&quot; hoặc bị loop Authentication:
                <br/><br/>
                1. Buộc đóng tiến trình GlobalProtect/Cisco AnyConnect qua Task Manager.<br/>
                2. Kiểm tra lại tín hiệu mạng, flush DNS (ipconfig /flushdns).<br/>
                3. Đăng nhập lại bằng Server Gateway phụ: <b>vpn2.corp.local</b>.<br/>
                <br/>
                <mark className="bg-citation/30 text-white rounded px-1">Lỗi liên quan đến VPN Gateway thường do server chính quá tải.</mark>
              </p>
           </div>
        </div>

      </div>
    </div>
  );
}
