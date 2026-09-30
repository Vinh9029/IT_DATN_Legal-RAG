import torch
from loguru import logger


def get_torch_device() -> str:
    """
    Tự động phát hiện thiết bị tối ưu để chạy PyTorch / Embedding.
    Thứ tự ưu tiên:
        1. CUDA   — NVIDIA GPU (cần torch với CUDA build)
        2. CUDA   — AMD ROCm trên Linux (torch ROCm build)
        3. MPS    — Apple Silicon Mac (M1/M2/M3/M4)
        4. DirectML — AMD GPU trên Windows (cần torch-directml)
        5. CPU    — Fallback an toàn nhất

    Returns:
        str — tên device hợp lệ để truyền vào SentenceTransformer / model.to(device)
    """

    # ── 1. CUDA (NVIDIA hoặc AMD ROCm trên Linux) ──────────────
    if torch.cuda.is_available():
        device = "cuda"
        try:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem  = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            logger.info(
                f"✅ CUDA khả dụng → GPU: {gpu_name} | VRAM: {gpu_mem:.1f} GB"
            )
        except Exception:
            logger.info("✅ CUDA khả dụng (không đọc được tên GPU)")
        return device

    # ── 2. MPS — Apple Silicon (Mac M1/M2/M3/M4) ───────────────
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        logger.info("✅ MPS (Apple Silicon) khả dụng → sử dụng GPU tích hợp Mac")
        return device

    # ── 3. DirectML — AMD / Intel GPU trên Windows ─────────────
    try:
        import torch_directml  # type: ignore[import-untyped]
        if torch_directml.is_available():
            device = str(torch_directml.device())
            logger.info(
                f"✅ DirectML khả dụng → AMD/Intel GPU (Windows) | device: {device}"
            )
            return device
        else:
            logger.warning("⚠️  torch_directml đã cài nhưng DirectML không khả dụng")
    except ImportError:
        pass  # torch_directml chưa được cài — OK, fallback tiếp

    # ── 4. CPU fallback ─────────────────────────────────────────
    device = "cpu"
    logger.warning(
        "⚠️  Không tìm thấy GPU phù hợp → chạy trên CPU "
        "(embedding sẽ chậm hơn đáng kể với tập dữ liệu lớn)"
    )
    return device


def log_device_summary() -> None:
    """In tóm tắt thông tin môi trường PyTorch + GPU ra log — dùng để debug."""
    logger.info(f"  PyTorch version : {torch.__version__}")
    logger.info(f"  CUDA available  : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"  CUDA version    : {torch.version.cuda}")
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            logger.info(
                f"  GPU [{i}]          : {props.name} | "
                f"VRAM {props.total_memory / 1024**3:.1f} GB | "
                f"SM {props.major}.{props.minor}"
            )
    mps_ok = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    logger.info(f"  MPS available   : {mps_ok}")
    try:
        import torch_directml  # type: ignore[import-untyped]
        logger.info(f"  DirectML avail  : {torch_directml.is_available()}")
    except ImportError:
        logger.info("  DirectML avail  : ✗ (torch_directml chưa cài)")
