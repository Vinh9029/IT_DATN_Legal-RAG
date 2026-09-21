import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/header';
import { Button } from '@/components/ui/button';
import { 
  ArrowDown, 
  ArrowRight, 
  BriefcaseBusiness, 
  FileCheck2, 
  Landmark, 
  Scale, 
  Bot, 
  Sparkles,
  ShieldCheck
} from 'lucide-react';

const areas = [
  { 
    number: "01", 
    title: "Hợp đồng & dân sự", 
    text: "Đặt cọc, mua bán, vay mượn, bồi thường và giải quyết nghĩa vụ dân sự phát sinh.", 
    icon: FileCheck2 
  },
  { 
    number: "02", 
    title: "Lao động", 
    text: "Hợp đồng lao động, tiền lương, bảo hiểm xã hội, kỷ luật và chấm dứt việc làm đúng quy định.", 
    icon: BriefcaseBusiness 
  },
  { 
    number: "03", 
    title: "Đất đai & nhà ở", 
    text: "Chuyển nhượng, thừa kế, cấp giấy chứng nhận (Sổ đỏ) và giải quyết tranh chấp quyền sử dụng đất.", 
    icon: Landmark 
  },
  { 
    number: "04", 
    title: "Doanh nghiệp", 
    text: "Thành lập, quản trị, đầu tư, tư vấn thay đổi nội dung ĐKKD và nghĩa vụ tuân thủ pháp luật.", 
    icon: Scale 
  },
];

