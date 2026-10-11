// Tự animate bằng rAF vì Chrome bỏ qua behavior: 'smooth' khi Windows tắt Animation effects
const HEADER_OFFSET = 80;

const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

let frameId = 0;

export function smoothScrollTo(targetY: number, duration = 600) {
  cancelAnimationFrame(frameId);
  const startY = window.scrollY;
  const maxY = document.documentElement.scrollHeight - window.innerHeight;
  const distance = Math.min(Math.max(targetY, 0), maxY) - startY;
  const startTime = performance.now();

  const step = (now: number) => {
    const progress = Math.min((now - startTime) / duration, 1);
    window.scrollTo(0, startY + distance * easeInOutCubic(progress));
    if (progress < 1) frameId = requestAnimationFrame(step);
  };
  frameId = requestAnimationFrame(step);
}

export function smoothScrollToId(id: string, duration?: number) {
  const el = document.getElementById(id);
  if (!el) return;
  smoothScrollTo(el.getBoundingClientRect().top + window.scrollY - HEADER_OFFSET, duration);
}
