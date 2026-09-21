import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, ArrowRight, HelpCircle, ChevronRight } from 'lucide-react';
import { Button } from './ui/Button';

interface FAQItem {
  id: string;
  question: string;
  answer: string;
  actionText?: string;
  actionLink?: string;
}

const FAQS: FAQItem[] = [
  {
    id: 'faq-1',
    question: 'Cách tra cứu câu hỏi & văn bản pháp luật thế nào?',
    answer: 'Bạn chỉ cần nhập tình huống thực tế bằng tiếng Việt (ví dụ: "Đặt cọc mua đất bằng giấy tay"). Hệ thống RAG AI sẽ tự động phân tích và trích dẫn căn cứ điều luật liên quan.',
    actionText: 'Mở trang Hỏi Đáp AI ngay',
    actionLink: '/tro-ly'
  },
  {
    id: 'faq-2',
    question: 'LƯU HÀNH hỗ trợ những nhóm vấn đề pháp lý nào?',
    answer: 'Hệ thống hỗ trợ 4 nhóm lĩnh vực trọng tâm: Hợp đồng & Dân sự, Lao động & Bảo hiểm, Đất đai & Sổ đỏ, Doanh nghiệp & Đầu tư.'
  },
  {
    id: 'faq-3',
    question: 'Thông tin từ Trợ lý AI có đảm bảo chính xác không?',
    answer: 'Nội dung phản hồi được tổng hợp tự động từ văn bản quy phạm pháp luật hiện hành Việt Nam để tham khảo định hướng ban đầu, không thay thế ý kiến tư vấn chính thức của Luật sư.'
  }
];

export const Floating_chatbot: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedFaq, setSelectedFaq] = useState<FAQItem | null>(null);
  const navigate = useNavigate();

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {/* CHAT POPOVER WINDOW */}
      {isOpen && (
        <div className="mb-4 w-80 sm:w-96 rounded-2xl border-2 border-slate-200 bg-white shadow-2xl overflow-hidden font-sans editorial-rise">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 bg-[#0F172A] px-4 py-3 text-white">
            <div className="flex items-center gap-3">
              <div className="relative flex size-8 items-center justify-center rounded-lg bg-white p-0.5 overflow-hidden">
                <img src="/logo.png" alt="Logo" className="size-full object-contain" />
              </div>
              <div>
                <h3 className="font-bold text-sm leading-none">Hỏi Đáp Nhanh LƯU HÀNH</h3>
                <p className="font-mono text-[10px] text-[#2563EB] mt-1">⚡ FAQ Engine & Guide</p>
              </div>
            </div>
            <button 
              onClick={() => setIsOpen(false)}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
            >
              <X className="size-5" />
            </button>
          </div>

          {/* Content Body */}
          <div className="p-4 max-h-[380px] overflow-y-auto space-y-3 bg-[#F8FAFC]">
            {selectedFaq ? (
              <div className="space-y-3">
                <button
                  onClick={() => setSelectedFaq(null)}
                  className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-[#2563EB] hover:underline"
                >
                  ← Quay lại danh sách câu hỏi
                </button>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <h4 className="font-bold text-sm text-[#0F172A]">{selectedFaq.question}</h4>
                  <p className="mt-2 text-xs leading-relaxed text-slate-600 font-normal">
                    {selectedFaq.answer}
                  </p>

                  {selectedFaq.actionLink && (
                    <Button
                      variant="accent"
                      size="sm"
                      onClick={() => {
                        setIsOpen(false);
                        navigate(selectedFaq.actionLink!);
                      }}
                      className="mt-4 w-full justify-center gap-2 font-mono text-xs"
                    >
                      <span>{selectedFaq.actionText}</span>
                      <ArrowRight className="size-3.5" />
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-center gap-1.5 font-mono text-xs font-semibold uppercase text-slate-500 mb-2">
                  <HelpCircle className="size-4 text-[#2563EB]" />
                  <span>Câu hỏi thường gặp</span>
                </div>

                <div className="space-y-2">
                  {FAQS.map((faq) => (
                    <button
                      key={faq.id}
                      onClick={() => setSelectedFaq(faq)}
                      className="group flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-left text-xs font-medium text-[#0F172A] transition-all hover:border-[#2563EB] hover:bg-slate-50 shadow-xs"
                    >
                      <span className="line-clamp-2">{faq.question}</span>
                      <ChevronRight className="size-4 shrink-0 text-slate-400 group-hover:text-[#2563EB]" />
                    </button>
                  ))}
                </div>

                <div className="mt-4 pt-3 border-t border-slate-200">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setIsOpen(false);
                      navigate('/tro-ly');
                    }}
                    className="w-full justify-between font-mono text-xs bg-[#0F172A] hover:bg-[#1E3A8A]"
                  >
                    <span>Hỏi đáp Trợ lý AI chính thức</span>
                    <ArrowRight className="size-3.5 text-[#2563EB]" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* FLOATING BUTTON WITH ANIMATIONS */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="group relative flex size-14 items-center justify-center rounded-full bg-[#0F172A] text-white shadow-2xl transition-transform hover:scale-110 focus:outline-none focus:ring-4 focus:ring-[#2563EB]/40 border-2 border-white cursor-pointer"
      >
        {/* Pulsing Outer Ring */}
        <span className="absolute -inset-1 rounded-full bg-[#2563EB] opacity-40 animate-ping" />

        {/* Floating Sparkle Image */}
        <img 
          src="/sparkles.png" 
          alt="Sparkle" 
          className="absolute -top-1.5 -right-1.5 size-5 animate-pulse drop-shadow-md" 
        />

        {/* Logo Image */}
        <div className="relative z-10 flex size-9 items-center justify-center rounded-full bg-white p-1 overflow-hidden shadow-xs">
          <img src="/logo.png" alt="Logo Bot" className="size-full object-contain" />
        </div>
      </button>
    </div>
  );
};
