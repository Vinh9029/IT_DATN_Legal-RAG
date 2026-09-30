"""
check_gpu.py — Kiểm tra GPU / Device trước khi chạy pipeline embedding
=======================================================================
Chạy từ thư mục backend/:
    python scripts/check_gpu.py

Kết quả mong đợi (ví dụ):
    ✅ CUDA khả dụng → GPU: NVIDIA GeForce RTX 3050 | VRAM: 4.0 GB
    PyTorch version : 2.3.1+cu128
    CUDA version    : 12.8
    ...
"""
import sys
from pathlib import Path

# Cho phép import từ backend/ (chạy như: python scripts/check_gpu.py từ backend/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from src.utils.device import get_torch_device, log_device_summary


def main() -> None:
    logger.info("=" * 55)
    logger.info("   Legal-RAG — GPU / Device Checker")
    logger.info("=" * 55)

    # Tóm tắt môi trường
    log_device_summary()

    logger.info("-" * 55)

    # Chọn device sẽ được dùng thực tế
    device = get_torch_device()
    logger.info(f"→ Device sẽ dùng cho embedding: [{device.upper()}]")

    logger.info("=" * 55)

    # Gợi ý nếu đang dùng CPU
    if device == "cpu":
        logger.warning(
            "\n📋 GỢI Ý CÀI ĐẶT GPU:\n"
            "\n  [NVIDIA — Windows/Linux]\n"
            "  pip install torch torchvision torchaudio "
            "--index-url https://download.pytorch.org/whl/cu128\n"
            "\n  [AMD — Windows (DirectML)]\n"
            "  pip install torch-directml\n"
            "\n  [AMD — Linux (ROCm 6.x)]\n"
            "  pip install torch torchvision torchaudio "
            "--index-url https://download.pytorch.org/whl/rocm6.1\n"
            "\n  [Apple Silicon — M1/M2/M3/M4]\n"
            "  pip install torch torchvision torchaudio   "
            "(bản mặc định trên macOS đã có MPS)\n"
            "\n  Sau khi cài xong hãy chạy lại script này để xác nhận."
        )
    else:
        logger.success(
            f"\n✅ Sẵn sàng chạy pipeline! Device: {device.upper()}\n"
            "   Bước tiếp theo:\n"
            "   python scripts/offline_rag/03_build_qdrant.py"
        )


if __name__ == "__main__":
    main()
