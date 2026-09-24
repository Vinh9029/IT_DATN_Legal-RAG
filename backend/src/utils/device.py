import torch
from loguru import logger

def get_torch_device() -> str:
    """
    Tự động phát hiện thiết bị tối ưu để chạy PyTorch / Embedding:
    1. CUDA (NVIDIA / AMD ROCm trên Linux)
    2. MPS (Apple Silicon Mac M1/M2/M3/M4)
    3. DirectML (AMD GPU trên Windows nếu cài torch_directml)
    4. Fallback về CPU
    """
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        try:
            import torch_directml
            if torch_directml.is_available():
                device = str(torch_directml.device())
            else:
                device = "cpu"
        except ImportError:
            device = "cpu"

    logger.info(f"Sử dụng thiết bị embedding: {str(device).upper()}")
    return device
