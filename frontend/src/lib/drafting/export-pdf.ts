import type { DocBlock, DocRun } from './document';
import { MOTTO, PAGE, SLOGAN } from './page-format';

// Xuất PDF bằng chính bộ in của trình duyệt (in → "Lưu dưới dạng PDF"): chữ Việt có dấu giữ nguyên,
// không phải nhúng phông vào bundle. Văn bản được dựng trong một iframe ẩn, tách hẳn khỏi giao diện app.

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const runHtml = (r: DocRun) => {
  let html = esc(r.text);
  if (r.bold) html = `<b>${html}</b>`;
  if (r.italic) html = `<i>${html}</i>`;
  return html;
};

function blockHtml(b: DocBlock): string {
  switch (b.kind) {
    case 'form-code':
      return `<div class="form-code">${b.lines.map(esc).join('<br>')}</div>`;
    case 'motto':
      return `<div class="motto"><div class="motto-1">${MOTTO}</div><div class="motto-2"><span>${SLOGAN}</span></div></div>`;
    case 'title':
      return `<div class="title">${esc(b.text)}</div>${b.sub ? `<div class="title-sub">${b.sub.map(runHtml).join('')}</div>` : ''}`;
    case 'para': {
      const cls = ['p', b.indent && 'indent', b.inset && 'inset', b.gap && 'gap'].filter(Boolean).join(' ');
      return `<p class="${cls}" style="text-align:${b.align}">${b.runs.map(runHtml).join('') || '&nbsp;'}</p>`;
    }
    case 'blank-lines':
      return `<div class="blank-lines${b.indent ? ' indent' : ''}">${'<div></div>'.repeat(b.count)}</div>`;
    case 'signatures':
      return `<table class="signatures"><tr>${b.parties
        .map(
          (p) => `<td><div class="sig-title">${esc(p.title)}</div>${p.caption ? `<div class="sig-caption">${esc(p.caption)}</div>` : ''}<div class="sig-space"></div><div class="sig-name">${p.name ? esc(p.name) : ''}</div></td>`,
        )
        .join('')}</tr></table>`;
  }
}

export function documentHtml(title: string, blocks: DocBlock[]): string {
  const m = PAGE.margin;
  // Chữ ký một bên: đặt nửa phải trang như mẫu giấy
  const css = `
    @page { size: A4; margin: ${m.top}mm ${m.right}mm ${m.bottom}mm ${m.left}mm; }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body { font-family: ${PAGE.font}; font-size: ${PAGE.bodyPt}pt; line-height: ${PAGE.lineHeight}; color: #000; }
    .form-code { text-align: right; font-style: italic; font-size: ${PAGE.formCodePt}pt; line-height: 1.3; margin-bottom: 8pt; }
    .motto { text-align: center; margin-bottom: 6pt; }
    .motto-1 { font-weight: bold; font-size: ${PAGE.mottoPt}pt; }
    .motto-2 { font-weight: bold; font-size: ${PAGE.sloganPt}pt; }
    .motto-2 span { display: inline-block; border-bottom: 1px solid #000; padding-bottom: 1pt; }
    .title { text-align: center; font-weight: bold; font-size: ${PAGE.titlePt}pt; margin-top: 14pt; }
    .title-sub { text-align: center; margin-bottom: 4pt; }
    .title + :not(.title-sub) { margin-top: 10pt; }
    .title-sub + * { margin-top: 10pt; }
    p.p { margin: 0 0 2pt; }
    p.indent { text-indent: ${PAGE.indentMm}mm; }
    p.inset, .blank-lines.indent { padding-left: ${PAGE.indentMm}mm; }
    p.gap { margin-top: ${PAGE.gapPt}pt; }
    .blank-lines div { height: ${PAGE.lineHeight}em; border-bottom: 1.2px dotted #000; }
    .signatures { width: 100%; border-collapse: collapse; margin-top: 14pt; page-break-inside: avoid; }
    .signatures td { vertical-align: top; text-align: center; padding: 0 4mm; }
    .signatures td:only-child { padding-left: 50%; }
    .sig-title { font-weight: bold; text-transform: uppercase; }
    .sig-caption { font-style: italic; }
    .sig-space { height: 24mm; }
    .sig-name { font-weight: bold; }
  `;
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${css}</style></head><body>${blocks
    .map(blockHtml)
    .join('\n')}</body></html>`;
}

/** Mở hộp thoại in của trình duyệt cho văn bản; tên file PDF mặc định lấy theo `title` */
export function printDocument(title: string, blocks: DocBlock[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const iframe = document.createElement('iframe');
    iframe.setAttribute('aria-hidden', 'true');
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden';
    document.body.appendChild(iframe);

    const win = iframe.contentWindow;
    const doc = iframe.contentDocument;
    if (!win || !doc) {
      iframe.remove();
      reject(new Error('Trình duyệt không cho phép mở bản in.'));
      return;
    }

    doc.open();
    doc.write(documentHtml(title, blocks));
    doc.close();

    const cleanup = () => setTimeout(() => iframe.remove(), 1000);
    win.addEventListener('afterprint', cleanup, { once: true });

    // Chờ phông tải xong để trang in không bị nhảy chữ
    const ready = doc.fonts?.ready ?? Promise.resolve();
    ready.then(() => {
      // Chrome lấy tiêu đề trang chính làm tên file PDF khi in từ iframe
      const previous = document.title;
      document.title = title;
      win.focus();
      win.print();
      document.title = previous;
      resolve();
      // Một số trình duyệt không bắn afterprint với iframe
      setTimeout(cleanup, 60_000);
    });
  });
}