export const IndexPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-[#2563EB]/20 selection:text-[#2563EB]">
      <Header />

      <main>
        {/* HERO SECTION */}
        <section className="relative mx-auto min-h-[calc(100vh-5rem)] max-w-7xl px-5 pb-20 pt-12 md:px-10 md:pt-20">
          <div className="grid gap-12 lg:grid-cols-[1fr_20rem] items-start">
            <div className="editorial-rise">
              <div className="inline-flex items-center gap-2 rounded-full border border-[#2563EB]/30 bg-[#2563EB]/10 px-3.5 py-1 text-xs font-mono font-medium text-[#2563EB]">
                <Sparkles className="size-3.5" />
                <span>Trợ lý AI & Tra cứu Pháp luật Việt Nam</span>
              </div>

              <h1 className="mt-6 max-w-5xl font-display text-[clamp(4.2rem,11vw,9.5rem)] uppercase leading-[0.85] text-[#0F172A] tracking-tight">
                Pháp luật,<br />
                <span className="text-[#2563EB]">đọc được</span><br />
                rõ ràng.
              </h1>
            </div>

            <div className="flex flex-col justify-end border-l-2 border-slate-200 pl-6 lg:mt-24 lg:pb-4">
              <p className="text-base leading-7 text-slate-600">
                Tìm hướng đi đầu tiên cho vấn đề pháp lý của bạn — bằng ngôn ngữ gần gũi, chính xác và có giới hạn rõ ràng.
              </p>

              <div className="mt-8 space-y-3">
                <Button 
                  variant="primary" 
                  size="lg" 
                  onClick={() => navigate('/tro-ly')}
                  className="w-full justify-between bg-[#0F172A] hover:bg-[#1E3A8A] text-white shadow-md group"
                >
                  <span className="font-mono text-sm uppercase tracking-wider">Mở trợ lý pháp lý</span>
                  <ArrowRight className="size-5 transition-transform group-hover:translate-x-1 text-[#2563EB]" />
                </Button>

                <p className="font-mono text-[11px] text-slate-500">
                  ⚡ Không cần đăng ký account · Phản hồi tiếng Việt chuẩn căn cứ
                </p>
              </div>
            </div>
          </div>

          <div className="editorial-grow absolute inset-x-5 bottom-8 flex items-center justify-between border-t border-slate-200 pt-4 font-mono text-[11px] uppercase text-slate-500 md:inset-x-10">
            <span className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-[#2563EB]" />
              Nội dung tham khảo căn cứ luật hiện hành
            </span>
            <ArrowDown className="size-4 animate-bounce text-[#2563EB]" />
          </div>
        </section>

        {/* SECTION 2: LĨNH VỰC THƯỜNG GẶP */}
        <section id="linh-vuc" className="border-y border-slate-200 bg-white">
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-10 md:py-28">
            <div className="grid gap-8 border-b border-slate-200 pb-10 md:grid-cols-2">
              <div>
                <p className="font-mono text-xs uppercase tracking-widest text-[#2563EB]">
                  Lĩnh vực thường gặp
                </p>
                <h2 className="mt-2 font-display text-5xl uppercase leading-none text-[#0F172A] md:text-6xl">
                  Bắt đầu từ đúng nhóm vấn đề.
                </h2>
              </div>
              <div className="flex items-end md:justify-end">
                <p className="max-w-md text-sm leading-relaxed text-slate-600">
                  Phân loại rõ ràng các nhóm vụ việc phổ biến giúp bạn dễ dàng đưa ra câu hỏi và nhận hướng dẫn chi tiết từ Trợ lý AI.
                </p>
              </div>
            </div>

            <div className="grid md:grid-cols-2">
              {areas.map((area) => (
                <article 
                  key={area.number} 
                  onClick={() => navigate('/tro-ly')}
                  className="group cursor-pointer border-b border-slate-200 py-8 transition-colors hover:bg-slate-50 md:odd:border-r md:odd:pr-10 md:even:pl-10"
                >
                  <div className="flex items-start justify-between">
                    <span className="font-mono text-xs text-slate-400 group-hover:text-[#2563EB]">{area.number}</span>
                    <div className="rounded-lg bg-slate-100 p-2.5 transition-colors group-hover:bg-[#2563EB]/10">
                      <area.icon className="size-6 text-[#2563EB]" strokeWidth={1.5} />
                    </div>
                  </div>
                  <h3 className="mt-8 font-display text-3xl uppercase text-[#0F172A] transition-colors group-hover:text-[#2563EB]">
                    {area.title}
                  </h3>
                  <p className="mt-3 max-w-md text-sm leading-6 text-slate-600">
                    {area.text}
                  </p>
                  <div className="mt-5 inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-[#2563EB] opacity-0 transition-opacity group-hover:opacity-100">
                    <span>Hỏi trợ lý về chủ đề này</span>
                    <ArrowRight className="size-3.5" />
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* SECTION 3: CÁCH TIẾP CẬN */}
        <section id="quy-trinh" className="mx-auto grid max-w-7xl gap-12 px-5 py-20 md:px-10 md:py-28 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="font-mono text-xs uppercase tracking-widest text-[#2563EB]">
              Cách tiếp cận
            </p>
            <h2 className="mt-4 font-display text-5xl uppercase leading-none text-[#0F172A] md:text-6xl">
              Từ tình huống đến hướng xử lý.
            </h2>
            <p className="mt-6 text-sm leading-relaxed text-slate-600">
              Quy trình 3 bước giúp định hình vụ việc pháp lý một cách rõ ràng và khoa học.
            </p>
          </div>

          <ol className="border-t-2 border-[#0F172A]">
            {[
              ["01", "Mô tả sự việc", "Nêu rõ chủ thể (cá nhân/công ty), các mốc thời gian diễn ra sự việc, văn bản ký kết và mong muốn cần giải quyết."],
              ["02", "Làm rõ căn cứ pháp lý", "Xác định các quy định pháp luật liên quan (Điều, Khoản, Luật hiện hành) và chỉ ra dữ kiện hay tài liệu còn thiếu."],
              ["03", "Chọn bước tiếp theo", "Chuẩn bị hồ sơ pháp lý, xây dựng phương án trao đổi hòa giải hoặc tìm Luật sư đại diện khi tình huống phức tạp."],
            ].map(([number, title, text]) => (
              <li key={number} className="grid grid-cols-[3.5rem_1fr] gap-4 border-b border-slate-200 py-8 transition-colors hover:bg-slate-50/50">
                <span className="font-mono text-sm font-bold text-[#2563EB]">{number}</span>
                <div>
                  <h3 className="text-xl font-bold text-[#0F172A]">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* SECTION 4: GIỚI HẠN & CẢNH BÁO */}
        <section id="luu-y" className="bg-[#0F172A] text-white py-20 md:py-24">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 md:px-10 lg:grid-cols-[1fr_1.3fr] items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded-md bg-[#2563EB]/20 px-3 py-1 font-mono text-xs font-semibold text-[#2563EB]">
                <Bot className="size-4" />
                <span>Giới hạn cần biết</span>
              </div>
              <h2 className="mt-4 font-display text-4xl uppercase leading-tight md:text-5xl text-white">
                Thông tin tốt giúp bạn hỏi đúng.<br />Không thay thế Luật sư hiểu hồ sơ.
              </h2>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 md:p-8 backdrop-blur-sm">
              <p className="text-sm leading-7 text-slate-300">
                Nội dung trên trang và phản hồi của Trợ lý AI mang tính chất tham khảo chung, có thể chưa phản ánh đầy đủ diễn biến thực tế hoặc các điều chỉnh văn bản mới nhất. Với các tranh chấp, tố tụng hình sự hay vụ việc mang rủi ro tài chính lớn, bạn hãy luôn chủ động tham khảo tư vấn chuyên môn từ Luật sư có giấy phép hành nghề.
              </p>
              <div className="mt-6 pt-6 border-t border-slate-800 flex items-center justify-between">
                <span className="font-mono text-xs text-slate-400">LƯU HÀNH Legal Tech System</span>
                <Button 
                  variant="accent" 
                  size="sm" 
                  onClick={() => navigate('/tro-ly')}
                >
                  Trải nghiệm Trợ lý ngay
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-10 md:flex-row md:items-end md:justify-between md:px-10">
          <div>
            <p className="font-display text-3xl uppercase tracking-wider text-[#0F172A]">LƯU HÀNH</p>
            <p className="mt-2 text-sm text-slate-500">Pháp luật Việt Nam được trình bày để dễ tiếp cận & áp dụng.</p>
          </div>
          <div className="flex flex-col gap-2 font-mono text-xs text-slate-500 md:text-right">
            <span>© 2026 LƯU HÀNH Legal RAG · Nội dung mang tính chất tham khảo</span>
            <span className="text-[10px] text-slate-400">Tích hợp Supabase Engine & AI RAG System</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
