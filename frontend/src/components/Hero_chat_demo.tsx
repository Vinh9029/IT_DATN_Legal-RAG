import React, { useState, useEffect } from 'react';
import { User, Sparkles, CheckCircle2, Search } from 'lucide-react';
import { Status_badge } from './Status_badge';

const DEMO_SCENARIOS = [
  {
    question: "Đặt cọc mua nhà bằng giấy tay có hủy được không và phạt cọc ra sao?",
    answer: "Căn cứ **Điều 328 Bộ luật Dân sự 2015**:\n\n1. **Hiệu lực**: Hợp đồng đặt cọc giấy tay vẫn có hiệu lực pháp lý nếu có chữ ký xác nhận tự nguyện của các bên.\n2. **Phạt cọc**: Nếu bên nhận cọc từ chối giao kết tiếp hợp đồng, phải hoàn trả tiền cọc và trả thêm một khoản tương đương giá trị đặt cọc.\n\n*Status Badge: [Còn hiệu lực]*",
    badge: "Bộ luật Dân sự 2015"
  },
  {
    question: "Nghỉ việc không báo trước 45 ngày có được hưởng trợ cấp thất nghiệp không?",
    answer: "Căn cứ **Điều 49 Luật Việc làm 2013** & **Điều 35 Bộ luật Lao động 2019**:\n\n* **Trường hợp đơn phương chấm dứt trái pháp luật** (không đủ thời hạn báo trước): Người lao động **KHÔNG** đủ điều kiện nhận trợ cấp thất nghiệp.\n\n*Status Badge: [Còn hiệu lực]*",
    badge: "Luật Việc làm & Bộ luật Lao động"
  }
];

