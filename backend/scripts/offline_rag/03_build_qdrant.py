import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import (
    PROCESSED_DATA_DIR,
    ensure_directories,
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
)
from src.indexing.qdrant_builder import build_qdrant_index
from src.utils.device import log_device_summary
from loguru import logger


def main():
    ensure_directories()

    # Hiển thị thông tin GPU/device trước khi chạy embedding
    log_device_summary()

    chunks_path = PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl"

    if not chunks_path.exists():
        logger.error(f"File {chunks_path} không tồn tại. Vui lòng chạy 02_chunk_documents.py trước.")
        sys.exit(1)

    # Kiểm tra tham số CLI (--cpu, --gpu, --directml)
    device = None
    batch_size = 64

    if "--gpu" in sys.argv or "--directml" in sys.argv:
        from src.utils.device import get_torch_device
        device = get_torch_device()
        batch_size = 16
        logger.info(f"Ép buộc chạy GPU qua CLI → Device: {device} (batch_size=16).")
    elif "--cpu" in sys.argv or "cpu" in sys.argv:
        device = "cpu"
        batch_size = 128
        logger.info("Chế độ CPU được chọn qua CLI (tối ưu đa luồng, ổn định 100%).")
    else:
        from src.utils.device import get_torch_device
        detected_device = get_torch_device()
        if "privateuseone" in detected_device:
            # DirectML rò rỉ VRAM khi chạy 500k+ chunks liên tục
            logger.info("Phát hiện DirectML (AMD/Intel GPU). Mặc định chọn CPU đa luồng để đảm bảo ổn định 100% không tràn VRAM. (Dùng '--gpu' nếu muốn ép chạy GPU AMD).")
            device = "cpu"
            batch_size = 128
        else:
            device = detected_device

    logger.info("=== BẮT ĐẦU BUILD VECTOR INDEX TRÊN QDRANT (LOCAL DOCKER) ===")
    build_qdrant_index(
        chunks_path=chunks_path,
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        collection_name=QDRANT_COLLECTION_NAME,
        model_name=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        batch_size=batch_size,
        device=device,
    )


if __name__ == "__main__":
    main()
