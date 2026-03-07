import { ChatWindow } from '@/components/chat/ChatWindow';

export const metadata = {
  title: 'Flownote AI Agent',
  description: '사용자 데이터 기반 RAG 스트리밍 챗봇',
};

export default function ChatPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex flex-col p-4 md:p-8 font-sans antialiased text-slate-800">
      <div className="w-full flex-1 max-w-7xl mx-auto items-center justify-center flex">
        <ChatWindow />
      </div>
    </main>
  );
}
