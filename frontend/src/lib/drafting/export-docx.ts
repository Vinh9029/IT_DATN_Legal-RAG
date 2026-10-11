import type { DocBlock, DocRun } from './document';
import { MOTTO, PAGE, SLOGAN } from './page-format';

// Xuất file Word để người dùng chỉnh tiếp. Thư viện `docx` khá nặng nên chỉ tải khi bấm xuất.

const MM_TO_TWIP = 56.7;
const pt = (n: number) => n * 2; // docx tính cỡ chữ theo nửa point
const twip = (mm: number) => Math.round(mm * MM_TO_TWIP);

export async function buildDocx(blocks: DocBlock[]): Promise<Blob> {
  const d = await import('docx');
  const FONT = 'Times New Roman';

  const textWidthMm = PAGE.widthMm - PAGE.margin.left - PAGE.margin.right;
  const lineSpacing = Math.round(240 * PAGE.lineHeight * 0.92); // "multiple" của Word rộng hơn line-height CSS một chút
  const ALIGN = {
    left: d.AlignmentType.LEFT,
    center: d.AlignmentType.CENTER,
    right: d.AlignmentType.RIGHT,
    justify: d.AlignmentType.JUSTIFIED,
  } as const;

  const run = (r: DocRun, size: number = PAGE.bodyPt) =>
    new d.TextRun({ text: r.text, bold: r.bold, italics: r.italic, font: FONT, size: pt(size) });

  const NO_BORDER = { style: d.BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const NO_BORDERS = { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER, insideHorizontal: NO_BORDER, insideVertical: NO_BORDER };

  const children: (InstanceType<typeof d.Paragraph> | InstanceType<typeof d.Table>)[] = [];

  for (const b of blocks) {
    switch (b.kind) {
      case 'form-code':
        children.push(
          new d.Paragraph({
            alignment: d.AlignmentType.RIGHT,
            spacing: { after: 160 },
            children: b.lines.flatMap((line, i) => [
              ...(i ? [new d.TextRun({ break: 1 })] : []),
              new d.TextRun({ text: line, italics: true, font: FONT, size: pt(PAGE.formCodePt) }),
            ]),
          }),
        );
        break;

      case 'motto':
        children.push(
          new d.Paragraph({
            alignment: d.AlignmentType.CENTER,
            children: [new d.TextRun({ text: MOTTO, bold: true, font: FONT, size: pt(PAGE.mottoPt) })],
          }),
          // Gạch dưới tiêu ngữ dài đúng bằng dòng chữ: ô bảng một cột, chỉ có viền dưới
          new d.Table({
            alignment: d.AlignmentType.CENTER,
            width: { size: twip(68), type: d.WidthType.DXA },
            columnWidths: [twip(68)],
            borders: NO_BORDERS,
            rows: [
              new d.TableRow({
                children: [
                  new d.TableCell({
                    borders: { top: NO_BORDER, left: NO_BORDER, right: NO_BORDER, bottom: { style: d.BorderStyle.SINGLE, size: 6, color: '000000' } },
                    margins: { left: 0, right: 0, bottom: 20 },
                    children: [
                      new d.Paragraph({
                        alignment: d.AlignmentType.CENTER,
                        children: [new d.TextRun({ text: SLOGAN, bold: true, font: FONT, size: pt(PAGE.sloganPt) })],
                      }),
                    ],
                  }),
                ],
              }),
            ],
          }),
          new d.Paragraph({ spacing: { after: 60 }, children: [] }),
        );
        break;

      case 'title':
        children.push(
          new d.Paragraph({
            alignment: d.AlignmentType.CENTER,
            spacing: { before: 280, after: b.sub ? 0 : 200 },
            children: [new d.TextRun({ text: b.text, bold: true, font: FONT, size: pt(PAGE.titlePt) })],
          }),
        );
        if (b.sub) {
          children.push(new d.Paragraph({ alignment: d.AlignmentType.CENTER, spacing: { after: 200 }, children: b.sub.map((r) => run(r)) }));
        }
        break;

      case 'para':
        children.push(
          new d.Paragraph({
            alignment: ALIGN[b.align],
            indent: b.indent || b.inset ? { firstLine: b.indent ? twip(PAGE.indentMm) : undefined, left: b.inset ? twip(PAGE.indentMm) : undefined } : undefined,
            spacing: { before: b.gap ? PAGE.gapPt * 20 : 0, after: 40, line: lineSpacing },
            children: b.runs.map((r) => run(r)),
          }),
        );
        break;

      case 'blank-lines':
        // Mỗi dòng là một tab chấm kéo tới lề phải — in ra là dòng chấm để viết tay
        for (let i = 0; i < b.count; i++) {
          children.push(
            new d.Paragraph({
              indent: b.indent ? { left: twip(PAGE.indentMm) } : undefined,
              tabStops: [{ type: d.TabStopType.RIGHT, position: twip(textWidthMm - (b.indent ? PAGE.indentMm : 0)), leader: d.LeaderType.DOT }],
              spacing: { line: lineSpacing },
              children: [new d.TextRun({ text: '\t', font: FONT, size: pt(PAGE.bodyPt) })],
            }),
          );
        }
        break;

      case 'signatures': {
        const cols = b.parties.length === 1 ? [null, b.parties[0]] : b.parties;
        const colWidth = twip(textWidthMm / cols.length);
        const cell = (p: (typeof b.parties)[number] | null) =>
          new d.TableCell({
            borders: { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER },
            width: { size: colWidth, type: d.WidthType.DXA },
            children: p
              ? [
                  new d.Paragraph({ alignment: d.AlignmentType.CENTER, children: [new d.TextRun({ text: p.title.toUpperCase(), bold: true, font: FONT, size: pt(PAGE.bodyPt) })] }),
                  ...(p.caption
                    ? [new d.Paragraph({ alignment: d.AlignmentType.CENTER, children: [new d.TextRun({ text: p.caption, italics: true, font: FONT, size: pt(PAGE.bodyPt) })] })]
                    : []),
                  new d.Paragraph({ spacing: { before: twip(22) }, children: [] }),
                  new d.Paragraph({ alignment: d.AlignmentType.CENTER, children: [new d.TextRun({ text: p.name ?? '', bold: true, font: FONT, size: pt(PAGE.bodyPt) })] }),
                ]
              : [new d.Paragraph({ children: [] })],
          });
        children.push(
          new d.Paragraph({ spacing: { before: 200 }, children: [] }),
          new d.Table({
            width: { size: twip(textWidthMm), type: d.WidthType.DXA },
            columnWidths: cols.map(() => colWidth),
            borders: NO_BORDERS,
            rows: [new d.TableRow({ cantSplit: true, children: cols.map(cell) })],
          }),
        );
        break;
      }
    }
  }

  const doc = new d.Document({
    styles: { default: { document: { run: { font: FONT, size: pt(PAGE.bodyPt) } } } },
    sections: [
      {
        properties: {
          page: {
            size: { width: twip(PAGE.widthMm), height: twip(PAGE.heightMm) },
            margin: { top: twip(PAGE.margin.top), right: twip(PAGE.margin.right), bottom: twip(PAGE.margin.bottom), left: twip(PAGE.margin.left) },
          },
        },
        children,
      },
    ],
  });
  return d.Packer.toBlob(doc);
}

export function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
