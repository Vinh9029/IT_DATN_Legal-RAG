import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowDown, ArrowRight, BriefcaseBusiness, FileCheck2, Landmark, Scale } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "LƯU HÀNH | Thông tin pháp luật Việt Nam rõ ràng" },
      { name: "description", content: "Đọc, hiểu và định hướng vấn đề pháp lý Việt Nam với nội dung rõ ràng cùng trợ lý pháp lý AI." },
      { property: "og:title", content: "LƯU HÀNH | Pháp luật, đọc được rõ ràng" },
      { property: "og:description", content: "Thông tin pháp luật Việt Nam và trợ lý tham khảo trực tuyến." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const areas = [
  { number: "01", title: "Hợp đồng & dân sự", text: "Đặt cọc, mua bán, vay mượn, bồi thường và giải quyết nghĩa vụ dân sự.", icon: FileCheck2 },
  { number: "02", title: "Lao động", text: "Hợp đồng lao động, tiền lương, bảo hiểm, kỷ luật và chấm dứt việc làm.", icon: BriefcaseBusiness },
  { number: "03", title: "Đất đai & nhà ở", text: "Chuyển nhượng, thừa kế, cấp giấy chứng nhận và tranh chấp quyền sử dụng đất.", icon: Landmark },
  { number: "04", title: "Doanh nghiệp", text: "Thành lập, quản trị, đầu tư, thuế và các nghĩa vụ tuân thủ thường gặp.", icon: Scale },
];

function Index() {
  return (
    <div className="min-h-screen overflow-hidden bg-background text-foreground">
      <header className="border-b border-foreground/20">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 md:px-10">
          <BrandMark />
          <nav className="hidden items-center gap-8 font-mono text-[11px] uppercase md:flex">
            <a href="#linh-vuc" className="hover:text-accent">Lĩnh vực</a>
            <a href="#quy-trinh" className="hover:text-accent">Cách tiếp cận</a>
            <a href="#luu-y" className="hover:text-accent">Lưu ý</a>
          </nav>
          <Button asChild className="rounded-none bg-accent text-accent-foreground hover:bg-accent/90">
            <Link to="/tro-ly">Hỏi trợ lý <ArrowRight /></Link>
          </Button>
        </div>
      </header>

      <main>
        <section className="relative mx-auto min-h-[calc(100svh-5rem)] max-w-7xl px-5 pb-20 pt-16 md:px-10 md:pt-24">
          <div className="grid gap-12 lg:grid-cols-[1fr_19rem]">
            <div className="editorial-rise">
              <p className="font-mono text-xs uppercase text-accent">Thông tin pháp luật Việt Nam</p>
              <h1 className="mt-5 max-w-5xl font-display text-[clamp(4.4rem,12vw,10.5rem)] uppercase leading-[0.82]">
                Pháp luật,<br /><span className="text-primary">đọc được</span><br />rõ ràng.
              </h1>
            </div>
            <div className="flex flex-col justify-end border-l border-foreground/20 pl-6 lg:pb-5">
              <p className="text-base leading-7 text-muted-foreground">Tìm hướng đi đầu tiên cho vấn đề pháp lý của bạn — bằng ngôn ngữ gần gũi, có giới hạn rõ ràng.</p>
              <Button asChild size="lg" className="mt-7 w-full rounded-none bg-foreground text-background hover:bg-primary">
                <Link to="/tro-ly">Mở trợ lý pháp lý <ArrowRight /></Link>
              </Button>
            </div>
          </div>
          <div className="editorial-grow absolute inset-x-5 bottom-8 flex items-center justify-between border-t border-foreground/25 pt-4 font-mono text-[10px] uppercase text-muted-foreground md:inset-x-10">
            <span>Nội dung tham khảo</span><ArrowDown className="size-4" />
          </div>
        </section>

        <section id="linh-vuc" className="border-y border-foreground/20 bg-surface">
          <div className="mx-auto max-w-7xl px-5 py-20 md:px-10 md:py-28">
            <div className="grid gap-8 border-b border-foreground/20 pb-10 md:grid-cols-2">
              <p className="font-mono text-xs uppercase text-accent">Lĩnh vực thường gặp</p>
              <h2 className="font-display text-5xl uppercase leading-none md:text-7xl">Bắt đầu từ đúng nhóm vấn đề.</h2>
            </div>
            <div className="grid md:grid-cols-2">
              {areas.map((area) => (
                <article key={area.number} className="group border-b border-foreground/15 py-8 md:odd:border-r md:odd:pr-10 md:even:pl-10">
                  <div className="flex items-start justify-between">
                    <span className="font-mono text-xs text-muted-foreground">{area.number}</span>
                    <area.icon className="size-6 text-accent" strokeWidth={1.5} />
                  </div>
                  <h3 className="mt-10 font-display text-3xl uppercase group-hover:text-primary">{area.title}</h3>
                  <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">{area.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="quy-trinh" className="mx-auto grid max-w-7xl gap-12 px-5 py-20 md:px-10 md:py-28 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="font-mono text-xs uppercase text-accent">Cách tiếp cận</p>
            <h2 className="mt-4 font-display text-5xl uppercase leading-none md:text-7xl">Từ tình huống đến hướng xử lý.</h2>
          </div>
          <ol className="border-t border-foreground/25">
            {[
              ["01", "Mô tả sự việc", "Nêu chủ thể, mốc thời gian, giấy tờ và điều bạn muốn đạt được."],
              ["02", "Làm rõ căn cứ", "Xác định nhóm quy định có thể liên quan và những dữ kiện còn thiếu."],
              ["03", "Chọn bước tiếp theo", "Chuẩn bị hồ sơ, trao đổi với bên liên quan hoặc tìm luật sư khi cần."],
            ].map(([number, title, text]) => (
              <li key={number} className="grid grid-cols-[3rem_1fr] gap-4 border-b border-foreground/20 py-7">
                <span className="font-mono text-xs text-accent">{number}</span>
                <div><h3 className="text-lg font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p></div>
              </li>
            ))}
          </ol>
        </section>

        <section id="luu-y" className="bg-primary text-primary-foreground">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 md:px-10 lg:grid-cols-[1fr_1.3fr]">
            <p className="font-mono text-xs uppercase text-primary-foreground/65">Giới hạn cần biết</p>
            <div>
              <h2 className="font-display text-4xl uppercase leading-tight md:text-6xl">Thông tin tốt giúp bạn hỏi đúng. Không thay thế một luật sư hiểu hồ sơ.</h2>
              <p className="mt-6 max-w-2xl text-sm leading-7 text-primary-foreground/70">Nội dung trên trang và phản hồi của trợ lý mang tính tham khảo chung, có thể chưa phản ánh thay đổi mới nhất hoặc hoàn cảnh riêng của vụ việc. Với tranh chấp, tố tụng, hình sự hay rủi ro lớn, hãy tìm tư vấn chuyên môn trực tiếp.</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-foreground/20 bg-foreground text-background">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-10 md:flex-row md:items-end md:justify-between md:px-10">
          <div><p className="font-display text-3xl uppercase">LƯU HÀNH</p><p className="mt-2 text-sm text-background/55">Pháp luật được trình bày để dễ bắt đầu.</p></div>
          <p className="font-mono text-[10px] uppercase text-background/45">© 2026 · Nội dung tham khảo</p>
        </div>
      </footer>
    </div>
  );
}
