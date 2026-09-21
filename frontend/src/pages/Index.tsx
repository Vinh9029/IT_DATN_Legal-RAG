import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/Button';
import { Hero_chat_demo } from '@/components/Hero_chat_demo';
import { Floating_chatbot } from '@/components/Floating_chatbot';
import {
  ArrowDown,
  ArrowRight,
  BriefcaseBusiness,
  FileCheck2,
  Landmark,
  Scale,
  Bot,
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

export const Index: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-[#2563EB]/20 selection:text-[#2563EB] relative">
      <Header />

      <main>
        {/* HERO SECTION STRETCHED FULL WIDTH (w-full) WITH main_hero.png BACKGROUND */}
        <section
          className="relative w-full min-h-[calc(100vh-5rem)] px-5 md:px-12 lg:px-16 pb-20 pt-12 md:pt-16 bg-cover bg-center bg-no-repeat rounded-b-3xl"
          style={{
            backgroundImage: `linear-gradient(rgba(248, 250, 252, 0.3), rgba(248, 250, 252, 0.05)), url('/main_hero.png')`
          }}
        >
          <div className="mx-auto max-w-7xl">
            <div className="grid gap-10 lg:grid-cols-[1fr_1fr] items-start">
              <div className="editorial-rise">
                <div className="inline-flex items-center gap-2.5 rounded-full border border-slate-200 bg-white/95 backdrop-blur-sm px-4 py-1.5 text-xs font-mono font-medium text-slate-700 shadow-sm">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-[#2563EB] opacity-60"></span>
                    <span className="relative inline-flex size-2 rounded-full bg-[#2563EB]"></span>
                  </span>
                  <span>Trợ lý AI & Tra cứu Pháp luật Việt Nam</span>
                </div>

                {/* HEADING TEXT WITH PROPER SPACING */}
                <h1 className="mt-6 font-display text-[clamp(3.8rem,8.5vw,7.5rem)] uppercase leading-[1.15] text-[#0F172A] tracking-tight">
                  Pháp luật,<br />
                  <span className="text-[#2563EB]">đọc được</span><br />
                  rõ ràng.
                </h1>

                <div className="mt-8 flex flex-col sm:flex-row gap-4 items-stretch sm:items-center justify-center sm:justify-start">
                  <Button
                    variant="accent"
                    size="lg"
                    onClick={() => navigate('/tro-ly')}
                    className="justify-center gap-3 bg-[#2563EB] hover:bg-[#1D4ED8] text-white shadow-md group px-8"
                  >
                    <span className="font-mono text-sm uppercase tracking-wider">Mở trợ lý pháp lý</span>
                    <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" />
                  </Button>
                </div>
              </div>

              {/* HERO RIGHT COLUMN: EDITORIAL INTRO TEXT DIRECTLY ABOVE ANIMATED CHATBOT DEMO */}
              <div className="lg:pl-4">
                <div className="mb-6">
                  <p className="font-display text-xl md:text-2xl uppercase leading-snug tracking-tight text-[#0F172A]">
                    Tìm hướng đi đầu tiên cho vấn đề pháp lý của bạn —
                  </p>
                  <p className="mt-2 text-sm md:text-base leading-relaxed text-slate-600 font-medium italic">
                    bằng ngôn ngữ gần gũi, chính xác và có giới hạn rõ ràng.
                  </p>
                </div>

                <Hero_chat_demo />
              </div>
            </div>
          </div>

          {/* BOTTOM DISCLAIMER MOVED TO THE RIGHT NEXT TO THE ARROW */}
          <div className="editorial-grow absolute inset-x-5 bottom-6 flex items-center justify-end gap-3 border-t border-slate-300/70 pt-4 font-mono text-[11px] uppercase text-slate-700 md:inset-x-12">
            <span className="flex items-center gap-2 font-medium bg-white/80 backdrop-blur-xs px-3 py-1 rounded-md border border-slate-200/60">
              <ShieldCheck className="size-4 text-[#2563EB]" />
              Nội dung tham khảo căn cứ luật hiện hành
            </span>
            <ArrowDown className="size-4 animate-bounce text-[#2563EB]" />
          </div>
        </section>

        {/* SECTION 2: LĨNH VỰC THƯỜNG GẶP */}
        <section
          id="linh-vuc"
          className="border-y border-slate-200 bg-white relative bg-cover bg-center bg-no-repeat"
          style={{
            backgroundImage: `linear-gradient(to right, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.6)), url('/hero_2.png')`
          }}
        >
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-10 md:py-28">
            <div className="grid gap-8 border-b border-slate-200 pb-12 md:grid-cols-2 items-end">
              <div className="border-l-[3px] border-[#2563EB] pl-5">
                <p className="font-mono text-xs uppercase tracking-widest text-[#2563EB]">
                  Lĩnh vực thường gặp
                </p>
                <h2 className="mt-3 font-display text-4xl uppercase leading-tight text-[#0F172A] md:text-6xl tracking-tight">
                  Bắt đầu từ đúng nhóm vấn đề.
                </h2>
              </div>
              <div className="flex md:justify-end">
                <p className="max-w-md text-sm md:text-base leading-relaxed text-slate-600 font-medium bg-white/70 backdrop-blur-xs p-4 rounded-xl border border-slate-200/60">
                  Phân loại rõ ràng các nhóm vụ việc phổ biến giúp bạn dễ dàng đưa ra câu hỏi và nhận hướng dẫn chi tiết từ Trợ lý AI.
                </p>
              </div>
            </div>

            {/* CARDS GRID */}
            <div className="mt-12 grid gap-6 md:grid-cols-2">
              {areas.map((area) => (
                <article
                  key={area.number}
                  onClick={() => navigate('/tro-ly')}
                  className="group cursor-pointer rounded-2xl border border-slate-200 bg-white/90 p-8 shadow-xs backdrop-blur-md transition-all duration-300 hover:border-[#2563EB] hover:bg-white hover:shadow-xl hover:-translate-y-1 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-[#2563EB] bg-[#2563EB]/10 px-2.5 py-1 rounded-md">
                        MỤC {area.number}
                      </span>
                      <div className="rounded-xl bg-slate-100 p-3 transition-colors group-hover:bg-[#2563EB] group-hover:text-white">
                        <area.icon className="size-6 text-[#2563EB] group-hover:text-white transition-colors" strokeWidth={1.5} />
                      </div>
                    </div>
                    <h3 className="mt-6 font-display text-2xl md:text-3xl uppercase text-[#0F172A] transition-colors group-hover:text-[#2563EB]">
                      {area.title}
                    </h3>
                    <p className="mt-3 text-sm leading-6 text-slate-600 font-normal">
                      {area.text}
                    </p>
                  </div>

                  <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between font-mono text-xs font-semibold text-[#2563EB]">
                    <span>Hỏi trợ lý AI chủ đề này</span>
                    <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* SECTION 3: CÁCH TIẾP CẬN — IRAC FRAMEWORK */}
        <section id="quy-trinh" className="mx-auto grid max-w-7xl gap-12 px-5 py-20 md:px-10 md:py-28 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="border-l-[3px] border-[#2563EB] pl-5">
            <p className="font-mono text-xs uppercase tracking-widest text-[#2563EB]">
              Cách tiếp cận — Khung IRAC
            </p>
            <h2 className="mt-4 font-display text-5xl uppercase leading-tight text-[#0F172A] md:text-6xl tracking-tight">
              Từ tình huống đến hướng xử lý.
            </h2>
            <p className="mt-6 text-sm leading-relaxed text-slate-600">
              Áp dụng khung lập luận pháp lý chuẩn quốc tế <strong className="text-[#0F172A]">IRAC</strong> — Issue, Rule, Application, Conclusion — giúp phân tích vụ việc có hệ thống và đưa ra kết luận rõ ràng.
            </p>
          </div>

          <ol className="border-t-2 border-[#0F172A]">
            {[
              ["I", "Issue — Xác định vấn đề", "Nhận diện tranh chấp hoặc vấn đề pháp lý cốt lõi từ tình huống thực tế: chủ thể, mốc thời gian, sự kiện và mong muốn cần giải quyết."],
              ["R", "Rule — Trích dẫn quy phạm", "Xác định Điều, Khoản, Luật hiện hành trực tiếp liên quan, kèm trạng thái hiệu lực. Không suy diễn — chỉ trích dẫn từ nguồn chính thống."],
              ["A", "Application — Phân tích áp dụng", "Lập luận chi tiết: áp dụng quy phạm vào tình tiết cụ thể, chỉ ra điểm phù hợp và các dữ kiện, tài liệu còn thiếu cần bổ sung."],
              ["C", "Conclusion — Kết luận & hướng xử lý", "Đưa ra kết luận pháp lý, phương án giải quyết khả thi: hòa giải, chuẩn bị hồ sơ khởi kiện hoặc tìm Luật sư khi tình huống phức tạp."],
            ].map(([letter, title, text]) => (
              <li key={letter} className="grid grid-cols-[3.5rem_1fr] gap-4 border-b border-slate-200 py-8 transition-colors hover:bg-slate-50/50">
                <span className="font-display text-3xl font-bold text-[#2563EB]">{letter}</span>
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

      {/* FLOATING CHATBOT WIDGET */}
      <Floating_chatbot />
    </div>
  );
};