export const Hero_chat_demo: React.FC = () => {
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const [typedQuestion, setTypedQuestion] = useState('');
  const [stage, setStage] = useState<'typing_question' | 'thinking' | 'streaming_answer' | 'completed'>('typing_question');
  const [typedAnswer, setTypedAnswer] = useState('');

  const currentScenario = DEMO_SCENARIOS[scenarioIdx];

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    if (stage === 'typing_question') {
      const q = currentScenario.question;
      if (typedQuestion.length < q.length) {
        timer = setTimeout(() => {
          setTypedQuestion(q.substring(0, typedQuestion.length + 1));
        }, 40);
      } else {
        timer = setTimeout(() => setStage('thinking'), 400);
      }
    } else if (stage === 'thinking') {
      timer = setTimeout(() => setStage('streaming_answer'), 1200);
    } else if (stage === 'streaming_answer') {
      const a = currentScenario.answer;
      if (typedAnswer.length < a.length) {
        timer = setTimeout(() => {
          setTypedAnswer(a.substring(0, typedAnswer.length + 3));
        }, 20);
      } else {
        setStage('completed');
      }
    } else if (stage === 'completed') {
      timer = setTimeout(() => {
        setTypedQuestion('');
        setTypedAnswer('');
        setStage('typing_question');
        setScenarioIdx((prev) => (prev + 1) % DEMO_SCENARIOS.length);
      }, 4000);
    }

    return () => clearTimeout(timer);
  }, [stage, typedQuestion, typedAnswer, scenarioIdx]);

  return (
    <div className="w-full rounded-2xl border-2 border-slate-200/80 bg-white shadow-2xl overflow-hidden text-left font-sans ring-1 ring-black/5">
      {/* Browser-Style Header with Gradient Bottom */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-gradient-to-b from-slate-100 to-slate-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="size-3 rounded-full bg-red-400 shadow-inner" />
          <div className="size-3 rounded-full bg-amber-400 shadow-inner" />
          <div className="size-3 rounded-full bg-emerald-400 shadow-inner" />
          <span className="ml-2 font-mono text-[11px] font-semibold text-slate-500 flex items-center gap-1.5">
            <Search className="size-3 text-[#2563EB]" />
            luuhanh.vn/rag-assistant
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Scenario Indicator Dots */}
          <div className="flex items-center gap-1">
            {DEMO_SCENARIOS.map((_, idx) => (
              <div 
                key={idx} 
                className={`size-1.5 rounded-full transition-all duration-500 ${
                  idx === scenarioIdx 
                    ? 'bg-[#2563EB] scale-125' 
                    : 'bg-slate-300'
                }`} 
              />
            ))}
          </div>
          <div className="flex items-center gap-1.5 rounded-full bg-[#2563EB]/10 px-2.5 py-0.5 font-mono text-[10px] font-semibold text-[#2563EB]">
            <span className="size-1.5 rounded-full bg-[#2563EB] animate-pulse" />
            AI Engine Online
          </div>
        </div>
      </div>

      {/* Demo Chat Content Container */}
      <div className="p-5 space-y-4 min-h-[320px] max-h-[380px] overflow-y-auto bg-[#F8FAFC]/50">
        {/* User Question Bubble */}
        <div className="flex items-start gap-3 justify-end">
          <div className="max-w-[88%] rounded-2xl rounded-tr-sm bg-[#0F172A] px-4 py-3 text-xs text-white shadow-md font-medium">
            <p className="inline">{typedQuestion}</p>
            {stage === 'typing_question' && (
              <span className="inline-block w-1.5 h-3.5 bg-[#2563EB] ml-1 animate-pulse rounded-sm" />
            )}
          </div>
          <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-700 text-xs font-bold shadow-inner">
            <User className="size-4" />
          </div>
        </div>

        {/* AI Response Block */}
        {(stage === 'thinking' || stage === 'streaming_answer' || stage === 'completed') && (
          <div className="flex items-start gap-3">
            {/* AI Avatar with Pulse Ring during streaming */}
            <div className="relative">
              {(stage === 'thinking' || stage === 'streaming_answer') && (
                <div className="absolute -inset-1 rounded-xl bg-[#2563EB]/20 animate-ping" style={{ animationDuration: '2s' }} />
              )}
              <div className="relative flex size-8 shrink-0 items-center justify-center rounded-lg bg-[#0F172A] text-white overflow-hidden p-1 shadow-xs border border-slate-700">
                <img src="/logo.png" alt="Logo" className="size-full object-contain" />
              </div>
            </div>

            <div className="flex-1 rounded-2xl rounded-tl-sm border border-slate-200 bg-white p-4 text-xs leading-relaxed text-[#0F172A] shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2 font-mono text-[10px] text-slate-400">
                <span className="flex items-center gap-1 font-semibold text-[#2563EB]">
                  <Sparkles className="size-3" />
                  Căn cứ: {currentScenario.badge}
                </span>
                <span className="text-emerald-600 font-medium flex items-center gap-1">
                  <CheckCircle2 className="size-3" />
                  Xác thực RAG
                </span>
              </div>

              {stage === 'thinking' ? (
                <div className="flex items-center gap-2 py-3 text-slate-500 font-mono text-[11px]">
                  <div className="flex space-x-1">
                    <div className="size-1.5 rounded-full bg-[#2563EB] animate-bounce" />
                    <div className="size-1.5 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="size-1.5 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span>Đang tra cứu dữ liệu pháp luật hiện hành...</span>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="whitespace-pre-wrap font-sans text-slate-700">
                    {typedAnswer.replace('*Status Badge: [Còn hiệu lực]*', '')}
                  </p>
                  {typedAnswer.includes('Còn hiệu lực') && (
                    <div className="pt-2">
                      <Status_badge status="valid" label="Văn bản còn hiệu lực" />
                    </div>
                  )}
                  {stage === 'streaming_answer' && (
                    <span className="inline-block w-1.5 h-3.5 bg-[#2563EB] ml-0.5 animate-pulse rounded-sm" />
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Demo Footer with Micro Progress Bar */}
      <div className="border-t border-slate-200 bg-slate-50 px-4 py-2 space-y-1.5">
        <div className="flex items-center justify-between font-mono text-[10px] text-slate-400">
          <span>* Minh họa hội thoại Trợ lý Legal AI</span>
          <span className="text-[#2563EB] font-semibold">Live Interactive Demo</span>
        </div>
        {/* Progress Bar showing typing/streaming state */}
        <div className="h-0.5 w-full rounded-full bg-slate-200 overflow-hidden">
          <div 
            className="h-full rounded-full bg-[#2563EB] transition-all duration-300 ease-linear"
            style={{ 
              width: stage === 'typing_question' 
                ? `${(typedQuestion.length / currentScenario.question.length) * 100}%`
                : stage === 'thinking' 
                ? '100%'
                : stage === 'streaming_answer'
                ? `${(typedAnswer.length / currentScenario.answer.length) * 100}%`
                : '100%',
              opacity: stage === 'completed' ? 0.4 : 1
            }}
          />
        </div>
      </div>
    </div>
  );
};
