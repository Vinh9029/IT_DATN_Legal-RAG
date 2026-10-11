// Thể thức trình bày dùng chung cho trang giấy trên màn hình, bản in PDF và file Word.
// Theo Phụ lục I Nghị định 30/2020/NĐ-CP: khổ A4, lề trên/dưới 20–25 mm, lề trái 30–35 mm,
// lề phải 15–20 mm, phông Times New Roman; quốc hiệu cỡ 12–13 in hoa đậm, tiêu ngữ cỡ 13–14 đậm.

export const PAGE = {
  widthMm: 210,
  heightMm: 297,
  margin: { top: 20, right: 15, bottom: 20, left: 30 },
  font: "'Times New Roman', Tinos, Times, serif",
  bodyPt: 13,
  mottoPt: 13,
  sloganPt: 14,
  titlePt: 14,
  formCodePt: 10,
  lineHeight: 1.4,
  indentMm: 10,
  gapPt: 6,
} as const;

export const MOTTO = 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM';
export const SLOGAN = 'Độc lập - Tự do - Hạnh phúc';
